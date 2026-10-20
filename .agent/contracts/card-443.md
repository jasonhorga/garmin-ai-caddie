# Card #443 — Bring the production stack back after a host reboot (database first)

After a host reboot the production stack must come back by itself, database
first, with nobody touching it. Restart policies cannot do this. A clean exit
and a failed exit behave in opposite ways, and nothing orders the containers.
So `ops/agenthub_deploy.py` gets an idempotent `up` action, and a systemd user
unit runs it at boot.

Touches: `ops/agenthub_deploy.py`, `ops/systemd/aicaddie-stack-up.service`, `docs/operations/runbook.md`, `tests/test_agenthub_deploy.py`, `tests/acceptance/test_card_443_stack_up.py`, `.agent/contracts/card-443.md`

Acceptance tests: `tests/acceptance/test_card_443_stack_up.py` (20 tests). They
use a fake `docker` and a fake `curl` on `PATH`, with no real containers and no
network. Most tests run `ops/agenthub_deploy.py` as a subprocess. Two of them
run a standalone copy of the script installed at the unit's path under a
temporary home directory, with that home as the working directory.

Risk: `ops/agenthub_deploy.py` is a pinned deploy file. State
"re-pin required: ops/agenthub_deploy.py" in the PR body. After the merge, its
release fails with `deploy pin mismatch` until the console reviews the diff and
re-pins the hash. That is expected. The console also installs the copy and the
unit.

## Revision 2: acceptance hardened after the adversarial gate

The gate's adversarial check failed on head `763bad1`. The 13 revision-1 tests
were too weak: an implementation could pass them and still break the interface
below. Revision 2 keeps the design and the interface, and closes these holes:

- **Each wait must use its own timeout.** Revision 1 only required failures to
  finish within 60 s. A wait that used another timeout, a fixed constant, or
  barely waited at all could still pass. The tests now set the other timeouts
  to 600 s. A failing wait must last at least its own short timeout (0.5 s)
  and end within 3.5 s after it. In the success cases the event comes after
  5 s: the daemon answers, or the database reports `healthy`. No fixed
  constant passes both.
- **API selection is tested against decoys.** Each decoy is a stopped
  container that breaks exactly one rule: wrong volume, wrong network, wrong
  port, no revision label, a short revision, or no release prefix. Each
  stopped later than the live release. The two valid older releases come first
  and last in list, name and Id order. One of them stopped in the same second
  as the live release, with no fraction (Docker trims trailing zeros), so
  `FinishedAt` must be compared as a time, not as a string.
- **The database is the configured container, by exact name.** A container
  whose name only contains the database name does not count, for `up` or for
  `deploy`. When `AICADDIE_DB_CONTAINER` is set, `up` starts that container
  even while the default-named one is healthy.
- **`part=` follows the phase, not the words of the reason.** A foreign
  container on the API port whose name contains "database" gives `part=api`.
  SIGTERM while `up` waits for the daemon gives `part=docker`; SIGTERM while
  it waits for the database gives `part=database`. With the default timeouts
  `up` is still waiting after 2.5 s.
- **`up` is done once the API reports its revision.** The fake daemon
  disappears right after that health answer. `up` must still exit 0 with the
  ok line. No output ever contains a traceback, which would carry the
  script's install path.
- **`deploy` and `rollback` check the database again under the sync lock.**
  The test holds the lock while the script waits for it, takes the database
  down, and then releases the lock. The script must refuse and leave the
  previous container untouched. A check made only before the image build and
  the lock wait, which can take minutes, used to pass.
- **Smaller holes:**
  - `AGENTHUB_DEPLOY_SHA` must not affect `up`.
  - A running API that does not report its revision is not stopped or
    restarted.
  - The standalone copy runs with the home directory as working directory,
    like a user unit.
  - A `TimeoutStartSec` must not cut `up` short.
  - The runbook's sandbox drill must name `AICADDIE_DB_CONTAINER` with a
    healthcheck.

Head `763bad1` has three defects these tests expose. This is the
implementation work still needed:

1. `main()` derives `part=` from substrings of the reason (`"docker daemon"`,
   `"database"`). Track the phase instead: `docker` until the daemon answers,
   `database` until the database is healthy, `api` after that. Signals and
   unexpected exceptions get the part of the phase they happen in.
2. The `result=ok action=up` line calls `list_containers()` again, outside the
   `try`. A Docker failure there prints a traceback, including the script's
   path, and exits 1 although the stack was confirmed healthy. `up()` should
   return the revision it checked, and `main()` should print the line from
   that value.
