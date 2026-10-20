# Card #447 — `up` starts the database first, then the serving release

On 2026-10-19 the host rebooted and production was down 4h20m. The database container had exited
cleanly, so its `on-failure` restart policy did not bring it back. The API then used up its
`on-failure:3` restarts waiting for the database. Restart policies cannot order containers. This
card adds one idempotent action, `ops/agenthub_deploy.py up`, that brings the stack back in order:
the Docker daemon, then the database, then the release container that was serving.

Touches: `ops/agenthub_deploy.py`, `tests/test_agenthub_deploy.py`, `tests/acceptance/test_card_447_up_order.py`, `.agent/contracts/card-447.md`

Acceptance tests (Claude-owned; Codex must not edit `tests/acceptance/`):
`tests/acceptance/test_card_447_up_order.py` (14 tests). Every test runs the real script as a
subprocess, with fake `docker` and `curl` executables first on `PATH`. No real containers are used.

PR body: `ops/agenthub_deploy.py` is a pinned release file. Write
"re-pin required: ops/agenthub_deploy.py". After the merge the console reviews the diff and
re-pins it.

## Revision 3: acceptance hardened after the adversarial gate

The gate's adversarial check failed on head `a3208f3`. I could not read the gate report, so I
reviewed the head against the revision-2 tests and found two kinds of gap.

**Structural.** Five tests used `self.subTest`. A failing subTest does not fail the test function
itself, so the gate did not credit those cases, for example the configuration errors, the health
cases and the fail-closed cases. Every multi-case test now uses a `_case` context manager instead,
and a failing case fails the whole test function.

**Behavioural.** These wrong variants of `up` passed revision 2 and are caught now:
- **Waits counted in attempts, not time.** The daemon is now down for 2.5 s, not 4 calls. The
  database turns healthy 1.5 s after its start in the reboot test, and 1 s late in the
  running-but-`starting` case. The daemon and database timeout cases also require the retries to
  span most of the timeout.
- **One timeout used for another wait.** In the timeout cases every other wait is 60 s, so the run
  must end within 15 s:
  - the daemon wait;
  - the database wait;
  - the sync lock wait;
  - the API health wait.
- **Defaults of 0, or empty values rejected.** The reboot and late-daemon tests run with both new
  timeouts unset, so they use the defaults. The healthy-stack test also runs with both set to `0`
  and with both set to empty.
- **Database:**
  - a container without a Docker healthcheck counted as healthy;
  - a running database that reports `unhealthy` treated as final instead of waited for;
  - a failed `docker start` ignored or retried;
  - a start attempted on a missing name;
  - `AICADDIE_DB_CONTAINER` used for only some of the steps (new positive test with a custom
    name).
- **API selection:** ordering by name, id or listing order instead of `FinishedAt`. A newer
  candidate with a read-only mount, and a newer one that does not publish the configured port, are
  also skipped now.
- **API failure paths:**
  - a failed API start that falls back to another candidate, or goes on to read health;
  - the fail-closed and no-candidate cases reading the local health anyway;
  - a start attempted despite a foreign container on the port. Start attempts are now counted
    from the `docker start` calls, failed ones included, not only successful starts.
- The fake now treats a container as the database by its compose service label `db`, not by
  whether it has a health value.

**No implementation change is expected.** From reading the code, head `a3208f3` already meets every
revision-3 condition. Every new pass condition below is marked **(rev 3)**, and each one states what
that head does. CI's `backend` job, which runs `tests/acceptance`, was green on that head for
revision 2. If a revision-3 case fails on the head, check the case against this contract first, and
fix `ops/agenthub_deploy.py` only where it breaks the contract. If the case itself is wrong, report
it on the card. Never edit the tests.

Some changes stay uncaught on purpose. They behave the same in every case this contract defines:
- `docker version` instead of `docker info` for the daemon check.
- Taking `SyncLock` before or after the database health wait (never before the database start).
  Holding it through the API health wait.
- Extra read calls (`ps`, `inspect`, `image inspect`).
- The text after `reason=`, except that a lock timeout names the "sync lock". Optional
  `revision=`/`elapsed_s=` fields.
