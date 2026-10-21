# Card #449 — `up` output carries no host values

`ops/agenthub_deploy.py up` runs from a systemd unit at boot, so its output lands in the journal. It
also lands in the test logs of this public repository. This card makes sure that output never
contains a host value, in every outcome. It also makes an unexpected exception end in a fixed
reason, never the exception text. Split from #443 (its G4.1). Depends on #448 (merged).

Touches: `ops/agenthub_deploy.py`, `tests/test_agenthub_deploy.py`,
`tests/acceptance/test_card_449_up_redaction.py`, `.agent/contracts/card-449.md`

Acceptance tests (Claude-owned; Codex must not edit `tests/acceptance/`):
`tests/acceptance/test_card_449_up_redaction.py` (7 tests). Every test runs the real script as a
subprocess. Test 7 runs the script's `__main__` through a small launcher that first installs a
fault (see G3). Fake `docker` and `curl` executables are the **only** entries on `PATH`, so no real
daemon can be reached. No real container is used.

PR body: `ops/agenthub_deploy.py` is a pinned release file. Write
"re-pin required: ops/agenthub_deploy.py".

## Revision 3

The gate's adversarial check caught 0 of 4 mutants on `9dae8cd`. Revision 3 covers each **class**
of those mutants, not only the instance:
1. **Text from outside reaches the output** (a health body logged while waiting). New test 6 runs
   the health wait through wrong answers to success, and through wrong answers to the timeout.
   Every field of every answer carries a canary or a number.
2. **A configured number reaches the output** (the database timeout in a "no healthcheck"
   message). Every numeric setting now has a distinctive value in every run, and no run may print
   one. Test 3 adds a database without a healthcheck, running and stopped.
3. **Exception text in a reason** (a new decoding handler). Every `reason=` must now be exactly one
   of the fixed reasons below. Tests 5 and 7 add Docker output that is not UTF-8, and a
   `UnicodeDecodeError` with canary text.
4. **A narrowed catch-all.** New test 7 raises an exception class derived from `Exception` only, and
   a `UnicodeDecodeError`, at an external call in every phase.

Also new in revision 3:
- G1 adds a Docker that answers only after three failed calls, and a sync that holds the lock while
  a deploy starts the serving release.
- `elapsed_s=` must hold a plain number.

As far as I can tell by reading, `9dae8cd` passes revision 3 unchanged. None of the four classes
exposes a real leak in it. I could not run the tests in this sandbox, so the gate's run is the
authority.

## Revision 2

The gate's adversarial check failed on `945d64b`. Revision 2 added:
- the number rule;
- the install-path check;
- the code-location check;
- the one-output-per-group rule;
- new G1 and G2 paths;
- canaries in labels, the health log, the `docker start` stdout, the health body, `USER`,
  `LOGNAME` and `HOSTNAME`.

## Interface

Only `up` changes. `deploy`, `rollback` and their helpers behave exactly as they do today, and their
tests in `tests/test_agenthub_deploy.py` keep passing unchanged. Everything in the #447 and #448
contracts still holds for `up`: the order of work, the timeouts, the selection rules, the Docker
command surface, the result line and the exit codes. The #447 and #448 acceptance tests must keep
passing.

### What `up` may print

Only these values may appear in `up`'s stdout or stderr:
- container names, including the configured database name and the release prefix as part of a name;
- revisions, meaning the revision labels of release containers. A revision that a health answer
  reports is outside text and is never printed **(rev 3)**;
- fixed text written in the script;
- exactly two kinds of number:
  - the `elapsed_s` value, written as a plain number such as `elapsed_s=0.4` **(rev 3)**;
  - a Docker exit code, written as `(exit <n>)`, as `run()` already does.

  No other number may appear: no timeout or other configured value, no container or image id, no
  Docker version, no process id and no line number.

### Fixed reasons (rev 3)

The text after ` reason=` on a `result=failed` line is exactly one of these. `<db>` is the
configured database name, `<name>` a container name, `<names>` a `, `-separated list of container
names and `<n>` a Docker exit code. These are the messages `9dae8cd` already prints:

