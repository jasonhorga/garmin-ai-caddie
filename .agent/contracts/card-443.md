# Card #443 — Bring the production stack back after a host reboot (database first)

After a host reboot the production stack must come back by itself, database
first, with nobody touching it. Restart policies cannot do this. A clean exit
and a failed exit behave in opposite ways, and nothing orders the containers.
So `ops/agenthub_deploy.py` gets an idempotent `up` action, and a systemd user
unit runs it at boot.

Touches: `ops/agenthub_deploy.py`, `ops/systemd/aicaddie-stack-up.service`, `docs/operations/runbook.md`, `tests/test_agenthub_deploy.py`, `tests/acceptance/test_card_443_stack_up.py`, `.agent/contracts/card-443.md`

Acceptance tests: `tests/acceptance/test_card_443_stack_up.py` (30 tests). They
use a fake `docker` and a fake `curl` on `PATH`, with no real containers and no
network. Most tests run `ops/agenthub_deploy.py` as a subprocess. Two of them
run a standalone copy of the script installed at the unit's path under a
temporary home directory, with that home as the working directory. Some tests
hold the sync lock themselves, standing in for a running sync. One test runs
the script's `__main__` on a virtual clock (see "Waits and the clock").

Risk: `ops/agenthub_deploy.py` is a pinned deploy file. State
"re-pin required: ops/agenthub_deploy.py" in the PR body. After the merge, its
release fails with `deploy pin mismatch` until the console reviews the diff and
re-pins the hash. That is expected. The console also installs the copy and the
unit.

## Revision 5: pin what was added after revision 4

This job names the adversarial failure on head `6ea5220`. The gate report is
not in the contract sandbox, and the sandbox refused to run Python. So this
revision again comes from reading the code. Revision 4 was written against
`7ba57af`. Since then the branch has gained two Codex commits:

- `f7a0969`:
  - `up` takes the sync lock before it starts a stopped API container;
  - under the lock it reads the containers again and selects again;
  - a failed `docker start` of the API is logged, and the health wait still
    runs;
  - the `is_up` branches of `main()`'s other handlers, which never ran, are
    gone.
- `6ea5220`:
  - `docker ps` in `list_containers` now discards Docker's stderr;
  - `up` now refuses when several valid stopped releases share the latest
    `FinishedAt`.

No revision-4 test pinned any of these, nor the running-API checks of
`7ba57af`. Reverting any one of them still passed all 25 tests. Revision 5 makes
each of them part of the contract and tests it:

- **Sync lock.** While the test holds the lock, `up` must not start the stopped
  API. Meanwhile a deploy starts a release, or a newer release stops. Under the
  lock `up` must then use that one. When the API already runs, `up` must not
  wait for the lock. A lock timeout and SIGTERM during the lock wait give
  `part=api`.
- **Failed API start.** Docker may report the start as failed even though the
  container comes up. `up` then still succeeds, and the failure is logged with
  the container's name. A container that stays exited is waited for until the
  health timeout.
- **`FinishedAt` tie.** `up` refuses a tie at the newest valid release
  (`part=api`, both names). A tie among older releases does not matter, and
  neither does a tie with a container that fails a rule.
- **Running API.** A running release container on the port that is on another
  network, has a read-only volume, or has no or a short revision label gives
  `part=api`. It is left running.
- **Docker's own output.** Like real Docker, the fake docker's output names
  things that must not reach the log:
  - its `info` answer names the host and the data root;
  - its "cannot connect" error names the socket (`DOCKER_HOST`);
  - its `start` errors name a path under the data root, or the port.

  All of these carry canaries. The daemon now also goes away just before the
  `inspect` and just before the database's `docker start`. Passing Docker's
  stderr or its `info` answer through fails.
- **Configuration.** Both new timeouts are now tested with a non-number and
  with a negative value.
- **Unit timeout.** With the lock wait, the default waits of `up` add up to
  1260 s. A `TimeoutStartSec`, if present, must allow that.

From reading the code, head `6ea5220` passes all 30 tests. **No change to the
script is expected.** Codex merges this branch and runs the tests. If a new
case fails on the head, check the case against this contract first. Fix the
script or the runbook only where they break the contract. If the case itself
is wrong, report it on the card. Never edit `tests/acceptance/`. The runbook's
"Boot recovery" section should also say that `up` waits for the sync lock
before it starts a stopped API container (review-checked).

All 30 tests fail on `main`. There, `up` is a usage error, the unit and the
runbook section do not exist, and `deploy` and `rollback` do not check the
database. Python could not be run in the contract sandbox, so this claim also
comes from reading the code.

### Changes that stay uncaught