- The poll interval of one wait, as long as each wait still runs for its own timeout.
- Treating every database inspect error as "missing".
- Validating the revision label of the candidates. This card leaves that out; it is a later card.

If the gate reports a survivor that is not on this list, it should name it. I will then either pin
the behaviour it changes or record it here as equivalent.

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

- **Timeouts.** Parse them like the existing `_float`.
  - Unset or empty means the default.
  - `0` is allowed and means one attempt. **(rev 3)** The existing `wait_health` works the same
    way.
  - A non-number, a negative value or `nan` is a configuration error:
    - exit 2;
    - a message on stderr that **names the variable**;
    - **no `docker` call at all**.
- **Every timeout is a time, not an attempt count, and governs only its own wait. (rev 3)** Each
  wait keeps retrying until its own timeout has passed, whatever the other timeouts are.
- **Poll interval.** Every `up` wait (daemon, database, API health) polls every
  `AICADDIE_DEPLOY_POLL_SECONDS`. The tests set it to `0.05`.
- **Existing settings.**
  - The API health wait uses the existing `AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS`.
  - The lock uses the existing `AICADDIE_SYNC_LOCK` and `AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS`,
    through the existing `SyncLock`.

### Order of work

1. **Docker daemon.** Run a cheap read (`docker info` or `docker version`) until it succeeds.
   Stop after `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS`; then exit 1 with `part=docker`. Nothing is
   started before the daemon answers.
2. **Database.** Read the container named exactly `AICADDIE_DB_CONTAINER` with
   `docker inspect <name>`. That name is used for every database step: the read, the start and the
   health wait.
   - **Missing:**
     - exit 1, `part=database`;
     - **no `docker start` call at all (rev 3)**, so nothing is started.

     A container whose name only contains the configured name (`<name>-old`, `old-<name>`) is
     not the database. Never `docker run`, `create` or recreate it.
   - **Not running:** `docker start <name>`, **once (rev 3)**. A failed start is exit 1,
     `part=database`, **at once (rev 3)**: no second start, and no waiting out the timeout.
   - **Running, or just started:** poll `.State.Health.Status` until it is `healthy`.
     - Wait at most `AICADDIE_DB_READY_TIMEOUT_SECONDS`. If it is not healthy in time: exit 1,
       `part=database`, and the API is not started.
     - The health value of a **stopped** container does not count. Start the container first.
     - **(rev 3)** `starting` and `unhealthy` are both "not yet"; keep polling until the timeout.
       A container without a Docker healthcheck (no `State.Health`) never becomes healthy.
   - Never stop, restart, remove, update or reconfigure the database.
3. **API.**
   - **A release container is running on `AICADDIE_API_PORT`:** find it with the existing
     `find_current`. Start nothing. Only run the existing
     `wait_health(local_health_url, <its revision>, ...)`.
   - **`find_current` fails closed:** a non-release container is running on the port, or more than
     one release container is. The result is exit 1 with `part=api`. **(rev 3)** `up` stops there:
     it starts no release container and reads no local health.
   - **Otherwise, pick a candidate.** Take the stopped containers that:
     - have a name starting with the release prefix;
     - **publish `AICADDIE_API_PORT` (rev 3)**. A container that does not publish the port cannot
       have been serving it, and starting it would only fail the health check.

     Pick the one with the latest `FinishedAt` by the existing `_finished_key` (numeric fraction)
     that passes the existing `assert_layout`, and skip candidates that fail it. Neither the name,
     the id nor the listing order decides. Never pick a container without the release prefix.
     - Start it with `docker start` only after the database is `healthy`.
     - Start it only while holding `SyncLock`.
     - If the lock is not acquired in time: exit 1, `part=api`, and the API is not started.
     - **(rev 3)** If its `docker start` fails: exit 1, `part=api`, `container=<that name>`, at
       once. Do not read health, and do not try another candidate.
     - Then run `wait_health` for that container's revision label. If it fails: exit 1, `part=api`.
       Do not remove the container afterwards.
     - Never `docker run` a new container.
   - **No candidate:** exit 1, `part=api`, `container=none`. **(rev 3)** No local health read.
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
health value that may be absent, use `{{json .State}}`, `{{json .State.Health}}`, or a plain
`docker inspect` (a JSON array).