| Reason |
|---|
| `Docker daemon did not become available` |
| `database <db> is missing or unavailable` |
| `database start failed (exit <n>)` |
| `database <db> did not become healthy` |
| `docker ps failed (exit <n>)` |
| `docker inspect failed (exit <n>)` |
| `the configured port is published by a non-release container: <names>` |
| `multiple running release containers publish the configured port: <names>` |
| `<name> has an invalid source revision label` |
| `<name> does not mount exactly the configured private volume read-write at /var/lib/ai-caddie` |
| `<name> is not on the configured network` |
| `multiple latest stopped release candidates: <names>` |
| `no stopped release container matches the configured layout and port` |
| `sync lock was not acquired in time; a sync is still running` |
| `API start failed (exit <n>)` |
| `<name> did not report status=ok for its revision` |
| `unexpected failure` |

Nothing is appended to a reason: no detail, no exception text, no decoder message. A failure the
list does not name ends in `unexpected failure`.

### What `up` never prints

`up` never prints any of these, on stdout or stderr, in any outcome:
- **Environment values.** That covers every variable except the container names above. Examples:
  tokens, `DOCKER_HOST`, `USER`, `LOGNAME`, `HOSTNAME`, the configured volume
  (`AICADDIE_PRIVATE_VOLUME`) and network (`AICADDIE_DEPLOY_NETWORK`), and **(rev 3)** every
  numeric setting: every timeout, the poll interval, the deadline, the CPU, memory and
  keep-stopped values, and the port.
- **Configured paths, URLs and the port.** That covers:
  - the sync lock, the sync script, the bootstrap env file and the public health URL;
  - the local health URL and `127.0.0.1`;
  - the configured `AICADDIE_API_PORT`.
- **Temporary directories and install paths.** That covers `HOME`, `TMPDIR`, `XDG_RUNTIME_DIR`, the
  checkout path and the interpreter's path and prefixes.
- **Container data:** a container's `Env`, its mount sources, its labels other than the revision,
  its network and volume names, and the database's health record (`State.Health`, with its log).
- **Text from outside**, from every source, failing calls included:
  - Docker's own stdout and stderr, from every `docker` call. That output can name the daemon
    socket, the config file, the data root or the host name. It includes the stdout of
    `docker start` and of `docker info`;
  - curl's error text, which echoes the URL;
  - **(rev 3)** any part of a health answer: its status, its revision, its other keys, a body that
    is not a JSON object, and bytes that are not UTF-8;
  - **(rev 3)** the text, type, module and location of any exception.
- **A traceback**, or Python's `File "…"` lines.

### Unexpected exceptions

An exception that is not a `DeployError` and is raised in any phase (`docker`, `database`, `api`)
gives one result:
- exit 1;
- one result line, `result=failed action=up part=<that phase>`;
- `container=` as in #447: `none` for `docker`, the configured database name for `database`, and
  for `api` the selected release, or `none` while no release has been selected;
- a fixed reason from the list above.

**(rev 3) Any type.** This holds for an exception of any class derived from `Exception`: an
`OSError`, a `ValueError` (including `UnicodeDecodeError` and `JSONDecodeError`), a `TypeError`,
`KeyError` or `AttributeError`, and a class derived from `Exception` alone. A handler narrowed to a
list of builtin families fails.

**One failure, one output.** Each group below is a single failure, whichever exception its cases
raise. Every case of a group prints the same lines, on stdout and on stderr. The `elapsed_s` value
is ignored, and a repeated line counts once.

| Group | `part` | `container` | Cases (the exception each raises in `9dae8cd`) |
|---|---|---|---|
| `docker` cannot be run | `docker` | `none` | not on `PATH` (`FileNotFoundError`); not executable (`PermissionError`); no `#!` line (`OSError`, exec format error) |
| the database inspect is unreadable | `database` | `<db>` | no JSON (`JSONDecodeError`); a JSON list (`TypeError`); an object without `running` (`KeyError`); a `health` that is text (`AttributeError`); **(rev 3)** bytes that are not UTF-8 (`UnicodeDecodeError`) |
| the release listing is unreadable | `api` | `none` | no JSON; a JSON list; an object without `id`; a `name` that is a list; **(rev 3)** bytes that are not UTF-8 |
| the sync lock cannot be opened | `api` | not checked | its directory is missing (`FileNotFoundError`); it is a directory (`IsADirectoryError`); its parent is a file (`NotADirectoryError`) |
| **(rev 3)** an external call raises (test 7) | the call's phase | see G3 | `CanaryFault` (derived from `Exception` only); `UnicodeDecodeError` |