3. `deploy` and `rollback` call `wait_database(cfg, start=False)` only before
   the image build and the lock. Call it again under the sync lock, before the
   decision to switch (`switch` or `verify_live`) and before the rollback's
   `docker stop`. The early check can stay as a fail-fast.

From reading the code, everything else in revision 2 already passes on
`763bad1`. Codex must not edit `tests/acceptance/`. All 20 tests fail on
`main`: `up`, the unit file, the runbook section and the database check do
not exist there. I could not run Python in the contract sandbox (shell
commands were denied), so these results come from reading the code, not from
running it.

## Interfaces

### CLI

```
ops/agenthub_deploy.py deploy <40-lowercase-hex-sha>
ops/agenthub_deploy.py rollback <40-lowercase-hex-sha>
ops/agenthub_deploy.py up
```

- `up` takes no argument. `up <anything>` is a usage error (exit 2).
  `AGENTHUB_DEPLOY_SHA` does not apply to `up`: with it set to any value,
  `up` runs normally.
- The usage line becomes exactly
  `usage: agenthub_deploy.py {deploy|rollback} <40-lowercase-hex-sha> | up`
  and is printed to stderr.
- `up` must work from a standalone copy of the file, with no other repository
  file beside it, at `%h/.local/lib/aicaddie/agenthub_deploy.py`. The working
  directory is the home directory, as for a user unit. It must not need the
  gate script, the sync build script, `XDG_RUNTIME_DIR` or a `.git`.

### New environment variables

`Config` parses these like the existing ones. A bad value is a `ConfigError`:
exit 2, the variable name on stderr, and no `docker` call at all.

| Variable | Meaning | Default |
|---|---|---|
| `AICADDIE_DB_CONTAINER` | Name of the database container. Must match the existing `PREFIX_PATTERN` (a valid container name) | `garmin-ai-caddie-db-1` |
| `AICADDIE_DB_READY_TIMEOUT_SECONDS` | How long to wait for the database's Docker health status to become `healthy` | `180` |
| `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS` | How long `up` retries while the Docker daemon is not reachable | `300` |

Every wait polls at `AICADDIE_DEPLOY_POLL_SECONDS` and uses only its own
timeout:

- the daemon wait uses `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS`;
- the database wait uses `AICADDIE_DB_READY_TIMEOUT_SECONDS`;
- the local API health wait keeps `AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS`
  (the existing `wait_health`).

The defaults are production values; the review checks them.

### Database container state

- The database is the container whose name is exactly `AICADDIE_DB_CONTAINER`.
  A container whose name only contains that name (`<db>-restore-test`,
  `old-<db>`) is a different container.
- The container is missing when `docker inspect <name>` fails with
  "No such object", or when no container of that exact name exists.
- It is running when `.State.Running` is true.
- It is healthy only when it is running **and** `.State.Health.Status` is
  `healthy`. When it is not running, a stale `healthy` from before the stop
  does not count. A container without a healthcheck (no `.State.Health`)
  never counts as healthy: that fails closed. The production container has a
  `pg_isready` healthcheck, like the compose `db` service.
- A database that is `starting` or `unhealthy` is waited for until
  `AICADDIE_DB_READY_TIMEOUT_SECONDS` expires, because Docker's `unhealthy`
  can recover. On a database without a healthcheck, `up` may give up at once.

### `up` result lines (stdout, existing `log()` prefix)

- Success, as the final line:
  `agenthub-deploy: result=ok action=up database=<db-name> container=<api-name> revision=<sha> elapsed_s=<n>`
- Failure, as the final line:
  `agenthub-deploy: result=failed action=up part=<docker|database|api> elapsed_s=<n> reason=<text>`
- `part=` is the phase `up` was in when it failed. It never depends on the
  words in the reason.
  - `docker`: from the start until the daemon has answered.
  - `database`: from then until the database is healthy. This covers the
    lookup, the start and the wait, including Docker errors and signals in
    this phase.
  - `api`: everything after the database is healthy, including API
    selection, start and health.
- Once `wait_health` confirms the selected container's revision, `up` makes
  no further `docker` call. The ok line uses the database name, container and
  revision it already holds.
- SIGTERM, SIGINT or SIGHUP (systemd stopping the unit) ends `up` with exit 1
  and the failed line, with the part of the current phase.
- No exception escapes `main()`. An unexpected one becomes the failed line
  with the part of its phase. No output contains a traceback.
- Every `docker start` that `up` issues is logged first as
  `starting <container-name>`.
- Log lines carry only names, revisions and reasons. They never contain
  environment values, configured paths or URLs, or the script's own path.

