# Card #447 — `up` starts the database first, then the serving release

On 2026-10-19 the host rebooted and production was down 4h20m. The database container had exited
cleanly, so its `on-failure` restart policy did not bring it back. The API then used up its
`on-failure:3` restarts waiting for the database. Restart policies cannot order containers. This
card adds one idempotent action, `ops/agenthub_deploy.py up`, that brings the stack back in order:
the Docker daemon, then the database, then the release container that was serving.

Touches: `ops/agenthub_deploy.py`, `tests/test_agenthub_deploy.py`, `tests/acceptance/test_card_447_up_order.py`, `.agent/contracts/card-447.md`

Acceptance tests (Claude-owned; Codex must not edit `tests/acceptance/`):
`tests/acceptance/test_card_447_up_order.py` (13 tests). Every test runs the real script as a
subprocess, with fake `docker` and `curl` executables first on `PATH`. No real containers are used.

PR body: `ops/agenthub_deploy.py` is a pinned release file. Write
"re-pin required: ops/agenthub_deploy.py". After the merge the console reviews the diff and
re-pins it.

## Interface

### Invocation

```
ops/agenthub_deploy.py up
```

- `up` takes no other argument. `up <anything>` is a usage error: exit 2, a `usage:` line on
  stderr, and no `docker` call.
- The usage text names `up` as a word, for example
  `usage: agenthub_deploy.py {deploy|rollback} <40-lowercase-hex-sha> | up`.
- `deploy` and `rollback` behave exactly as they do today. Their existing tests in
  `tests/test_agenthub_deploy.py` must keep passing unchanged.
- `up` does not read `AGENTHUB_DEPLOY_SHA`. This is not tested.

### Configuration

`up` reads the existing `Config`, so the existing validation still gives exit 2. It also reads:

| Variable | Default | Meaning |
|---|---|---|
| `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS` | `300` | how long to retry until the Docker daemon answers |
| `AICADDIE_DB_READY_TIMEOUT_SECONDS` | `180` | how long to wait for the database's Docker health to be `healthy` |
| `AICADDIE_DB_CONTAINER` | `garmin-ai-caddie-db-1` | the exact name of the database container |

- **Timeouts.** Parse them like the existing `_float`: empty means the default, and `0` is
  allowed. A non-number, a negative value or `nan` is a configuration error:
  - exit 2;
  - a message on stderr that **names the variable**;
  - **no `docker` call at all**.
- **Poll interval.** Every `up` wait (daemon, database, API health) polls every
  `AICADDIE_DEPLOY_POLL_SECONDS`. The tests set it to `0.05`.
- **Existing settings.** The API health wait uses the existing `AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS`.
  The lock uses the existing `AICADDIE_SYNC_LOCK` and `AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS`
  through the existing `SyncLock`.

### Order of work

1. **Docker daemon.** Run a cheap read (`docker info` or `docker version`) until it succeeds.
   Stop after `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS`; then exit 1 with `part=docker`. Nothing is
   started before the daemon answers.
2. **Database.** Read the container named exactly `AICADDIE_DB_CONTAINER` with
   `docker inspect <name>`.
   - **Missing:** exit 1, `part=database`, and nothing is started. A container whose name only
     contains the configured name (`<name>-old`, `old-<name>`) is not the database. Never
     `docker run`, `create` or recreate it.
   - **Not running:** `docker start <name>`. A failed start is exit 1, `part=database`.
   - **Running, or just started:** poll `.State.Health.Status` until it is `healthy`.
     - Wait at most `AICADDIE_DB_READY_TIMEOUT_SECONDS`. If it is not healthy in time: exit 1,
       `part=database`, and the API is not started.
     - The health value of a **stopped** container does not count. Start the container first.
   - Never stop, restart, remove, update or reconfigure the database.
