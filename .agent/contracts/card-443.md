# Card #443 — Bring the production stack back after a host reboot (database first)

After a host reboot the production stack must come back by itself, database
first, with nobody touching it. Restart policies cannot do this. A clean exit
and a failed exit behave in opposite ways, and nothing orders the containers.
So `ops/agenthub_deploy.py` gets an idempotent `up` action, and a systemd user
unit runs it at boot.

Touches: `ops/agenthub_deploy.py`, `ops/systemd/aicaddie-stack-up.service`, `docs/operations/runbook.md`, `tests/test_agenthub_deploy.py`, `tests/acceptance/test_card_443_stack_up.py`, `.agent/contracts/card-443.md`

Acceptance tests: `tests/acceptance/test_card_443_stack_up.py` (30 tests). They
use a fake `docker` and a fake `curl` on `PATH`, with no real containers and no
network. Most tests run `ops/agenthub_deploy.py` as a subprocess, with its
stdout written to a file. Two of them run a standalone copy of the script
installed at the unit's path under a temporary home directory, with that home
as the working directory. One test runs the script's `__main__` on a virtual
clock (see "Waits and the clock").

Risk: `ops/agenthub_deploy.py` is a pinned deploy file. State
"re-pin required: ops/agenthub_deploy.py" in the PR body. After the merge, its
release fails with `deploy pin mismatch` until the console reviews the diff and
re-pins the hash. That is expected. The console also installs the copy and the
unit.

## Revision 5: what the revision-4 tests still let through

This job names the adversarial failure on head `6ea5220`. After revision 4,
Codex added two commits:

- `f7a0969`: `up` takes the sync lock before it starts a stopped API, selects
  the API again under the lock, and logs a failed `docker start` of the API
  and keeps waiting for its health.
- `6ea5220`: `docker ps` errors are no longer printed, and a tie for the
  newest stopped release is refused.

CI reports `backend` green on `6ea5220`, and that job runs the 25 revision-4
tests. The contract sandbox still cannot read the gate report or run Python.
So I read `6ea5220` against the revision-4 tests as the adversary would.
Reverting either Codex commit, or most single parts of them, passed every
test. Revision 5 pins that behaviour as contract. It also closes most of the
revision-4 list of "changes that stay uncaught":

- **Ties.** Two valid stopped releases with the same latest `FinishedAt`
  (compared as a time) end in `part=api` with both names. A tie with a
  container that fails a rule, or among older releases, is no tie.
- **Docker's own error text.** The fake docker now writes what the real one
  does: the daemon address from `DOCKER_HOST` when it refuses a connection,
  the daemon's data root when a start fails, and the port when a bind fails.
  `DOCKER_HOST` and the data root carry canaries. `up` must not pass Docker's
  error output on, for any call. The tests also take the daemon away after
  one or after two answers, so each read of the database phase is checked.
- **The sync lock in `up`.** `up` waits for the lock before it starts a
  stopped API. It does not start the API while the lock is busy. Under the
  lock it selects again, so a release that a deploy started meanwhile is the
  one it checks. A lock that stays busy gives `part=api`, and so does SIGTERM
  during the lock wait. Starting the database, or an API that already runs,
  never waits for the lock.
- **A failed `docker start` of the API.** It is logged, and `up` still waits
  for health. The test's container is in restart backoff and comes up by
  itself a second later.
- **A running API that is not a valid release.** A running release container
  on the port needs a 40-hex revision label and the configured layout.
  Otherwise the result is `part=api` with its name, and it keeps running.
  Revision 4 left this open.
- **`starting <name>` comes first.** At each `docker start` the fake docker
  reads the script's stdout file. The start must already be logged.
- **The database check comes first in `deploy` and `rollback`.** `deploy`
  refuses for the database before it builds images. `rollback` refuses for
  the database even when its target does not exist. Revision 4 let the early
  check be dropped.
- **Defaults.** A failed wait must sleep less than one poll interval more than
  its timeout. A default set slightly too high (for example 301 s) is now
  caught.
- **Unit timeout.** With the lock wait, the longest path of `up` is 300 + 180
  + 600 + 180 = 1260 s, so `TimeoutStartSec`, if present, is at least that.