The fake moves the database's health forward only when an `inspect` names the database (by name
or id). It treats a container as the database when its compose service label is `db`.

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
    In the lock-timeout and fail-closed cases the tests do not check it.
- **Exit codes:**
  - `0`: the stack is healthy;
  - `1`: some part is not healthy;
  - `2`: usage or configuration error, with no `docker` call.

  `up` never exits 3.
- **Output hygiene.** As for deploy, nothing prints environment values, the lock path or URLs, and
  there is no traceback. The tests put canaries in the containers' `Env`, the lock path, the sync
  script path and the public URL.

## Goals and pass conditions

"Start calls" below means every `docker start` the script asked for, failed ones included, in
order. "Quick" means the run ended within 15 s while every wait other than the one under test was
60 s.

### G1 — `up` waits for the Docker daemon

1. `test_docker_daemon_reachable_late_still_brings_the_stack_up`: every `docker` call fails with
   "Cannot connect to the Docker daemon" for the first 2.5 s. **(rev 3)** Both new timeouts are
   unset, so their defaults apply. `up` keeps retrying, then:
   - at least two calls were refused;
   - it starts the database and then `SERVING`, after the outage;
   - it exits 0 with `container=SERVING`.
2. `test_unreachable_docker_daemon_exits_1_part_docker`: the daemon never answers and its timeout
   is `1`. The result is exit 1, `part=docker`, `container=none`, with:
   - at least two attempts, **spanning at least 0.6 s (rev 3)**;
   - a quick finish **(rev 3)**;
   - no start call, and nothing running.

### G2 — The database comes first and is never changed

3. `test_reboot_starts_database_first_then_serving_release`: the database is stopped with a stale
   `healthy` value, and the release has exited. **(rev 3)** The database turns healthy 1.5 s after
   its start, and both new timeouts use their defaults.
   - the start calls and the starts are exactly `[db, SERVING]`, in that order;
   - when the API started, the database was running and `healthy`, **at least 1.5 s after the
     database start (rev 3)**;
   - afterwards exactly the database and `SERVING` are running. This is a set check: the test
     compares the sorted names with `sorted([db, SERVING])`. Only the starts list checks order.
4. `test_unhealthy_database_never_starts_the_api`. Each case gives exit 1, `part=database`,
   `container=<db>`, no API start and a quick finish:
   - the database is started but stays `starting` (timeout `1`): start calls `[db]`, and the
     retries span at least 0.5 s;
   - **(rev 3)** the database has no healthcheck (timeout `1`): start calls `[db]`, and the retries
     span at least 0.5 s;
   - **(rev 3)** the database runs and stays `unhealthy` (timeout `1`): no start call, and the
     retries span at least 0.5 s;
   - its `docker start` fails (timeout `60`): exactly one start call `[db]`, and the run ends at
     once.
5. `test_missing_database_is_never_created`. There are two cases: the default name is missing next
   to look-alike names, and a custom `AICADDIE_DB_CONTAINER` is missing while the default-named one
   exists. Each case gives:
   - exit 1, `part=database`, `container=<configured name>`;
   - **no start call (rev 3)**, and no start;
   - nothing running;
   - no `run`/`create`.
6. **(rev 3)** `test_configured_database_name_is_the_one_started`. `AICADDIE_DB_CONTAINER=drill-db-1`
   is set, and both `drill-db-1` and the default-named database are stopped. Then:
   - the start calls are `[drill-db-1, SERVING]`;
   - `drill-db-1` was `healthy` when the API started;
   - the default-named database stays stopped;
   - the run exits 0.
7. `test_partially_running_stack_starts_only_what_is_stopped`:
   - a running database that is `starting`, and turns healthy only after 1 s, is not started
     again. The start calls are `[SERVING]`, and the API starts after `healthy`;
   - **(rev 3)** a running database that reports `unhealthy` for a few inspects is waited for in
     the same way;
   - a stopped database next to a running release: the start calls are `[db]` only.

