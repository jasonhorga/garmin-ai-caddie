# Card #443 — Bring the production stack back after a host reboot (database first)

After a host reboot the production stack must come back by itself, database
first, with nobody touching it. Restart policies cannot do this. A clean exit
and a failed exit behave in opposite ways, and nothing orders the containers.
So `ops/agenthub_deploy.py` gets an idempotent `up` action, and a systemd user
unit runs it at boot.

Touches: `ops/agenthub_deploy.py`, `ops/systemd/aicaddie-stack-up.service`, `docs/operations/runbook.md`, `tests/test_agenthub_deploy.py`, `tests/acceptance/test_card_443_stack_up.py`, `.agent/contracts/card-443.md`

Acceptance tests: `tests/acceptance/test_card_443_stack_up.py` (23 tests). They
use a fake `docker` and a fake `curl` on `PATH`, with no real containers and no
network. Most tests run `ops/agenthub_deploy.py` as a subprocess. Two of them
run a standalone copy of the script installed at the unit's path under a
temporary home directory, with that home as the working directory. One test
runs the script's `__main__` on a virtual clock (see "Waits and the clock").

Risk: `ops/agenthub_deploy.py` is a pinned deploy file. State
"re-pin required: ops/agenthub_deploy.py" in the PR body. After the merge, its
release fails with `deploy pin mismatch` until the console reviews the diff and
re-pins the hash. That is expected. The console also installs the copy and the
unit.

## Revision 3: what the revision-2 tests still let through

The gate's adversarial check failed again, this time on head `f0460ed`
(revision 2, CI green). The contract sandbox could not read the gate report. So
I went through the head and the 20 revision-2 tests as the adversary would,
looking for changes to the head that break this contract and still pass every
test. Revision 3 keeps the design and the interface and closes these holes:

- **Production defaults.** Only "still waiting after 2.5 s" was tested. A
  default of 30 s instead of 300 or 180 passed, and so did capping a wait at
  30 s. Now one test leaves all three timeouts at their defaults and runs the
  script on a virtual clock. Each failing wait must sleep at least its default
  (300, 180, 180 s) and at most one poll interval more.
- **Poll interval.** The same test sets `AICADDIE_DEPLOY_POLL_SECONDS=3`, which
  is not the production 2 s. Every sleep in a wait must be exactly 3 s; only
  the last may be shorter. A fixed 2 s sleep used to pass.
- **Healthy means `status` is `ok` and the revision is the container's own.**
  Accepting any 40-hex revision, or ignoring `status`, used to pass. New cases:
  the API answers another release's revision, or `status: degraded` with its
  own revision. Both must end in `part=api`.
- **The API health is polled.** The started API now answers `booting` for 5 s
  and reports its revision only after that. A single check that then slept out
  the timeout used to pass.
- **Under the lock: the already-live path and an unhealthy database.** The
  re-check under the sync lock is now also tested before `verify_live` (deploy
  of the revision that already serves) and with a database that turns
  `unhealthy` while still running. A check placed only in the switch branch,
  or one that only looks at `running`, used to pass.
- **Every deploy and rollback path checks the database.** New cases: a
  bootstrap deploy (nothing serves), a rollback with nothing serving, and a
  database without a healthcheck. A control case shows that with a healthy
  database `deploy` passes both checks and starts the switch.
- **Failures inside the database phase.** If the daemon disappears after its
  first answer, or `docker inspect` prints something unreadable, the result
  must be `part=database` with no traceback. Passing unexpected exceptions on
  to `main()`, which reports `part=api`, used to pass.
- **SIGTERM in the API phase** gives `part=api`, and the API is left running.
- **Several running release containers on the port** give `part=api`, with
  both names in the reason, and nothing more is started.
- **A missing database is final.** `up` reports it without waiting out the
  database timeout, because nothing will create it.
- **`AICADDIE_DB_CONTAINER=-db`** is a configuration error (exit 2). Docker
  would read that name as an option.
- **Runbook.** The section must name the enable command
  (`systemctl --user enable`) and the unit directory (`.config/systemd/user`).
  The Environment table must list each new variable with its production
  default. The deploy "Contract" section must state the database requirement.