From reading the code, head `6ea5220` passes all 30 tests. **No code change is
expected.** Codex merges this branch unchanged and runs the tests. If a case
fails on the head, check the case against this contract first. Fix the script
or the runbook only where they break the contract. If the case itself is
wrong, report it on the card. Never edit `tests/acceptance/`. Recommended
(review-checked): the runbook's "Boot recovery" section should say that `up`
waits for the sync lock before it starts a stopped API, and that it refuses a
tie.

All 30 tests fail on `main`. There, `up` is a usage error, the unit and the
runbook section do not exist, and `deploy` and `rollback` do not check the
database. I could not run Python in the contract sandbox (it denied the shell
command), so these results come from reading the code, not from running it.

### Changes that stay uncaught

Each change below either behaves the same in every run this contract defines,
or is allowed by it:

- **A default up to one poll interval below 300 or 180 s** (for example 298 or
  299 s). With 3-s polls these waits sleep exactly as long as with the right
  default. A higher default is caught.
- **A second `docker start` of the database**, after a failed start or after a
  database that stops again during the wait. The contract does not forbid it.
- **Whether a failed `docker start` of the database ends `up` at once** or is
  waited out until the database timeout. The part is `database` either way.
- **How the daemon is probed** (`docker info`, `docker version` or `docker ps`)
  and how many calls one attempt makes.
- **Whether a Docker error in the database phase ends `up` at once** or is
  retried until the database timeout. The part is `database` either way.
- **The phase boundary inside the round of calls that reports the database
  healthy.** A Docker error that arrives exactly between that answer and the
  first call of the API selection is not modelled.
- **Whether `up` keeps the sync lock while it waits for the started API's
  health**, or releases it after the start.
- **`shield_signals()` after the health answer in `up`.** It only matters for a
  signal that arrives between that answer and the ok line.
- **The words of a reason, where this contract does not say what the reason
  must contain.** For example, without the `api is None` checks, "no stopped
  release container" becomes "unexpected AttributeError". The part is still
  `api`.
- **The `not c.running` condition among the stopped candidates.** It applies
  only when no running container publishes the port, and every candidate
  publishes it. So no candidate is running anyway.

If the gate reports a survivor that is not on this list, it should name it. I
will then either pin the behaviour it changes or record it here as equivalent.

### History

Revision 4 (the adversarial check failed on `f0460ed`) required:
- that `up` only reads and starts, and that a refused `deploy` or `rollback`
  only reads;
- `part=database` when `docker start` of the database fails, even with the
  stale `healthy` from before the reboot;
- the sandbox drill's prefix, network, volume and database, with decoys that
  match only the production values;
- the whole layout rule for stopped releases: a read-only volume, a volume at
  another path, or a second mount;
- the database re-check under the sync lock for a bootstrap deploy, a rollback
  with nothing serving, and a rollback to the revision that already serves;
- `part=database` for SIGHUP and SIGINT during the database wait;
- no configured port or local health URL in the output of `up`, and no
  container environment;
- a unit without comment lines, with fixed value forms.

Codex then added the sync lock in `up` (`f7a0969`), quiet `docker ps` and the
tie refusal (`6ea5220`).

Revision 3 (the adversarial check failed on `f0460ed`) required:
- the production defaults (300, 180, 180 s) and the poll interval, measured
  on a virtual clock;
- `status: ok` and the container's own revision for API health, polled until
  the API reports it;
- the database re-check under the sync lock on the already-live path, and for
  a database that turns `unhealthy`;
- the database check on a bootstrap deploy, a rollback with nothing serving,
  and a database without a healthcheck, with a healthy-database control case;
- `part=database` for Docker errors and unexpected exceptions in that phase,
  and `part=api` for SIGTERM in the API phase and for several running release
  containers on the port;
- a missing database reported at once, and `AICADDIE_DB_CONTAINER=-db`
  refused;
- the runbook's enable command, unit directory, variable rows and database
  requirement.

Codex then added the running-API checks and the runbook sentence about the
check under the lock (`7ba57af`).

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

`up` also uses the existing `AICADDIE_SYNC_LOCK` and
`AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS` (default 600) for its lock wait.

### Waits and the clock

There are three waits that poll. Each one uses only its own timeout:

- the daemon wait uses `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS`;
- the database wait uses `AICADDIE_DB_READY_TIMEOUT_SECONDS`;
- the local API health wait keeps `AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS`
  (the existing `wait_health`).

Every one of these waits follows the same rules:

- It measures time with `time.monotonic()` (`time.time()` also works).
- Between attempts it pauses with `time.sleep(AICADDIE_DEPLOY_POLL_SECONDS)`.
  Only the last pause may be shorter, for example `min(poll, remaining)`.
