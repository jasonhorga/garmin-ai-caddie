# Card #449 — `up` output carries no host values

`ops/agenthub_deploy.py up` runs from a systemd unit at boot, so its output lands in the journal. It
also lands in the test logs of this public repository. This card makes sure that output never
contains a host value, in every outcome. It also makes an unexpected exception end in a fixed
reason, never the exception text. Split from #443 (its G4.1). Depends on #448 (merged).

Touches: `ops/agenthub_deploy.py`, `tests/test_agenthub_deploy.py`,
`tests/acceptance/test_card_449_up_redaction.py`, `.agent/contracts/card-449.md`

Acceptance tests (Claude-owned; Codex must not edit `tests/acceptance/`):
`tests/acceptance/test_card_449_up_redaction.py` (5 tests). Every test runs the real script as a
subprocess. Fake `docker` and `curl` executables are the **only** entries on `PATH`, so no real
daemon can be reached. No real container is used.

PR body: `ops/agenthub_deploy.py` is a pinned release file. Write
"re-pin required: ops/agenthub_deploy.py".

## Revision 2

The gate's adversarial check failed on `945d64b`. I could not read its report, so this revision
closes every gap I found by reading the revision 1 tests against that head. Revision 1 missed these
mutants. Revision 2 catches them:
- a reason that still encodes the exception, just not as its CamelCase name: the name in lower case
  or without `Error`, `errno`, `strerror`, the module, a function name or a line number;
- a narrowed `except` (for example `OSError, ValueError, TypeError`), so a `KeyError` or an
  `AttributeError` escapes as a traceback;
- exception details on a log line before the result line;
- other numbers: a configured timeout, the poll interval, a container or image id, the Docker
  version, the process id;
- host values on paths revision 1 never ran:
  - a non-release container on the port;
  - two running releases;
  - a running release on another network or volume;
  - a tie;
  - a newer stopped release skipped for its layout;
- forwarding the stdout of `docker start`, or logging the database's health record, container
  labels or the health response body;
- the interpreter's install path, `USER`, `LOGNAME` or `HOSTNAME`.

As far as I can tell by reading, head `945d64b` passes revision 2 unchanged. I could not run the tests
in this sandbox. The gate's run is the authority.

## Interface

Only `up` changes. `deploy`, `rollback` and their helpers behave exactly as they do today, and their
tests in `tests/test_agenthub_deploy.py` keep passing unchanged. Everything in the #447 and #448
contracts still holds for `up`: the order of work, the timeouts, the selection rules, the Docker
command surface, the result line and the exit codes. The #447 and #448 acceptance tests must keep
passing.

### What `up` may print

Only these values may appear in `up`'s stdout or stderr:
- container names, including the configured database name and the release prefix as part of a name;
- revisions;
- fixed text written in the script;
- **(rev 2)** exactly two kinds of number:
  - the `elapsed_s` value;
  - a Docker exit code, written as `(exit <n>)`, as `run()` already does.

  No other number may appear: no timeout or other configured value, no container or image id, no
  Docker version, no process id and no line number.

### What `up` never prints

`up` never prints any of these, on stdout or stderr, in any outcome:
- **Environment values.** That covers every variable except the container names above. Examples:
  tokens, `DOCKER_HOST`, `USER`, `LOGNAME`, `HOSTNAME`, the configured volume
  (`AICADDIE_PRIVATE_VOLUME`) and network (`AICADDIE_DEPLOY_NETWORK`), and every timeout.
- **Configured paths, URLs and the port.** That covers:
  - the sync lock, the sync script, the bootstrap env file and the public health URL;
  - the local health URL and `127.0.0.1`;
  - the configured `AICADDIE_API_PORT`.
- **Temporary directories and install paths.** That covers `HOME`, `TMPDIR`, `XDG_RUNTIME_DIR`, the
  checkout path and **(rev 2)** the interpreter's path and prefixes.
- **Container data:** a container's `Env`, its mount sources, **(rev 2)** its labels other than the
  revision, its network and volume names, and the database's health record (`State.Health`, with its
  log).
- **Docker's own stdout and stderr**, from every `docker` call, failing ones included. That output
  can name the daemon socket, the config file, the data root or the host name. **(rev 2)** That
  includes the stdout of `docker start` and of `docker info`. The same holds for curl's error text,
  which echoes the URL, and **(rev 2)** for the health response body beyond `status` and `revision`.
- **A traceback**, or Python's `File "…"` lines.

The existing `DeployError` messages that `up` prints already follow these rules. A new message
must too.

### Unexpected exceptions