From reading the code, head `f0460ed` passes all 23 tests. **No code change is
expected.** Codex merges this branch unchanged and runs the tests. If a new case
fails on the head, check the case against this contract first. Fix the script
or the runbook only where they break the contract. If the case itself is
wrong, report it on the card. Never edit `tests/acceptance/`.

One documentation item is checked in review only. The runbook's database
paragraph in "Contract" should say that `deploy` and `rollback` repeat the
check under the sync lock (G2.4). It currently says only "first require".

All 23 tests fail on `main`. There, `up` is a usage error, the unit and the
runbook section do not exist, and `deploy` and `rollback` do not check the
database. I could not run Python in the contract sandbox (shell commands were
denied), so these results come from reading the code, not from running it.

### Changes that stay uncaught

Each change below either behaves the same in every run this contract defines,
or is allowed by it:

- **A default within one poll interval of 300 or 180 s** (for example 301 or
  299). The virtual-clock test uses 3-s polls, which is as fine as it can
  measure.
- **A second `docker start` of a database that stops again during the wait.**
  No test models a database that exits after its start, and the contract does
  not forbid it.
- **Dropping the early fail-fast database check** in `deploy` or `rollback`.
  It is optional; the check under the lock is the one that decides.
- **Logging `starting <name>` just after the `docker start`** instead of just
  before it. The tests see the log and the call, but not their relative order.
- **Taking `SyncLock` in `up`, or not.** It is recommended, not required.
- **How the daemon is probed** (`docker info`, `docker version` or `docker ps`)
  and how many calls one attempt makes.
- **Whether a Docker error in the database phase ends `up` at once** or is
  retried until the database timeout. Both are allowed; the part is `database`
  either way.
- **Checking `assert_layout` on a running API container too.** The selection
  rules below pick among stopped containers. `up` never stops or restarts a
  running one, and it only waits for its health.

If the gate reports a survivor that is not on this list, it should name it. I
will then either pin the behaviour it changes or record it here as equivalent.

### History

Revision 2 (the adversarial check failed on `763bad1`) required:
- each wait to use its own timeout (the other timeouts are 600 s);
- API selection to hold against decoys, with `FinishedAt` compared as a time;
- the database to be matched by exact name, `AICADDIE_DB_CONTAINER` included;
- `part=` to come from the phase, not from the words of the reason, including
  for SIGTERM;
- no Docker call after the health answer, and no traceback;
- the database to be re-checked under the sync lock;
- the standalone copy to run with the home directory as working directory;
- `TimeoutStartSec`, if present, not to cut `up` short.

Codex then fixed the phase tracking, the ok line and the check under the lock
(`5d29212`).

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
| `AICADDIE_DB_CONTAINER` | Name of the database container. Must match the existing `PREFIX_PATTERN` (a valid container name; it never starts with `-`) | `garmin-ai-caddie-db-1` |
| `AICADDIE_DB_READY_TIMEOUT_SECONDS` | How long to wait for the database's Docker health status to become `healthy` | `180` |
| `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS` | How long `up` retries while the Docker daemon is not reachable | `300` |

### Waits and the clock

There are three waits. Each one uses only its own timeout:

- the daemon wait uses `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS`;
- the database wait uses `AICADDIE_DB_READY_TIMEOUT_SECONDS`;
- the local API health wait keeps `AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS`
  (the existing `wait_health`).

Every wait follows the same rules:

- It measures time with `time.monotonic()` (`time.time()` also works).
- Between attempts it pauses with `time.sleep(AICADDIE_DEPLOY_POLL_SECONDS)`.
  Only the last pause may be shorter, for example `min(poll, remaining)`.
- When a wait fails, it has slept at least its timeout in total, and at most
  one poll interval more.

One test runs `python -c <runner> ops/agenthub_deploy.py <record> up`. The
runner replaces `time.monotonic`, `time.time` and `time.sleep` with a virtual
clock, so sleeping advances the clock at once. It then runs the script with
`runpy.run_path(..., run_name="__main__")` and records every sleep. The waits
must therefore use these functions of the `time` module. Calling `time.sleep`
at call time or binding it with `from time import sleep` both work. Other
timers, such as `threading.Event.wait`, `select` or `signal.alarm`, do not.