Each change below either behaves the same in every run this contract defines,
or is allowed by it:

- **A default within one poll interval of 300 or 180 s** (for example 301 or
  299). The virtual-clock test uses 3-s polls, which is as fine as it can
  measure.
- **A second `docker start` of the database**, after a failed start or after a
  database that stops again during the wait. The contract does not forbid it.
- **Whether a failed `docker start` of the database ends `up` at once** or is
  waited out until the database timeout. The part is `database` either way.
- **Dropping the early fail-fast database check** in `deploy` or `rollback`.
  It is optional; the check under the lock is the one that decides.
- **Logging `starting <name>` just after the `docker start`** instead of just
  before it. The tests see the log and the call, but not their relative order.
- **How the daemon is probed** (`docker info`, `docker version` or `docker ps`)
  and how many calls one attempt makes.
- **Whether a Docker error in the database phase ends `up` at once** or is
  retried until the database timeout. Both are allowed; the part is `database`
  either way.
- **The phase boundary inside the round of calls that reports the database
  healthy.** A Docker error that arrives exactly between that answer and the
  first call of the API selection is not modelled. The API selection itself
  is tested with `part=api`.
- **A selection before the lock.** `up` may select once before it takes the
  lock, as the head does, or only look for a running API first. Either way,
  the selection under the lock decides. Its errors (no candidate, a tie, a
  foreign container) give `part=api` before or under the lock.
- **Holding the lock through the health wait**, or releasing it once the start
  was issued. A deploy that takes the lock afterwards sees the started
  container as the current one either way.
- **Re-checking the database under the lock in `up`.** This is not required.
  The database was healthy just before the lock wait. An API started on a
  database that has gone away fails its health wait with `part=api`.
- **`shield_signals()` just before `up` returns.** It only matters for a
  signal in the instant between the health answer and the ok line. No test can
  hit that instant.
- **The lock wait's own poll** (at most 1 s) and its bound by
  `AICADDIE_DEPLOY_DEADLINE_SECONDS`. That is the existing `SyncLock` code,
  which `deploy` and `rollback` share; this card does not change it.
- **The wording** of reasons and of the failed-start log line, as long as they
  carry the names they must.

If the gate reports a survivor that is not on this list, it should name it. I
will then either pin the behaviour it changes or record it here as equivalent.

### History

Revision 4 (the adversarial check again named `f0460ed`) required:
- that `up` uses only reads and `start`, and that a refused `deploy` or
  `rollback` uses only reads;
- `part=database` and nothing else started when the database's `docker start`
  fails (the exited database keeps a stale `healthy`);
- that `up` follows the sandbox drill's prefix, network, volume and database,
  with decoys that match only the production values;
- the whole layout rule: a read-only volume, another mount path and a second
  mount are decoys;
- the check under the sync lock for a bootstrap deploy, a rollback with nothing
  serving and a rollback to the revision that already serves;
- `part=database` for SIGHUP and SIGINT during the database wait;
- no configured port and no container environment in the output of `up`;
- no comment lines and fixed value forms in the unit.

Codex then added `f7a0969` and `6ea5220` (see above).

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

`Config` parses these like the existing ones. A bad value (for a timeout: not
a number, or negative) is a `ConfigError`: exit 2, the variable name on
stderr, and no `docker` call at all.

| Variable | Meaning | Default |
|---|---|---|
| `AICADDIE_DB_CONTAINER` | Name of the database container. Must match the existing `PREFIX_PATTERN` (a valid container name; it never starts with `-`) | `garmin-ai-caddie-db-1` |
| `AICADDIE_DB_READY_TIMEOUT_SECONDS` | How long to wait for the database's Docker health status to become `healthy` | `180` |
| `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS` | How long `up` retries while the Docker daemon is not reachable | `300` |

### Waits and the clock

`up` has three new waits. Each one uses only its own timeout:

- the daemon wait uses `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS`;
- the database wait uses `AICADDIE_DB_READY_TIMEOUT_SECONDS`;
- the local API health wait keeps `AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS`
  (the existing `wait_health`).

Every one of these waits follows the same rules:

- It measures time with `time.monotonic()` (`time.time()` also works).
- Between attempts it pauses with `time.sleep(AICADDIE_DEPLOY_POLL_SECONDS)`.
  Only the last pause may be shorter, for example `min(poll, remaining)`.
- When a wait fails, it has slept at least its timeout in total, and at most
  one poll interval more.

`up` also waits for the sync lock before it starts a stopped API container
(G1.4). That is the existing `SyncLock` wait. It keeps
`AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS` (default 600 s) and its own poll, and
the rules above do not apply to it.

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
  - `api`: everything after the database is healthy. That includes the API
    selection, the sync lock wait, the start and the health wait.