Exit codes for `up`: `0` when the stack is healthy, `1` when it is not (the
`part=` names which part failed), `2` on a usage or configuration error.

### Systemd unit `ops/systemd/aicaddie-stack-up.service`

The file must contain exactly these lines. Comments (`#` or `;`) and blank
lines may be added.

```
[Unit]
Description=<non-empty text>
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 %h/.local/lib/aicaddie/agenthub_deploy.py up
[Install]
WantedBy=default.target
```

Only these other keys are allowed:
- `[Unit]`: `Documentation`, `After`, `Wants`;
- `[Service]`: `TimeoutStartSec`, `RemainAfterExit`, `SyslogIdentifier`.

The file has exactly one `ExecStart=`, and no `Environment`,
`EnvironmentFile`, `WorkingDirectory` or `ExecStart*Pre/Post` lines. The
script's production defaults are the configuration.

A oneshot unit has no start timeout by default. `TimeoutStartSec`, if
present, appears once. It is `infinity`, `0`, or at least 660 s, which is the
sum of the default waits (300 + 180 + 180 s). It is written as `<n>`,
`<n>s`, `<n>min` or `<n>h`.

## Goals

### G1 — `up` brings the live stack up, database first, idempotently

Pass conditions:

1. **Docker daemon.** Before anything else, `up` waits for the Docker daemon.
   - While the daemon is not reachable (any `docker` call fails, for example
     `docker info`), `up` retries every poll interval, up to
     `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS`.
   - A daemon that answers only after 5 s still leads to success.
   - Once the timeout expires: exit 1 with `part=docker`, and no
     `docker start`. With a 0.5 s timeout this takes at least 0.5 s and less
     than 4 s, while the other timeouts are 600 s.
2. **Database.**
   - Missing: exit 1 with `part=database` and the container's exact name in
     the result line. There is no `docker start`, `run`, `create`, `pull`,
     `rm`, `update`, `rename`, `restart`, `kill` or `compose`. A similarly
     named container (running and healthy or not) is neither used nor
     touched.
   - Not running: `docker start <db>`, then wait for `healthy`.
   - Running: wait for `healthy` (a database that reports healthy only after
     5 s is waited for), and never stop or restart it.
   - Not healthy within `AICADDIE_DB_READY_TIMEOUT_SECONDS`: exit 1 with
     `part=database`, and the API container is not started. With a 0.5 s
     timeout, a database that is `starting` or `unhealthy` takes at least
     0.5 s and less than 4 s.
   - The database container's configuration (`Config`, `HostConfig`,
     `Mounts`, image, id) is never changed. `AICADDIE_DB_CONTAINER` picks the
     name, also when a default-named container exists and is healthy.
3. **API selection.**
   - If a container is running and publishes the port, select it with
     `find_current`. Its existing fail-closed rules apply: a non-release
     container on the port, or several release containers on it, end in exit
     1 with `part=api` and the container names in the reason.
   - Otherwise select the stopped release container with the latest
     `FinishedAt`, compared as a time (Docker trims trailing zeros of the
     fraction; the existing `_finished_key`).
   - The selected container must:
     - have a name with the release prefix;
     - carry a 40-lowercase-hex `ai.caddie.source-revision` label;
     - publish the configured port;
     - pass `assert_layout` (exactly the configured volume at
       `/var/lib/ai-caddie`, read-write, on the configured network).

     A newer container that fails any of these rules is skipped.
     `previous_release` without the sha exclusion is fine.
   - Name, Id or list order never decide.
   - No candidate: exit 1 with `part=api`.
   - Older stopped releases are never started.
4. **API start.** Only after the database is healthy: if the selected
   container is not running, `docker start` it. Never `docker run` a new one,
   and never stop or restart a running one. Then wait with
   `wait_health(local_health_url, <its revision>, …)`. If it does not report
   that revision: exit 1 with `part=api`. With a 0.5 s health timeout this
   takes at least 0.5 s and less than 4 s. The container is left running.
5. **Nothing to change.** When the database is running and healthy and the API
   is running, `up` issues no `docker start` (or any other mutating command).
   It checks local health for the running revision and exits 0.
6. **Phases and the end.**
   - `part=` follows the phase (see "`up` result lines"). A foreign container
     on the API port whose name contains "database" gives `part=api`.
   - SIGTERM while waiting for the daemon gives `part=docker`. SIGTERM while
     waiting for the database gives `part=database`. Both exit 1, and the API
     is not started.
   - With the default timeouts, `up` is still waiting after 2.5 s.
   - After the health answer `up` needs no Docker: if the daemon disappears
     then, `up` still exits 0 with the ok line.