### Database container state

- The database is the container whose name is exactly `AICADDIE_DB_CONTAINER`.
  A container whose name only contains that name (`<db>-restore-test`,
  `old-<db>`) is a different container.
- The container is missing when `docker inspect <name>` fails with
  "No such object", or when no container of that exact name exists. Missing
  is final: `up` reports it at the first look and does not wait for the
  container to appear.
- It is running when `.State.Running` is true.
- It is healthy only when it is running **and** `.State.Health.Status` is
  `healthy`. When it is not running, a stale `healthy` from before the stop
  does not count. A container without a healthcheck (no `.State.Health`)
  never counts as healthy: that fails closed. The production container has a
  `pg_isready` healthcheck, like the compose `db` service.
- A database that is `starting` or `unhealthy` is waited for until
  `AICADDIE_DB_READY_TIMEOUT_SECONDS` expires, because Docker's `unhealthy`
  can recover. On a database without a healthcheck, `up` may give up at once.

### Local API health

The API is healthy when local `/api/v2/health` answers JSON with `status` equal
to `ok` and `revision` equal to the selected container's
`ai.caddie.source-revision` label. The existing `wait_health` already checks
exactly this. An answer that names another revision, even a valid 40-hex one,
or another status, does not count.

### `up` result lines (stdout, existing `log()` prefix)

- Success, as the final line:
  `agenthub-deploy: result=ok action=up database=<db-name> container=<api-name> revision=<sha> elapsed_s=<n>`
- Failure, as the final line:
  `agenthub-deploy: result=failed action=up part=<docker|database|api> elapsed_s=<n> reason=<text>`
- `part=` is the phase `up` was in when it failed. It never depends on the
  words in the reason.
  - `docker`: from the start until the daemon has answered.
  - `database`: from then until the database is healthy. This covers the
    lookup, the start and the wait. It includes Docker errors (the daemon
    going away again), unexpected exceptions (for example unreadable
    `docker inspect` output) and signals in this phase.
  - `api`: everything after the database is healthy, including API
    selection, start and health.
- Once `wait_health` confirms the selected container's revision, `up` makes
  no further `docker` call. The ok line uses the database name, container and
  revision it already holds.
- SIGTERM, SIGINT or SIGHUP (systemd stopping the unit) ends `up` with exit 1
  and the failed line, with the part of the current phase. A started API is
  left running.
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
     the result line, in less than 3.5 s even with a 600 s database timeout.
     There is no `docker start`, `run`, `create`, `pull`, `rm`, `update`,
     `rename`, `restart`, `kill` or `compose`. A similarly named container
     (running and healthy or not) is neither used nor touched.
   - Not running: `docker start <db>`, then wait for `healthy`.
   - Running: wait for `healthy` (a database that reports healthy only after
     5 s is waited for), and never stop or restart it.
   - Not healthy within `AICADDIE_DB_READY_TIMEOUT_SECONDS`: exit 1 with
     `part=database`, and the API container is not started. With a 0.5 s
     timeout, a database that is `starting` or `unhealthy` takes at least
     0.5 s and less than 4 s.
   - A Docker error or an unexpected exception in this phase: exit 1 with
     `part=database`, no traceback, nothing started. With a 0.5 s database
     timeout this ends in less than 4 s.
   - The database container's configuration (`Config`, `HostConfig`,
     `Mounts`, image, id) is never changed. `AICADDIE_DB_CONTAINER` picks the
     name, also when a default-named container exists and is healthy.
