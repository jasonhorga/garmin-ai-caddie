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
- `elapsed_s` and other numbers the script computes itself.

### What `up` never prints

`up` never prints any of these, on stdout or stderr, in any outcome:
- **Environment values.** That covers every variable except the container names above, for example
  tokens, `DOCKER_HOST`, the configured volume (`AICADDIE_PRIVATE_VOLUME`) and network
  (`AICADDIE_DEPLOY_NETWORK`).
- **Configured paths, URLs and the port.** That covers:
  - the sync lock, the sync script, the bootstrap env file and the public health URL;
  - the local health URL and `127.0.0.1`;
  - the configured `AICADDIE_API_PORT`.
- **Temporary directories and install paths.** That covers `HOME`, `TMPDIR`, `XDG_RUNTIME_DIR`
  and the checkout path.
- **Container data:** a container's `Env` and its mount sources.
- **Docker's own stdout and stderr**, from every `docker` call, failing ones included. That output
  can name the daemon socket, the config file, the data root or the host name. The same holds for
  curl's error text, which echoes the URL.
- **A traceback**, or Python's `File "…"` lines.

The existing `DeployError` messages that `up` prints already follow these rules. A new message
must too.

### Unexpected exceptions

An exception that is not a `DeployError` and is raised in any phase (`docker`, `database`, `api`)
gives one result:
- exit 1;
- one result line, `result=failed action=up part=<that phase>`;
- `container=` as in #447: `none` for `docker`, the configured database name for `database`;
- a **fixed** ` reason=` text.

A fixed reason does not depend on the exception. It contains neither the exception's type name
(`FileNotFoundError`, `JSONDecodeError` …) nor its message (`[Errno 2] No such file or
directory: …`, `Expecting value …`), and no traceback follows. Today `up` prints
`unexpected <TypeName>`. That is no longer allowed.

For example, each of these is such a case, or may be turned into a `DeployError` with a fixed
message:
- `docker` is missing or not executable;
- `docker inspect` prints something that is not JSON, or JSON of another shape;
- the sync lock cannot be opened.

## Goals and pass conditions

**Hygiene.** Every run in every test passes these checks on stdout and on stderr:
- no line contains `canary` (case-insensitive), the temporary directory or the checkout path;
- no line contains `47913` (the configured port), `127.0.0.1`, `/api/v2/health`, `unix://` or
  `docker.sock`;
- no `Traceback` and no `File "` line;
- `docker` is called only with `info`, `version`, `ps`, `inspect`, `image inspect` and `start`;
- no sync script run and no public health request.

**Canaries.** Every value the script can see carries the word `canary`, except container names and
revisions:
- the environment: `HOME`, `TMPDIR`, `XDG_RUNTIME_DIR`, `DOCKER_HOST`, `DOCKER_CONFIG`, an admin
  token, the lock path, the sync script, the bootstrap env file, the public URL, the volume and the
  network;
- the containers' `Env` and mount sources;
- the fake `docker`'s stderr on every call, failing ones included. It names a config file, the
  daemon socket, the data root and the host name;
- the fake `docker info` stdout;
- the fake `curl`'s stderr, which also echoes the local URL with the port.

**Start calls** means every `docker start` the script asked for, failed ones included.

### G1 — A successful `up` prints no host values

1. `test_successful_up_prints_no_host_values`:
   - After a reboot: the database and `SERVING` are stopped. The result is exit 0,
     `container=SERVING`, start calls `[db, SERVING]`, and health read for its revision.
   - The stack is already healthy: exit 0, `container=SERVING`, no start call.

   Both runs pass the hygiene checks.

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
   - a sync holds the lock (lock timeout 0.5 s), with no start call.

Every run passes the hygiene checks. Tests 2 and 3 already pass on `main` and pin that behaviour.

### G3 — An unexpected exception ends in its phase's `part=` and a fixed reason

5. `test_unexpected_errors_end_with_the_phase_and_a_fixed_reason`. Each case gives:
   - exit 1 with the expected `part=` (and `container=` where it is fixed);
   - the hygiene checks pass;
   - neither stream matches `\b[A-Za-z]*(Error|Exception)\b`, `Errno`, `No such file`,
     `Permission denied`, `Expecting value`, `line <n> column` or `Traceback`.

   | Case | `part` | Also |
   |---|---|---|
   | `docker` is not on `PATH` | `docker`, `container=none` | |
   | `docker` is not executable | `docker`, `container=none` | |
   | the database inspect prints no JSON | `database`, `container=<db>` | `SERVING` not started |
   | the database inspect prints a JSON list | `database`, `container=<db>` | `SERVING` not started |
   | the release containers' inspect prints no JSON | `api` | no start call |
   | the sync lock's directory is missing | `api` | no start call |

   The docker and database timeouts are 0.5 s in these cases, so an implementation that keeps
   retrying still ends quickly.

## Free choices (not tested)

- How Docker's output is kept out: captured, discarded, or sent to `DEVNULL`. It must never be
  forwarded.
- The wording of every `reason=`, as long as it is fixed text plus names and revisions. A lock
  timeout still names the "sync lock" (#447).
- Whether malformed Docker output is a `DeployError` with its own fixed message, or falls through
  to the generic unexpected-exception reason.
- Whether a missing or non-executable `docker` is retried until the docker timeout or fails at
  once. Either way it is `part=docker`.
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
`unexpected <TypeName>`, for example `unexpected FileNotFoundError`.

I could not run Python in this sandbox, so I checked the tests by reading them against `main`'s
script. The gate's run is the authority. If a case looks wrong against this contract, report it on
the card. Never edit the tests.