A group may get its own `DeployError` with a reason from the list instead of `unexpected failure`.
That reason then covers every case of the group. Reading unreadable output leniently, for example as
"not running" or "not healthy", gives a different output for some cases, so it fails.

## Goals and pass conditions

**Hygiene.** Every run in every test passes these checks on stdout and on stderr:
- no line contains `canary` (case-insensitive), the temporary directory or the checkout path;
- no line contains `47913` (the configured port), `127.0.0.1`, `/api/v2/health`, `unix://` or
  `docker.sock`;
- no line contains the interpreter's path or prefixes: `sys.executable`, its real path,
  `sys.prefix`, `sys.base_prefix` and `sys.exec_prefix`. Values shorter than 5 characters, such as
  `/usr`, are skipped;
- no line holds a digit once container names, revisions, `elapsed_s=<plain number>` and
  `(exit <n>)` are removed;
- **(rev 3)** neither stream contains the value of any numeric setting of that run, as configured
  (for example `0.7193` or `8263`);
- no `Traceback` and no `File "` line;
- `docker` is called only with `info`, `version`, `ps`, `inspect`, `image inspect` and `start`;
- no sync script run and no public health request.

Every failed run also has a reason from the fixed list **(rev 3)**.

**Canaries.** Every value the script can see carries the word `canary`, except container names and
revisions:
- the environment: `HOME`, `TMPDIR`, `XDG_RUNTIME_DIR`, `USER`, `LOGNAME`, `HOSTNAME`,
  `DOCKER_HOST`, `DOCKER_CONFIG`, an admin token, the lock path, the sync script, the bootstrap env
  file, the public URL, the volume and the network;
- the containers' `Env`, mount sources and labels: the compose working directory and config file,
  and a build-context label. Also the database's health log;
- the fake `docker`'s stderr on every call, failing ones included. It names a config file, the
  daemon socket, the data root and the host name;
- the fake `docker info` stdout, and a line on the fake `docker start` stdout;
- the fake `curl`'s stderr, which also echoes the local URL with the port, and a `host` field in
  the health body;
- **(rev 3)** the wrong health answers of test 6, and the message of every exception test 7 raises.

**(rev 3) Numbers.** Every numeric setting has a value that appears nowhere else:
`AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS=15.9371`, `…_PUBLIC_HEALTH_TIMEOUT_SECONDS=7.3719`,
`…_LOCK_TIMEOUT_SECONDS=16.5317`, `…_DEADLINE_SECONDS=2913.8264`, `…_POLL_SECONDS=0.0386`,
`…_KEEP_STOPPED=8263`, `…_DEFAULT_CPUS=1.7319`, `…_DEFAULT_MEMORY_BYTES=5293817`,
`AICADDIE_UP_DOCKER_TIMEOUT_SECONDS=23.6173` and `AICADDIE_DB_READY_TIMEOUT_SECONDS=24.7193`. Paths
that time out use short values that are just as distinctive: docker `0.6173`, database `0.7193`,
health `1.9371` (test 6: `4.9371`), lock `0.5317`.

**Start calls** means every `docker start` the script asked for, failed ones included.

### G1 — A successful `up` prints no host values