- When a wait fails, it has slept at least its timeout in total, and less than
  one poll interval more. It gives up at the first check at or after its
  timeout.

The sync lock wait is the existing `SyncLock` wait, with
`AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS` and its own short pause. These rules do
not apply to it.

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
  - `api`: everything after the database is healthy. That includes API
    selection, the sync lock wait, the start and the health wait.
- Once `wait_health` confirms the selected container's revision, `up` makes
  no further `docker` call. The ok line uses the database name, container and
  revision it already holds.
- SIGTERM, SIGINT or SIGHUP (systemd stopping the unit) ends `up` with exit 1
  and the failed line, with the part of the current phase. A started API is
  left running.
- No exception escapes `main()`. An unexpected one becomes the failed line
  with the part of its phase. No output contains a traceback.
- Every `docker start` that `up` issues is logged as `starting <container-name>`
  before the call is made.
- A `docker start` of the API that fails is logged as a line that names the
  container and contains the word `failed` (not the result line).
- Log lines carry only names, revisions and reasons. They never contain
  environment values, configured paths or URLs, or the script's own path.
  That includes the configured port and the local health URL: say "the
  configured port", as `deploy` already does. `up` never prints a container's
  environment.

### Docker commands

- `up` uses only reads and `start`. The reads are `info`, `version`, `ps`,
  `inspect` (also as `container inspect`) and `image inspect`. Any other
  command is a change and is not allowed, even with `check=False`. That
  includes `run`, `create`, `rm`, `stop`, `restart`, `kill`, `pause`,
  `update`, `rename`, `exec`, `network`, `pull` and `compose`.
- A `deploy` or `rollback` that refuses for the database uses only the reads.
- `up` never passes Docker's own error output (stderr) on, for any call. Real
  Docker error text can name the daemon address (`DOCKER_HOST`), the daemon's
  data root (a host path, under the home directory for rootless Docker) and
  the port of a failed bind. `up` reports a failed call by its label and exit
  code only.

Exit codes for `up`: `0` when the stack is healthy, `1` when it is not (the
`part=` names which part failed), `2` on a usage or configuration error.

### Systemd unit `ops/systemd/aicaddie-stack-up.service`

The file must contain exactly these lines. Blank lines may be added; comment
lines (`#` or `;`) may not, so that no line can carry a host path.

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

Each value has a fixed form:

| Key | Form |
|---|---|
| `Description` | letters, digits, spaces and `,'()-`, starting with a letter or digit |
| `Documentation` | space-separated `https://github.com/jasonhorga/garmin-ai-caddie[/…]` URLs |
| `After`, `Wants` | space-separated unit names ending in `.target`, `.service` or `.socket` (no `.mount`: its name encodes a path) |
| `RemainAfterExit` | `yes`, `no`, `true` or `false` |
| `SyslogIdentifier` | letters, digits, `_`, `.` and `-` |

The file has exactly one `ExecStart=`, and no `Environment`,
`EnvironmentFile`, `WorkingDirectory` or `ExecStart*Pre/Post` lines. The
script's production defaults are the configuration.

A oneshot unit has no start timeout by default. `TimeoutStartSec`, if
present, appears once. It is `infinity`, `0`, or at least 1260 s. That is the
longest path of `up` with the defaults: the daemon (300 s), the database
(180 s), the sync lock (600 s) and the API's health (180 s). It is written as
`<n>`, `<n>s`, `<n>min` or `<n>h`.

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
     There are only reads (see "Docker commands"), and no `docker start`. A
     similarly named container (running and healthy or not) is neither used
     nor touched.
   - Not running: `docker start <db>`, then wait for `healthy`.
   - `docker start <db>` fails: the database stays exited with its stale
     `healthy`, which does not count. Exit 1 with `part=database`, and nothing
     but the database is started. With a 0.5 s database timeout this ends in
     less than 4 s.
   - Running: wait for `healthy` (a database that reports healthy only after
     5 s is waited for), and never stop or restart it.
   - Not healthy within `AICADDIE_DB_READY_TIMEOUT_SECONDS`: exit 1 with
     `part=database`, and the API container is not started. With a 0.5 s
     timeout, a database that is `starting` or `unhealthy` takes at least
     0.5 s and less than 4 s.
   - A Docker error or an unexpected exception in this phase: exit 1 with
     `part=database`, no traceback, nothing started. With a 0.5 s database
     timeout this ends in less than 4 s. That holds whichever read the
     daemon refuses first (after one answer or after two).
   - The database container's configuration (`Config`, `HostConfig`,
     `Mounts`, image, id) is never changed. `AICADDIE_DB_CONTAINER` picks the
     name, also when a default-named container exists and is healthy.
   - Starting the database never waits for the sync lock.