### G3 — The serving release starts under the sync lock and is health-checked for its revision

8. `test_reboot_starts_database_first_then_serving_release`:
   - the API start happened while the sync lock was held;
   - local health was read after the start and reported `SERVING`'s revision;
   - the older release stays stopped;
   - the lock is free afterwards.
9. `test_newest_valid_stopped_release_is_started`: the start calls are exactly
   `[db, cccccccc]`. The fixture requires:
   - `.1Z` beats `Z` in the same second, so the ordering is numeric, not lexical;
   - newer releases are skipped when they have the wrong volume, the wrong network, a
     **read-only mount (rev 3)**, or **publish another port (rev 3)**;
   - a newer non-release container is skipped too;
   - **(rev 3)** a valid but older release, with the highest name and the highest id, listed last,
     is not chosen.
10. `test_sync_lock_delays_the_api_start_not_the_database_start`: while the test holds the lock:
    - the database is started;
    - `up` waits and starts no API.

    After the lock is released, the API is started (its start time is after the release) and `up`
    exits 0.
11. `test_held_sync_lock_times_out_without_starting_the_api`: lock timeout `0.5`. The result is
    exit 1, `part=api`, start calls `[db]`, no API start, and the reason names the "sync lock". The
    run is **quick (rev 3)**.
12. `test_api_health_is_checked_for_the_started_release_revision`, with health timeout `0.5`. Each
    case below gives exit 1, `part=api`, `container=SERVING` and a **quick (rev 3)** finish:
    - health reports another revision: start calls `[db, SERVING]`, health read;
    - health reports `booting`: start calls `[db, SERVING]`, health read;
    - a running release reports another revision: no start call, health read;
    - **(rev 3)** `SERVING`'s `docker start` fails: start calls `[db, SERVING]`, no other
      candidate, and no health read.
13. `test_no_api_candidate_or_foreign_port_owner_exits_1_part_api`. Each case gives exit 1,
    `part=api`, start calls `[db]` (no release container) and **no local health read (rev 3)**:
    - no release container at all, which also gives `container=none`;
    - a running non-release container on the port;
    - **(rev 3)** two release containers running on the port.

### G4 — A healthy stack is only read

14. `test_running_and_healthy_stack_is_only_read`: no `start` call, exit 0 with
    `container=SERVING`, health read for `SERVING`'s revision, and no state change. **(rev 3)** The
    same holds when both new timeouts are `0`, and when both are empty.
15. Re-running `up` after test 3's recovery makes no `start` call and exits 0. The same two
    containers are still running.
16. Test 7's running-database cases do not start the database again.

### G5 — Exit codes, the result line, and configuration errors

17. Every `up` run in the tests checks:
    - exactly one `result=` line with `action=up`;
    - `part`/`container` as listed above;
    - the exit code;
    - only the allowed `docker` commands;
    - no canary or traceback in the output;
    - no sync-script run and no public-URL request.
18. `test_usage_and_configuration_errors_exit_2_without_docker`:
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
- Multi-case tests use `_case`, not `subTest`, so a failing case fails its test function.
- Shell access in this sandbox was limited to `git`; running Python was refused. I checked the
  revision-3 tests by reading them against `main` and against head `a3208f3`'s script. The gate's
  run is the authority. If a case looks wrong against this contract, report it on the card. Never
  edit the tests.

## Revisions

- **Revision 3** (adversarial gate on `a3208f3`): see the section at the top. One new test
  (`test_configured_database_name_is_the_one_started`), new cases inside existing tests, and
  `_case` instead of `subTest`. The interface is unchanged. The added pass conditions are marked
  **(rev 3)**, and the head already meets them.
- **Revision 2:** Codex reported a test bug. `running()` returns the running container names
  sorted, so the two running-container checks in
  `test_reboot_starts_database_first_then_serving_release` could never equal `[db, SERVING]`:
  `aicaddie-release-…` sorts before `garmin-ai-caddie-db-1`. Both checks now compare with
  `sorted([db, SERVING])`. The ordered check on the starts list (`[db, SERVING]`) is unchanged.