1. `test_successful_up_prints_no_host_values`:
   - After a reboot: the database and `SERVING` are stopped. The result is exit 0,
     `container=SERVING`, start calls `[db, SERVING]`, and health read for its revision.
   - The stack is already healthy: exit 0, `container=SERVING`, no start call.
   - A newer stopped release is on another volume and another network. It is skipped: exit 0,
     `container=SERVING`, start calls `[SERVING]`.
   - **(rev 3)** Docker answers only after three failed calls, each with the daemon-down
     diagnostics: exit 0, `container=SERVING`, start calls `[db, SERVING]`.
   - **(rev 3)** A sync holds the lock. Once `up` has listed the containers, a deploy starts
     `SERVING`, and then the sync releases the lock: exit 0, `container=SERVING`, no start call
     (#448: `up` lists again under the lock).
6. `test_health_answers_never_reach_the_output` **(rev 3)**, waiting path: the first six health
   answers are wrong, then the right one comes. The wrong answers are:
   - a canary status with the right revision;
   - `ok` with a canary revision and a canary key;
   - `ok` with an unknown 40-digit revision and numeric extra keys;
   - a canary status and revision with a nested error object;
   - a JSON list;
   - plain text.

   The result is exit 0 and `container=SERVING`, after every wrong answer was read.

Every run passes the hygiene checks.

### G2 — A failed `up` prints no host values, whatever part fails

2. `test_docker_failure_prints_no_host_values` (pinned). The daemon never answers: every call
   fails with "Cannot connect to the Docker daemon at unix:///…", and `info` also prints client
   details on stdout. The result is exit 1, `part=docker`, `container=none`, and no start call.
3. `test_database_failure_prints_no_host_values` (pinned). Each case gives exit 1,
   `part=database`, `container=garmin-ai-caddie-db-1`, and `SERVING` is not started:
   - the database is missing;
   - its `docker start` fails;
   - it stays `unhealthy`;
   - **(rev 3)** it runs without a healthcheck (no `State.Health`);
   - **(rev 3)** it is stopped and has no healthcheck, so it is started and never becomes healthy.
4. `test_api_failure_prints_no_host_values`. Each case gives exit 1 and `part=api`:
   - `docker ps` fails;
   - `docker inspect` of the release containers fails;
   - there is no release container;
   - the API `docker start` fails;
   - the API health never answers (curl fails);
   - the running release has no revision label;
   - a non-release container publishes the port;
   - two running releases publish the port;
   - the running release is on another network;
   - the running release mounts another volume;
   - the newest stopped releases tie;
   - a sync holds the lock, with no start call.
6. `test_health_answers_never_reach_the_output` **(rev 3)**, timeout path: the six wrong answers,
   then a body that is not UTF-8, in turn until the health timeout. The result is exit 1,
   `part=api`, `container=SERVING`, after every wrong answer was read at least once. `up` may end
   at the body that is not UTF-8 (`unexpected failure`), or count it as "not yet" and time out.

Every run passes the hygiene checks. Tests 2 and 3 already pass on `main` and pin that behaviour.

### G3 — An unexpected exception ends in its phase's `part=` and a fixed reason

5. `test_unexpected_errors_end_with_the_phase_and_a_fixed_reason`. It runs the first four groups
   of the table above. Each case gives:
   - exit 1 with the group's `part=`, and its `container=` where the table fixes it;
   - the hygiene checks pass, and the reason is from the fixed list;
   - neither stream matches any of these:
     - `\b[A-Za-z]*(Error|Exception)\b`, `Errno`, `Traceback`, `\bline \d+`, `\.py\b`;
     - `No such file`, `Permission denied`, `Is a directory`, `Not a directory`, `Exec format`;
     - `Expecting value`, `has no attribute`, `not subscriptable`, `indices must be`;
   - once container names and revisions are removed, the reason holds no digit and no snake_case or
     dunder identifier;
   - no start call (`docker` and listing groups, the lock group), or `SERVING` not started
     (database group).

   Then, per group, every case printed the same lines as the group's first case.
7. `test_any_exception_in_any_phase_ends_with_its_part_and_a_fixed_reason` **(rev 3)**. A launcher
   imports a fault module and then runs `ops/agenthub_deploy.py` with
   `runpy.run_path(..., run_name="__main__")`, so `main()` runs as it does from the command line.
   The fault module replaces `subprocess.Popen`, so every matching external call raises instead of
   running, every time. Each call point is tried with two exceptions:
   - `CanaryFault`, a class derived from `Exception` only, defined in module `canary_fault_449`,
     with a canary in its message;
   - a `UnicodeDecodeError` over bytes that are not UTF-8, with a canary in its reason.

   | Calls that raise | `part` | `container` |
   |---|---|---|
   | every `docker` call | `docker` | `none` |
   | every `docker` call that names the database (by name or id) | `database` | `<db>` |
   | every `docker ps` | `api` | `none` |
   | every `docker start` of `SERVING` (by name or id) | `api` | `SERVING` |
   | every `curl` | `api` | `SERVING` |

   Each case gives exit 1 with that `part=` and `container=`, and passes every check of test 5.
   The fault must really have been raised: the fault module records it. `SERVING` is not started,
   except at the health read. At each call point, both exceptions print the same lines.

   The docker, database, health and lock timeouts are short in these cases, so an implementation
   that retries until a timeout still ends quickly.

## Free choices (not tested)

- How Docker's output is kept out: captured, discarded, or sent to `DEVNULL`. It must never be
  forwarded.
- Whether a group of the G3 table gets a reason of its own from the fixed list, or falls through to
  `unexpected failure`. Either way the whole group gives one output.
- Whether a `docker` that cannot be run, or an external call that raises, is retried until its
  timeout or fails at once. Either way the part is the phase's.
- Whether a health answer that is not UTF-8 ends the wait at once or counts as "not yet".
- Extra log lines before the result line, if they print only allowed values.

**(rev 3)** The wording of `reason=` is no longer free: it is one of the fixed reasons.

## Not covered (other cards; do not add here)

- Signal handling. That includes a signal that arrives while the result is printed.
- Configuration errors. They stay exit 2 with a message that names the variable, as today.
- `deploy` and `rollback` output.
- The systemd unit and the runbook.

## Gate notes

`main` (`69627e4`) differs from `9dae8cd` in `ops/agenthub_deploy.py` in two places:
- `list_containers` runs `docker ps` without `quiet=True`, so its stderr reaches the output. Every
  run that reaches the API phase therefore prints the fake Docker's canary diagnostics. That makes
  tests 1, 4 and 6 fail on `main`.
- `up` reports `unexpected <TypeName>`, for example `unexpected FileNotFoundError`. That makes
  test 5 fail on `main`. Test 7 fails there too, on `unexpected CanaryFault`: it carries the
  canary, and it is not a fixed reason.

Tests 2 and 3 pass on `main`, because the daemon and database calls already discard their output
and their reasons are in the fixed list. They carry `# pinned:`. The new test 3 cases (no
healthcheck) pass on `main` too.

I traced revision 3 against `9dae8cd` by reading:
- every reason it can print is in the fixed list;
- `wait_health` reads health answers and never logs them. On the body that is not UTF-8,
  `fetch_health` raises, and `up` ends with `part=api container=SERVING reason=unexpected failure`,
  after all seven answers were read;
- a database without a healthcheck ends in `did not become healthy`, with no number;
- Docker output that is not UTF-8 raises `UnicodeDecodeError` in `run()`. The catch-all turns it
  into `unexpected failure`, the same as the other cases of its group;
- the catch-all is `except Exception`, so `CanaryFault` ends in `unexpected failure` in every
  phase. A start that raises still releases the lock (`sync lock released`).

I could not run the tests in this sandbox, so the gate's run is the authority. If a case looks
wrong against this contract, report it on the card. Never edit the tests.

## History

- Revision 3 (the adversarial check caught 0 of 4 mutants on `9dae8cd`) added:
  - test 6 (health answers);
  - test 7 (exceptions of any type in every phase);
  - the fixed reason list;
  - distinctive values for every numeric setting;
  - the no-healthcheck cases;
  - the non-UTF-8 cases;
  - the late-Docker and lock-wait G1 cases;
  - the plain-number `elapsed_s` rule.
- Revision 2 (the adversarial check failed on `945d64b`) added:
  - the number rule;
  - the install-path check;
  - the code-location check;
  - the one-output-per-group rule;
  - new G1 and G2 paths;
  - more canaries.
- Revision 1 was the first contract.