3. **API.**
   - **A release container is running on `AICADDIE_API_PORT`:** find it with the existing
     `find_current`. Its fail-closed rules apply: a non-release container on the port, or more
     than one release container on it, is exit 1 with `part=api`. Start nothing. Only run the
     existing `wait_health(local_health_url, <its revision>, ...)`.
   - **Otherwise:** pick the stopped container whose name starts with the release prefix, has the
     latest `FinishedAt` by the existing `_finished_key` (numeric fraction), and passes the
     existing `assert_layout`. Skip candidates that fail `assert_layout`. Never pick a container
     without the release prefix.
     - Start it with `docker start` only after the database is `healthy`.
     - Start it only while holding `SyncLock`.
     - If the lock is not acquired in time: exit 1, `part=api`, and the API is not started.
     - Then run `wait_health` for that container's revision label. If it fails: exit 1, `part=api`.
       Do not remove the container afterwards.
     - Never `docker run` a new container.
     - **No candidate:** exit 1, `part=api`, `container=none`.
   - `up` runs none of these: the deployment gate, the sync contract check, the public health
     check, or cleanup.
4. **Idempotent.** When the database is running and `healthy` and a release container runs on the
   port, `up` only reads: no `docker start`. Exit 0 if that container's health reports its
   revision.

Whether `SyncLock` is taken before or after the database health wait is free. It is never taken
before the database is started: a sync holding the lock must not delay the database start.

### Docker commands

`up` uses only these commands. The fake implements exactly them, and every other subcommand fails
the test:
- `docker info` or `docker version`, optionally with `--format`/`-f`;
- `docker ps` with `-a`, `-q`, `--no-trunc`, `--format` or `--filter`;
- `docker inspect` with `--format`/`-f`, `--type container` or `-s`, and one or more names or ids;
- `docker image inspect`;
- `docker start <name>`.

Never use `run`, `create`, `stop`, `restart`, `rm`, `kill`, `update`, `rename`, `exec`, `compose`
or the `docker container ...` spellings.

`--format` templates may use only field actions: `{{.A.B}}`, `{{json .A.B}}`, `{{json .}}`,
`{{index .A "key"}}`. The fake rejects `{{if}}`, `{{range}}` and other control actions. To read a
health value that may be absent, use `{{json .State}}`, or a plain `docker inspect` (a JSON
array).

### Result line and exit codes

The last outcome is exactly **one** stdout line that starts with `agenthub-deploy: result=`,
printed through the existing `log()`:

```
agenthub-deploy: result=ok action=up container=<api container> [revision=<rev>] [elapsed_s=<s>] ...
agenthub-deploy: result=failed action=up part=<docker|database|api> container=<name|none> [elapsed_s=<s>] ... reason=<text>
```

- `reason=` comes last; everything after it is free text. All `key=value` tokens before it are
  single words.
- **`container` on failure:**
  - `part=docker`: `none`;
  - `part=database`: the configured database name;
  - `part=api`: the API container that was checked or started, or `none` when none was selected.
    In the lock-timeout and foreign-port cases the tests do not check it.
- **Exit codes:**
  - `0`: the stack is healthy;
  - `1`: some part is not healthy;
  - `2`: usage or configuration error, with no `docker` call.

  `up` never exits 3.
- **Output hygiene.** As for deploy, nothing prints environment values, the lock path or URLs, and
  there is no traceback. The tests put canaries in the containers' `Env`, the lock path, the sync
  script path and the public URL.

## Goals and pass conditions

### G1 — `up` waits for the Docker daemon

1. `test_docker_daemon_reachable_late_still_brings_the_stack_up`: the first 4 `docker` calls fail
   with "Cannot connect to the Docker daemon". `up` keeps retrying, then:
   - starts the database and then `SERVING`;
   - exits 0 with `container=SERVING`.
2. `test_unreachable_docker_daemon_exits_1_part_docker`: the daemon never answers and the timeout
   is `0.5`. The result is exit 1, `part=docker`, `container=none`, with:
   - at least two attempts;
   - nothing started;
   - a finish within 30 s.

### G2 — The database comes first and is never changed

3. `test_reboot_starts_database_first_then_serving_release` (database stopped with a stale
   `healthy` value; the release exited):
   - the starts are exactly `[db, SERVING]`, in that order;
   - when the API started, the database was running and `healthy`.