An exception that is not a `DeployError` and is raised in any phase (`docker`, `database`, `api`)
gives one result:
- exit 1;
- one result line, `result=failed action=up part=<that phase>`;
- `container=` as in #447: `none` for `docker`, the configured database name for `database`, and
  `none` for `api` while no release has been selected;
- a **fixed** ` reason=` text.

A fixed reason does not depend on the exception. It contains none of these:
- the exception's type name, in any spelling: `FileNotFoundError`, `filenotfounderror`,
  `FileNotFound`, the module;
- its message (`[Errno 2] No such file or directory: …`, `Expecting value …`), its `errno` or
  `strerror`;
- where it was raised: a function name, a file, a line number.

Once container names and revisions are removed, **(rev 2)** the reason holds no digit and no
snake_case or dunder identifier. No traceback follows. Today `up` prints `unexpected <TypeName>`.
That is no longer allowed.

**(rev 2) One failure, one output.** Each group below is a single failure, whichever exception its
cases raise. Every case of a group prints the same lines, on stdout and on stderr. The `elapsed_s`
value is ignored, and a repeated line counts once.

| Group | `part` | `container` | Cases (the exception each raises in `945d64b`) |
|---|---|---|---|
| `docker` cannot be run | `docker` | `none` | not on `PATH` (`FileNotFoundError`); not executable (`PermissionError`); no `#!` line (`OSError`, exec format error) |
| the database inspect is unreadable | `database` | `<db>` | no JSON (`JSONDecodeError`); a JSON list (`TypeError`); an object without `running` (`KeyError`); a `health` that is text (`AttributeError`) |
| the release listing is unreadable | `api` | `none` | no JSON; a JSON list; an object without `id`; a `name` that is a list |
| the sync lock cannot be opened | `api` | not checked | its directory is missing (`FileNotFoundError`); it is a directory (`IsADirectoryError`); its parent is a file (`NotADirectoryError`) |

A group may get its own `DeployError` with a fixed message instead of the generic reason. That
message then covers every case of the group. Reading unreadable output leniently, for example as
"not running" or "not healthy", gives a different output for some cases, so it fails.

## Goals and pass conditions

**Hygiene.** Every run in every test passes these checks on stdout and on stderr:
- no line contains `canary` (case-insensitive), the temporary directory or the checkout path;
- no line contains `47913` (the configured port), `127.0.0.1`, `/api/v2/health`, `unix://` or
  `docker.sock`;
- **(rev 2)** no line contains the interpreter's path or prefixes: `sys.executable`, its real path,
  `sys.prefix`, `sys.base_prefix` and `sys.exec_prefix`. Values shorter than 5 characters, such as
  `/usr`, are skipped;
- **(rev 2)** no line holds a digit once container names, revisions, `elapsed_s=<value>` and
  `(exit <n>)` are removed;
- no `Traceback` and no `File "` line;
- `docker` is called only with `info`, `version`, `ps`, `inspect`, `image inspect` and `start`;
- no sync script run and no public health request.

**Canaries.** Every value the script can see carries the word `canary`, except container names and
revisions:
- the environment: `HOME`, `TMPDIR`, `XDG_RUNTIME_DIR`, **(rev 2)** `USER`, `LOGNAME`, `HOSTNAME`,
  `DOCKER_HOST`, `DOCKER_CONFIG`, an admin token, the lock path, the sync script, the bootstrap env
  file, the public URL, the volume and the network;
- the containers' `Env` and mount sources. **(rev 2)** Also their labels: the compose working
  directory and config file, and a build-context label. And the database's health log;
- the fake `docker`'s stderr on every call, failing ones included. It names a config file, the
  daemon socket, the data root and the host name;
- the fake `docker info` stdout, and **(rev 2)** a line on the fake `docker start` stdout;
- the fake `curl`'s stderr, which also echoes the local URL with the port, and **(rev 2)** a `host`
  field in the health body.

**Start calls** means every `docker start` the script asked for, failed ones included.

### G1 — A successful `up` prints no host values

1. `test_successful_up_prints_no_host_values`:
   - After a reboot: the database and `SERVING` are stopped. The result is exit 0,
     `container=SERVING`, start calls `[db, SERVING]`, and health read for its revision.
   - The stack is already healthy: exit 0, `container=SERVING`, no start call.
   - **(rev 2)** A newer stopped release is on another volume and another network. It is skipped:
     exit 0, `container=SERVING`, start calls `[SERVING]`.

   Every run passes the hygiene checks.

### G2 — A failed `up` prints no host values, whatever part fails

2. `test_docker_failure_prints_no_host_values` (pinned). The daemon never answers: every call
   fails with "Cannot connect to the Docker daemon at unix:///…", and `info` also prints client
   details on stdout. With a docker timeout of 0.5 s the result is exit 1, `part=docker`,
   `container=none`, and no start call.