3. **API selection.**
   - If a container is running and publishes the port, select it with
     `find_current`. Its existing fail-closed rules apply: a non-release
     container on the port, or several release containers on it, end in exit
     1 with `part=api` and the container names in the reason.
   - The running release container selected this way must carry a
     40-lowercase-hex `ai.caddie.source-revision` label and pass
     `assert_layout`. Otherwise: exit 1 with `part=api` and its name in the
     reason. It keeps running, and nothing is started.
   - Otherwise select, among the stopped containers, the release container
     with the latest `FinishedAt`, compared as a time (Docker trims trailing
     zeros of the fraction; the existing `_finished_key`).
   - The selected stopped container must:
     - have a name with the release prefix;
     - carry a 40-lowercase-hex `ai.caddie.source-revision` label;
     - publish the configured port;
     - pass `assert_layout` (exactly one mount: the configured volume at
       `/var/lib/ai-caddie`, read-write; on the configured network).

     A newer container that fails any of these rules is skipped. That
     includes a read-only volume, the volume at another path, and a second
     mount. `previous_release` without the sha exclusion is fine.
   - The prefix, port, volume and network are the configured ones
     (`AICADDIE_CONTAINER_PREFIX`, `AICADDIE_API_PORT`,
     `AICADDIE_PRIVATE_VOLUME`, `AICADDIE_DEPLOY_NETWORK`), never the
     production defaults. With the sandbox drill's values, `up` starts the
     drill's database and release. It skips newer decoys that match the
     production prefix or the production layout instead.
   - Name, Id or list order never decide. If two or more containers that pass
     every rule share the latest `FinishedAt` (compared as a time, so
     `…41.75Z` and `…41.750Z` are the same), `up` does not choose: exit 1 with
     `part=api`, each of their names in the reason, and no API started. A tie
     with a container that fails a rule, or a tie among older releases, does
     not matter.
   - No candidate: exit 1 with `part=api`.
   - Older stopped releases are never started.
4. **API start.** Only after the database is healthy.
   - A selected API that already runs is never started, stopped or
     restarted, and `up` does not wait for the sync lock for it.
   - Before it starts a stopped API, `up` takes the sync lock
     (`AICADDIE_SYNC_LOCK`, the flock that `deploy`, `rollback` and the sync
     cron take). It waits up to `AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS` and
     starts nothing while the lock is busy.
   - Under the lock it selects the API again by the rules in 3. If a release
     serves by then (a deploy or rollback started it while `up` waited), `up`
     starts nothing and checks that release's health. The ok line names that
     container and its revision.
   - A lock not acquired in time: exit 1 with `part=api`, API not started.
     SIGTERM during the lock wait: exit 1 with `part=api`, API not started.
   - If the selected container is still stopped, `up` runs `docker start` on
     it. It never runs `docker run` for a new one. If `docker start` fails,
     `up` logs it (see "`up` result lines") and still waits for health: a
     container in Docker's restart backoff can come up by itself.
   - Then `up` polls `wait_health(local_health_url, <its revision>, …)` (see
     "Local API health"). An API that answers `booting` for 5 s after its
     start and then reports its revision leads to success.
   - If it does not report its revision with `status: ok` in time: exit 1
     with `part=api`. That includes an answer with another release's
     revision, or with another status. With a 0.5 s health timeout this takes
     at least 0.5 s and less than 4 s. The container is left running.
5. **Nothing to change.** When the database is running and healthy and the API
   is running, `up` issues no `docker start`, only reads. It checks local
   health for the running revision and exits 0. A busy sync lock does not
   delay it. In every run, `up`'s Docker calls are reads or `start` (see
   "Docker commands").