4. `test_unhealthy_database_never_starts_the_api`: the database never becomes healthy (timeout
   `0.6`), or its `docker start` fails. Either way the result is exit 1, `part=database`,
   `container=<db>`, and no API start.
5. `test_missing_database_is_never_created`: covers the default name missing next to look-alike
   names, and a custom `AICADDIE_DB_CONTAINER` missing while the default-named one exists. Each
   case gives:
   - exit 1, `part=database`, `container=<configured name>`;
   - no `start`;
   - nothing running;
   - no `run`/`create`.
6. `test_partially_running_stack_starts_only_what_is_stopped`:
   - a running but `starting` database is not started again; the API waits for `healthy`;
   - a stopped database next to a running release starts only the database.

### G3 — The serving release starts under the sync lock and is health-checked for its revision

7. `test_reboot_starts_database_first_then_serving_release`:
   - the API start happened while the sync lock was held;
   - local health was read after the start and reported `SERVING`'s revision;
   - the older release stays stopped;
   - the lock is free afterwards.
8. `test_newest_valid_stopped_release_is_started`: `.1Z` beats `Z` in the same second, so the
   ordering is numeric, not lexical. A newer release with the wrong volume and one with the wrong
   network are skipped, and so is a newer non-release container on the port. Only `cccccccc` is
   started.
9. `test_sync_lock_delays_the_api_start_not_the_database_start`: while the test holds the lock:
   - the database is started;
   - `up` waits and starts no API.

   After the lock is released, the API is started (its start time is after the release) and `up`
   exits 0.
10. `test_held_sync_lock_times_out_without_starting_the_api`: lock timeout `0.5` gives exit 1,
    `part=api`, and no API start. The database start is allowed.
11. `test_api_health_is_checked_for_the_started_release_revision`: each case below gives exit 1,
    `part=api`, `container=SERVING`:
    - health reports another revision;
    - health reports `booting`;
    - a running release reports another revision. Nothing is started in this case.
12. `test_no_api_candidate_or_foreign_port_owner_exits_1_part_api`: each case gives exit 1,
    `part=api`, and no release start:
    - no release container at all, which also gives `container=none`;
    - a running non-release container on the port.

### G4 — A healthy stack is only read

13. `test_running_and_healthy_stack_is_only_read`: no `start` call, exit 0 with
    `container=SERVING`, health read for `SERVING`'s revision, and no state change.
14. Re-running `up` after test 3's recovery makes no `start` call and exits 0.
15. Test 6's running-database case does not start the database again.

### G5 — Exit codes, the result line, and configuration errors

16. Every `up` run in the tests checks:
    - exactly one `result=` line with `action=up`;
    - `part`/`container` as listed above;
    - the exit code;
    - only the allowed `docker` commands;
    - no canary or traceback in the output;
    - no sync-script run and no public-URL request.
17. `test_usage_and_configuration_errors_exit_2_without_docker`:
    - `up <x>` is exit 2 with a usage line that names `up`;
    - `soon`, `-1`, `-0.5` or `nan` in either new timeout is exit 2 and names the variable;
    - a bad `AICADDIE_API_PORT` is exit 2;
    - none of these makes a `docker` call.

## Not covered (later cards, do not add here)

- Refusing a tie among equally new releases, validating the revision label, re-selecting under the
  lock.
- Redacting Docker output or env values, signal handling.
- The deploy/rollback database guard, the systemd unit and the runbook.
- No change to `docker-compose.yml`, images, the database's restart policy or app code.
- Prior art: `codex/card-443-stack-up` (PR #444, closed). Reuse code where it fits; this contract
  decides.

## Gate notes

- On `main`, `up` is a usage error (exit 2, no `result=` line), so every test fails. The usage test
  fails on the `up` word in the usage text and the variable names.
- I could not run the tests in this sandbox, because shell commands are refused. I checked them by
  reading them against `main`'s script. The gate's run is the authority. If a case looks wrong
  against this contract, report it on the card. Never edit the tests.