3. `test_database_failure_prints_no_host_values` (pinned). Each case gives exit 1,
   `part=database`, `container=garmin-ai-caddie-db-1`, and `SERVING` is not started:
   - the database is missing;
   - its `docker start` fails;
   - it stays `unhealthy` (database timeout 0.5 s).
4. `test_api_failure_prints_no_host_values`. Each case gives exit 1 and `part=api`:
   - `docker ps` fails;
   - `docker inspect` of the release containers fails;
   - there is no release container;
   - the API `docker start` fails;
   - the API health never answers (curl fails; health timeout 1 s);
   - the running release has no revision label;
   - **(rev 2)** a non-release container publishes the port;
   - **(rev 2)** two running releases publish the port;
   - **(rev 2)** the running release is on another network;
   - **(rev 2)** the running release mounts another volume;
   - **(rev 2)** the newest stopped releases tie;
   - a sync holds the lock (lock timeout 0.5 s), with no start call.

Every run passes the hygiene checks. Tests 2 and 3 already pass on `main` and pin that behaviour.

### G3 — An unexpected exception ends in its phase's `part=` and a fixed reason

5. `test_unexpected_errors_end_with_the_phase_and_a_fixed_reason`. It runs the four groups of the
   table above. Each case gives:
   - exit 1 with the group's `part=`, and its `container=` where the table fixes it;
   - the hygiene checks pass;
   - neither stream matches any of these:
     - `\b[A-Za-z]*(Error|Exception)\b`, `Errno`, `Traceback`, `\bline \d+`, `\.py\b`;
     - `No such file`, `Permission denied`, `Is a directory`, `Not a directory`, `Exec format`;
     - `Expecting value`, `has no attribute`, `not subscriptable`, `indices must be`;
   - once container names and revisions are removed, the reason holds no digit and no snake_case or
     dunder identifier;
   - no start call (`docker` and listing groups, the lock group), or `SERVING` not started
     (database group).

   **(rev 2)** Then, per group, every case printed the same lines as the group's first case.

   The docker and database timeouts are 0.5 s in these cases, so an implementation that keeps
   retrying still ends quickly.

## Free choices (not tested)

- How Docker's output is kept out: captured, discarded, or sent to `DEVNULL`. It must never be
  forwarded.
- The wording of every `reason=`, as long as it uses only the values `up` may print. A lock timeout
  still names the "sync lock" (#447).
- Whether a group of the G3 table becomes a `DeployError` with its own fixed message, or falls
  through to the generic unexpected-exception reason. Either way the whole group gives one output.
- Whether a `docker` that cannot be run is retried until the docker timeout or fails at once. Either
  way it is `part=docker`.
- Extra log lines before the result line, if they print only allowed values.

## Not covered (other cards; do not add here)

- Signal handling. That includes a signal that arrives while the result is printed.
- Configuration errors. They stay exit 2 with a message that names the variable, as today.
- `deploy` and `rollback` output.
- The systemd unit and the runbook.

## Gate notes

On `main` (`c24063c`), `up` passes `docker ps` stderr straight through: `list_containers` calls
`docker("ps", …, capture=True)` without `quiet=True`. Every run that reaches the API phase
therefore prints the fake Docker's canary diagnostics. That makes G1 and test 4 of G2 fail on
`main`. Tests 2 and 3 pass on `main`, because the daemon and database calls already discard their
output; they carry `# pinned:`. G3 fails on `main` because `up` reports
`unexpected <TypeName>`, for example `unexpected FileNotFoundError`. Revision 2 does not change
which tests fail on `main`.

Revision 2 traced every new case against `945d64b`:
- the new G2 cases end in `find_current`, `assert_layout` or the tie check, with messages that hold
  only names;
- every G3 case falls through to the fixed `unexpected failure`. In the lock group, the container is
  the selected `SERVING`;
- the new canaries reach only output that `945d64b` captures or discards.

I could not run the tests in this sandbox, so this trace is by reading only. The gate's run is the
authority. If a case looks wrong against this contract, report it on the card. Never edit the
tests.

## History

- Revision 2 (the adversarial check failed on `945d64b`) added the number rule, the install-path
  check, the code-location check, the one-output-per-group rule with the `KeyError`,
  `AttributeError`, exec-format, `IsADirectoryError` and `NotADirectoryError` cases, the
  new G1 and G2 paths, and canaries in labels, the health log, `docker start` stdout, the health
  body, `USER`, `LOGNAME` and `HOSTNAME`.
- Revision 1 was the first contract.