3. **API selection.**
   - If a container is running and publishes the port, select it with
     `find_current`. Its existing fail-closed rules apply: a non-release
     container on the port, or several release containers on it, end in exit
     1 with `part=api` and the container names in the reason.
   - Otherwise select, among the stopped containers, the release container
     with the latest `FinishedAt`, compared as a time (Docker trims trailing
     zeros of the fraction; the existing `_finished_key`).
   - The selected stopped container must:
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
   and never stop or restart a running one. Then poll
   `wait_health(local_health_url, <its revision>, …)` (see "Local API
   health"). An API that answers `booting` for 5 s after its start and then
   reports its revision leads to success. If it does not report its revision
   with `status: ok` in time: exit 1 with `part=api`. That includes an answer
   with another release's revision, or with another status. With a 0.5 s
   health timeout this takes at least 0.5 s and less than 4 s. The container
   is left running.
5. **Nothing to change.** When the database is running and healthy and the API
   is running, `up` issues no `docker start` (or any other mutating command).
   It checks local health for the running revision and exits 0.
6. **Phases and the end.**
   - `part=` follows the phase (see "`up` result lines"). A foreign container
     on the API port whose name contains "database" gives `part=api`.
   - SIGTERM while waiting for the daemon gives `part=docker`. SIGTERM while
     waiting for the database gives `part=database`. In both cases `up` exits
     1 and the API is not started. SIGTERM while waiting for the started API's
     health gives `part=api`, exit 1, and the API is left running.
   - With the default timeouts, `up` is still waiting after 2.5 s.
   - After the health answer `up` needs no Docker: if the daemon disappears
     then, `up` still exits 0 with the ok line.
7. **Defaults and polling** (virtual clock, poll 3 s, the three timeouts
   unset). With the daemon never reachable, `up` fails with `part=docker`
   after sleeping 300–303 s in total. With a database that stays `starting`,
   it fails with `part=database` after 180–183 s. With a running API that
   never reports its revision, it fails with `part=api` after 180–183 s.
   Every sleep is 3 s, except that the last may be shorter. Nothing is
   started in these runs.
8. Usage and configuration errors exit 2 without calling `docker`. The usage
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
   - This holds on every path: a switch, a deploy of the revision that already
     serves, a bootstrap deploy (nothing serves, bootstrap env file set), and
     a rollback with nothing serving.
   - The check that decides runs **under the sync lock**: after the lock is
     taken, before `switch` or `verify_live` (the already-live path of
     `deploy`, whose failure handling can stop containers), and before the
     rollback's `docker stop`.
   - An earlier fail-fast check before the image build may stay, but it does
     not replace the check under the lock. A database that stops or turns
     `unhealthy` while the script waits for the lock (a sync is running) must
     be noticed.
   - Each check may wait up to `AICADDIE_DB_READY_TIMEOUT_SECONDS`.
     `deploy` and `rollback` never start the database themselves.
2. If the check fails: exit 1, the existing
   `result=failed … previous_untouched=true … reason=…` line with the database
   container's exact name in it, and no `docker stop`, `start`, `run` or
   `rm`. The release container that served keeps running, and no other
   release container runs. A missing database with a similarly named healthy
   container is a failed check, and so is a running database without a
   healthcheck.
3. With a healthy database, `rollback` and `deploy` behave as before.
   - A rollback succeeds.
   - A deploy passes both checks and starts the switch: it stops the current
     container. In the test, the fake `docker run` then fails and the previous
     container is restored (`previous_restored=true`).
   - The unit tests in `tests/test_agenthub_deploy.py` must stay green: add a
     running, healthy database container to `production_fixture()` and teach
     their fake `docker` about `.State.Health`.
   - Change their exact command-set assertions only as far as the new
     `inspect` of the database requires. Do not weaken anything else.
4. `docs/operations/runbook.md` says, in the deploy "Contract" section, that
   `deploy` and `rollback` refuse to run without a healthy
   `AICADDIE_DB_CONTAINER`. It should also say that the check is repeated
   under the sync lock (review-checked). The "Sandbox drill" section names
   `AICADDIE_DB_CONTAINER` and a disposable container with a healthcheck.

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
   - the unit directory `.config/systemd/user`;
   - `systemctl --user enable` (enable the unit);
   - `loginctl enable-linger`, without which a user unit does not start at
     boot;
   - `journalctl --user -u aicaddie-stack-up` (read its journal).

   The section runs to the next heading of the same or a higher level. Lines
   in fenced code blocks are not headings.
4. The runbook's Environment table has one row per new variable, in the form
   `` | `<VARIABLE>` | <meaning> | `<default>` | ``, with the defaults
   `garmin-ai-caddie-db-1`, `180` and `300`.

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
- In `tests/test_agenthub_deploy.py`, `running_names()` hides only the
  database container, so that a wrongly started foreign container stays
  visible to those tests (done in `f0460ed`).