6. **Phases and the end.**
   - `part=` follows the phase (see "`up` result lines"). A foreign container
     on the API port whose name contains "database" gives `part=api`.
   - SIGTERM while waiting for the daemon gives `part=docker`. SIGTERM while
     waiting for the database gives `part=database`. In both cases `up` exits
     1 and the API is not started. SIGHUP and SIGINT while waiting for the
     database do the same. SIGTERM while waiting for the started API's health
     gives `part=api`, exit 1, and the API is left running.
   - With the default timeouts, `up` is still waiting after 2.5 s.
   - After the health answer `up` needs no Docker: if the daemon disappears
     then, `up` still exits 0 with the ok line.
7. **Defaults and polling** (virtual clock, poll 3 s, the three timeouts
   unset). With the daemon never reachable, `up` fails with `part=docker`
   after sleeping at least 300 s and less than 303 s in total. With a database
   that stays `starting`, it fails with `part=database` after at least 180 s
   and less than 183 s. With a running API that never reports its revision,
   it fails with `part=api` after at least 180 s and less than 183 s. Every
   sleep is 3 s, except that the last may be shorter. Nothing is started in
   these runs.
8. Usage and configuration errors exit 2 without calling `docker`. The usage
   text names `up`. `AGENTHUB_DEPLOY_SHA` does not change `up`.

### G2 — `deploy` and `rollback` require a healthy database before touching containers

Pass conditions:

1. `deploy <sha>` and `rollback <sha>` check that the database container
   (exact name) exists, is running and is `healthy`.
   - The database check is their first check. `deploy` makes it before it
     builds images: a revision whose images are not built yet is refused for
     the database, without `docker build`. `rollback` makes it before it
     looks for its target: a rollback to a revision with no stopped release
     is refused for the database.
   - The check holds on every path: a switch, a deploy of the revision that
     already serves, a bootstrap deploy (nothing serves, bootstrap env file
     set), a rollback with nothing serving, and a rollback to the revision
     that already serves.
   - The check that decides runs **under the sync lock** on each of these
     paths: after the lock is taken, before `switch` or `verify_live` (the
     already-live path of `deploy`, whose failure handling can stop
     containers), and before the rollback's `docker stop` or its already-live
     health check.
   - The early check does not replace the check under the lock. A database
     that stops or turns `unhealthy` while the script waits for the lock (a
     sync is running) must be noticed.
   - Each check may wait up to `AICADDIE_DB_READY_TIMEOUT_SECONDS`.
     `deploy` and `rollback` never start the database themselves.
2. If the check fails: exit 1, the existing
   `result=failed … previous_untouched=true … reason=…` line with the database
   container's exact name in it, and only reads (see "Docker commands"): no
   `docker stop`, `start`, `run`, `rm`, `restart`, `pause`, `update`, `build`
   or any other change. The release container that served keeps running, and
   no other release container runs. A missing database with a similarly named
   healthy container is a failed check, and so is a running database without
   a healthcheck.
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
   under the sync lock (review-checked; done in `7ba57af`). The "Sandbox
   drill" section names `AICADDIE_DB_CONTAINER` and a disposable container
   with a healthcheck.

### G3 — A systemd user unit runs `up` at boot from the installed copy; the runbook explains it

Pass conditions:

1. `ops/systemd/aicaddie-stack-up.service` matches the "Systemd unit"
   interface above exactly: no comment lines, only the allowed keys, each
   value in its form, and the `TimeoutStartSec` rule.
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
   in fenced code blocks are not headings. It should also say that `up`
   waits for the sync lock before it starts a stopped API, and that it
   refuses a tie between stopped releases (review-checked).
4. The runbook's Environment table has one row per new variable, in the form
   `` | `<VARIABLE>` | <meaning> | `<default>` | ``, with the defaults
   `garmin-ai-caddie-db-1`, `180` and `300`.

### G4 — Public repository hygiene: no host paths or values

Pass conditions:

1. `up` prints none of these:
   - environment values, configured paths or URLs;
   - temporary directories or install paths;
   - container environments;
   - Docker's own error text (the daemon address from `DOCKER_HOST`, the
     daemon's data root, the port of a failed bind);
   - a traceback.

   The tests put canary strings in all of them and check the output of every
   run. The output of every `up` run also never contains the configured port,
   so it holds no local health URL either.
2. The unit file and the runbook name only the `%h/.local/lib/aicaddie/`
   install path (`~/.local/lib/aicaddie/` in shell examples is the same path).
   They name no home directory, user name, host name or private data path.
   The tests check exact unit lines and the fixed value forms instead of
   searching for forbidden strings. The unit has no comment lines. The
   runbook is review-checked.

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