- Once `wait_health` confirms the selected container's revision, `up` makes
  no further `docker` call. The ok line uses the database name, container and
  revision it already holds.
- SIGTERM, SIGINT or SIGHUP (systemd stopping the unit) ends `up` with exit 1
  and the failed line, with the part of the current phase. A started API is
  left running.
- No exception escapes `main()`. An unexpected one becomes the failed line
  with the part of its phase. No output contains a traceback.
- Every `docker start` that `up` issues is logged first as
  `starting <container-name>`. A `docker start` of the API that fails is
  logged with the container's name and the word "failed".
- Log lines carry only names, revisions and reasons. They never contain
  environment values, configured paths or URLs, or the script's own path.
  That includes the configured port and the local health URL: say "the
  configured port", as `deploy` already does. `up` never prints a container's
  environment.
- `up` never passes Docker's own output through. It captures the stdout of
  every docker call it makes, and it discards or captures the stderr. Docker's
  text can name the daemon socket (`DOCKER_HOST`), the data root, the host
  name or the port.

### Docker commands

- `up` uses only reads and `start`. The reads are `info`, `version`, `ps`,
  `inspect` (also as `container inspect`) and `image inspect`. Any other
  command is a change and is not allowed, even with `check=False`. That
  includes `run`, `create`, `rm`, `stop`, `restart`, `kill`, `pause`,
  `update`, `rename`, `exec`, `network`, `pull` and `compose`.
- A `deploy` or `rollback` that refuses for the database uses only the reads.

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
present, appears once. Its value is `infinity`, `0`, or at least 1260 s. That
is the sum of the default waits: 300 s daemon, 180 s database, 600 s sync
lock and 180 s API health. It is written as `<n>`, `<n>s`, `<n>min` or
`<n>h`.

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
     `part=database`, no traceback, nothing started. This covers the daemon
     going away before the `ps`, before the `inspect` or before the
     database's `docker start`. With a 0.5 s database timeout this ends in
     less than 4 s.
   - The database container's configuration (`Config`, `HostConfig`,
     `Mounts`, image, id) is never changed. `AICADDIE_DB_CONTAINER` picks the
     name, also when a default-named container exists and is healthy.
3. **API selection.**
   - If a container is running and publishes the port, select it with
     `find_current`. Its existing fail-closed rules apply: a non-release
     container on the port, or several release containers on it, end in exit
     1 with `part=api` and the container names in the reason.
   - A running release container selected this way must also carry a
     40-lowercase-hex `ai.caddie.source-revision` label and pass
     `assert_layout`. If it does not, `up` exits 1 with `part=api` and its
     name in the reason. The container is left running and nothing is
     started. Its health answer does not make it valid: an `ok` answer with
     an empty or short revision is refused too.
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
   - **Tie.** Several valid stopped releases may share the latest
     `FinishedAt`, compared as a time. Then `up` refuses to guess: exit 1 with
     `part=api`, the reason names all of them, and no API container is
     started. Only a tie among the newest valid releases counts. A tie among
     older releases, or with a container that fails a rule, does not matter.
   - The prefix, port, volume and network are the configured ones
     (`AICADDIE_CONTAINER_PREFIX`, `AICADDIE_API_PORT`,
     `AICADDIE_PRIVATE_VOLUME`, `AICADDIE_DEPLOY_NETWORK`), never the
     production defaults. With the sandbox drill's values, `up` starts the
     drill's database and release. It skips newer decoys that match the
     production prefix or the production layout instead.
   - Name, Id or list order never decide.
   - No candidate: exit 1 with `part=api`.
   - Older stopped releases are never started.