7. Usage and configuration errors exit 2 without calling `docker`. The usage
   text names `up`. `AGENTHUB_DEPLOY_SHA` does not change `up`.

Recommended, not tested:
- Take the existing `SyncLock` around the API start, so `up` cannot race a
  concurrent `deploy` or `rollback`.
- If `docker start` of the selected API container fails, log it and still
  wait for health, as `restore_previous` does. A container in Docker's
  restart backoff can come up by itself.

### G2 — `deploy` and `rollback` require a healthy database before touching containers

Pass conditions:

1. `deploy <sha>` and `rollback <sha>` check that the database container
   (exact name) exists, is running and is `healthy`.
   - The check that decides runs **under the sync lock**: after the lock is
     taken, before `switch` or `verify_live` (the already-live path of
     `deploy`, whose failure handling can stop containers), and before the
     rollback's `docker stop`.
   - An earlier fail-fast check before the image build may stay, but it does
     not replace the check under the lock. A database that goes down while
     the script waits for the lock (a sync is running) must be noticed.
   - Each check may wait up to `AICADDIE_DB_READY_TIMEOUT_SECONDS`.
     `deploy` and `rollback` never start the database themselves.
2. If the check fails: exit 1, the existing
   `result=failed … previous_untouched=true … reason=…` line with the database
   container's exact name in it, and no `docker stop`, `start`, `run` or
   `rm`. The current container keeps running. A missing database with a
   similarly named healthy container is a failed check.
3. With a healthy database, `rollback` (and `deploy`) behave as before.
   - The unit tests in `tests/test_agenthub_deploy.py` must stay green: add a
     running, healthy database container to `production_fixture()` and teach
     their fake `docker` about `.State.Health`.
   - Change their exact command-set assertions only as far as the new
     `inspect` of the database requires. Do not weaken anything else.
4. `docs/operations/runbook.md` says that `deploy` and `rollback` refuse to
   run without a healthy database, including the check under the lock. The
   "Sandbox drill" section names `AICADDIE_DB_CONTAINER` and a disposable
   container with a healthcheck.

### G3 — A systemd user unit runs `up` at boot from the installed copy; the runbook explains it

Pass conditions:

1. `ops/systemd/aicaddie-stack-up.service` matches the "Systemd unit"
   interface above exactly, including the `TimeoutStartSec` rule.
2. The unit's `ExecStart` works. With `%h` expanded to a home directory that
   is also the working directory, and the script installed there at
   `.local/lib/aicaddie/agenthub_deploy.py`, it brings a stopped database and
   an exited API back and exits 0. The test replaces only the interpreter with
   the test runtime.
3. `docs/operations/runbook.md` has a `## Boot recovery` (or `###`) section
   that mentions:
   - `ops/systemd/aicaddie-stack-up.service` and `agenthub_deploy.py up`;
   - the install location `.local/lib/aicaddie/agenthub_deploy.py`, a pinned
     copy rather than a checkout;
   - `systemctl --user` (enable the unit);
   - `loginctl enable-linger`, without which a user unit does not start at
     boot;
   - `journalctl --user -u aicaddie-stack-up` (read its journal).

   The section runs to the next heading of the same or a higher level. Lines
   in fenced code blocks are not headings. The runbook also documents the
   three new variables, for example in the existing Environment table.

### G4 — Public repository hygiene: no host paths or values

Pass conditions:

1. `up` prints no environment values, configured paths or URLs, temporary
   directories or install paths, and no traceback. The tests put canary
   strings in all of them and check the output of every run.
2. The unit file and the runbook name only the `%h/.local/lib/aicaddie/`
   install path (`~/.local/lib/aicaddie/` in shell examples is the same path).
   They name no home directory, user name, host name or private data path.
   The tests check exact unit lines instead of searching for forbidden
   strings.

## Out of scope (review-checked)

- Do not change `docker-compose.yml`, the database container's restart
  policy, any image, `Dockerfile*`, or app code (`server_v2/`, `ai_caddie/`,
  `web_v2/`, `mobile/`).
- Do not change the other pinned files (`ops/build_sync_image.sh`,
  `ops/complete_homeserver_api_deploy.sh`, the TestFlight files).
- Codex does not edit `tests/acceptance/`.
- In `tests/test_agenthub_deploy.py`, `running_names()` now hides every
  running container outside the release prefix. Narrow it so that it hides
  only the database container. A wrongly started foreign container must stay
  visible to those tests.