4. **API start.**
   - **Sync lock.** A stopped API container is started only after the
     database is healthy, and only under the existing sync lock (`SyncLock`
     on `AICADDIE_SYNC_LOCK`, waiting up to
     `AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS`). So `up` cannot race a sync, a
     deploy or a rollback. While it waits for the lock it starts nothing.
   - **Selection under the lock.** Under the lock, `up` reads the containers
     again and repeats the selection of rule 3, and that selection decides.
     If a release now runs on the port (a deploy finished meanwhile), `up`
     starts nothing and waits for that container's health. If a newer valid
     release has stopped meanwhile, that release is the one started.
   - When an API container already runs, `up` does not wait for the lock.
     That also holds when `up` has just started the database.
   - The lock is not acquired in time, or SIGTERM arrives during the lock
     wait: exit 1 with `part=api`, nothing started. With a 0.5 s lock timeout
     this takes at least 0.5 s and less than 4 s.
   - If the selected container is not running, `docker start` it. Never
     `docker run` a new one, and never stop or restart a running one.
   - If `docker start` fails, `up` logs a line that names the container and
     says the start failed. It still waits for the container's health, since
     Docker's restart policy can bring it up by itself. If the container then
     reports its revision, `up` exits 0.
   - Then poll `wait_health(local_health_url, <its revision>, …)` (see "Local
     API health"). An API that answers `booting` for 5 s after its start and
     then reports its revision leads to success.
   - If the API does not report its revision with `status: ok` in time: exit
     1 with `part=api`. That includes an answer with another release's
     revision, or with another status. With a 0.5 s health timeout this takes
     at least 0.5 s and less than 4 s, also after a failed start. The
     container is left running.
5. **Nothing to change.** The database is running and healthy and the API is
   running. Then `up` issues no `docker start`, only reads. It checks local
   health for the running revision and exits 0, also while a sync holds the
   lock. In every run, `up`'s Docker calls are reads or `start` (see "Docker
   commands").
6. **Phases and the end.**
   - `part=` follows the phase (see "`up` result lines"). A foreign container
     on the API port whose name contains "database" gives `part=api`.
   - SIGTERM while waiting for the daemon gives `part=docker`. SIGTERM while
     waiting for the database gives `part=database`. In both cases `up` exits
     1 and the API is not started. SIGHUP and SIGINT while waiting for the
     database do the same.
   - SIGTERM while waiting for the sync lock gives `part=api`, and nothing is
     started.
   - SIGTERM while waiting for the started API's health gives `part=api` and
     exit 1. The API is left running.
   - With the default timeouts, `up` is still waiting after 2.5 s.
   - After the health answer `up` needs no Docker: if the daemon disappears
     then, `up` still exits 0 with the ok line.
7. **Defaults and polling** (virtual clock, poll 3 s, the three timeouts
   unset). Nothing is started in these runs.
   - With the daemon never reachable, `up` fails with `part=docker` after
     sleeping 300–303 s in total.
   - With a database that stays `starting`, it fails with `part=database`
     after 180–183 s.
   - With a running API that never reports its revision, it fails with
     `part=api` after 180–183 s.
   - Every sleep is 3 s, except that the last may be shorter.
8. **Usage and configuration errors** exit 2 without calling `docker`. The
   usage text names `up`. Both new timeouts refuse a non-number and a negative
   value. `AGENTHUB_DEPLOY_SHA` does not change `up`.

### G2 — `deploy` and `rollback` require a healthy database before touching containers

Pass conditions:

1. `deploy <sha>` and `rollback <sha>` check that the database container
   (exact name) exists, is running and is `healthy`.
   - This holds on every path: a switch, a deploy of the revision that already
     serves, a bootstrap deploy (nothing serves, bootstrap env file set), a
     rollback with nothing serving, and a rollback to the revision that
     already serves.
   - The check that decides runs **under the sync lock** on each of these
     paths: after the lock is taken, before `switch` or `verify_live` (the
     already-live path of `deploy`, whose failure handling can stop
     containers), and before the rollback's `docker stop` or its already-live
     health check.
   - An earlier fail-fast check before the image build may stay, but it does
     not replace the check under the lock. A database that stops or turns
     `unhealthy` while the script waits for the lock (a sync is running) must
     be noticed.
   - Each check may wait up to `AICADDIE_DB_READY_TIMEOUT_SECONDS`.
     `deploy` and `rollback` never start the database themselves.
2. If the check fails: exit 1, the existing
   `result=failed … previous_untouched=true … reason=…` line with the database
   container's exact name in it, and only reads (see "Docker commands"): no
   `docker stop`, `start`, `run`, `rm`, `restart`, `pause`, `update` or any
   other change. The release container that served keeps running, and no other
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
   under the sync lock (review-checked; done in `7ba57af`). The "Sandbox
   drill" section names
   `AICADDIE_DB_CONTAINER` and a disposable container with a healthcheck.

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
   in fenced code blocks are not headings. It should also say that `up` waits
   for the sync lock before it starts a stopped API container
   (review-checked).
4. The runbook's Environment table has one row per new variable, in the form
   `` | `<VARIABLE>` | <meaning> | `<default>` | ``, with the defaults
   `garmin-ai-caddie-db-1`, `180` and `300`.

### G4 — Public repository hygiene: no host paths or values

Pass conditions:

1. `up` prints none of these:
   - environment values, configured paths or URLs;
   - temporary directories or install paths;
   - container environments;
   - Docker's own output: its daemon socket, data root or host name;
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
- A `docker` call that blocks without answering is outside the waits above.
  That is a daemon that accepts the connection but never replies. Per-call
  timeouts are allowed, not required.
