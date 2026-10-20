# Card #443 — Bring the production stack back after a host reboot (database first)

After a host reboot the production stack must come back by itself, database
first, with nobody touching it. Restart policies cannot do this. A clean exit
and a failed exit behave in opposite ways, and nothing orders the containers.
So `ops/agenthub_deploy.py` gets an idempotent `up` action, and a systemd user
unit runs it at boot.

Touches: `ops/agenthub_deploy.py`, `ops/systemd/aicaddie-stack-up.service`, `docs/operations/runbook.md`, `tests/test_agenthub_deploy.py`, `tests/acceptance/test_card_443_stack_up.py`, `.agent/contracts/card-443.md`

Acceptance tests: `tests/acceptance/test_card_443_stack_up.py`. They use a fake
`docker` and a fake `curl` on `PATH`, with no real containers and no network.
Most tests run `ops/agenthub_deploy.py` as a subprocess. Two of them run a
standalone copy of the script installed at the unit's path under a temporary
home directory.

Risk: `ops/agenthub_deploy.py` is a pinned deploy file. State
"re-pin required: ops/agenthub_deploy.py" in the PR body. After the merge, its
release fails with `deploy pin mismatch` until the console reviews the diff and
re-pins the hash. That is expected. The console also installs the copy and the
unit.

## Interfaces

### CLI

```
ops/agenthub_deploy.py deploy <40-lowercase-hex-sha>
ops/agenthub_deploy.py rollback <40-lowercase-hex-sha>
ops/agenthub_deploy.py up
```

- `up` takes no argument. `up <anything>` is a usage error (exit 2).
  `AGENTHUB_DEPLOY_SHA` does not apply to `up`.
- The usage line becomes exactly
  `usage: agenthub_deploy.py {deploy|rollback} <40-lowercase-hex-sha> | up`
  and is printed to stderr.
- `up` must work from a standalone copy of the file, with no other repository
  file beside it, at `%h/.local/lib/aicaddie/agenthub_deploy.py`. It must not
  need the gate script, the sync build script, `XDG_RUNTIME_DIR` or a `.git`.

### New environment variables

`Config` parses these like the existing ones. A bad value is a `ConfigError`:
exit 2, the variable name on stderr, and no `docker` call at all.

| Variable | Meaning | Default |
|---|---|---|
| `AICADDIE_DB_CONTAINER` | Name of the database container. Must match the existing `PREFIX_PATTERN` (a valid container name) | `garmin-ai-caddie-db-1` |
| `AICADDIE_DB_READY_TIMEOUT_SECONDS` | How long to wait for the database's Docker health status to become `healthy` | `180` |
| `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS` | How long `up` retries while the Docker daemon is not reachable | `300` |

Every wait polls at `AICADDIE_DEPLOY_POLL_SECONDS`. The local API health wait
keeps `AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS` (the existing `wait_health`).

### Database container state

- The container is missing when `docker inspect <name>` fails with
  "No such object", or when no container of that exact name exists.
- It is running when `.State.Running` is true.
- It is healthy only when it is running **and** `.State.Health.Status` is
  `healthy`. When it is not running, a stale `healthy` from before the stop
  does not count. A container without a healthcheck (no `.State.Health`)
  never counts as healthy: that fails closed. The production container has a
  `pg_isready` healthcheck, like the compose `db` service.

### `up` result lines (stdout, existing `log()` prefix)

- Success, as the final line:
  `agenthub-deploy: result=ok action=up database=<db-name> container=<api-name> revision=<sha> elapsed_s=<n>`
- Failure, as the final line:
  `agenthub-deploy: result=failed action=up part=<docker|database|api> elapsed_s=<n> reason=<text>`
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

There is exactly one `ExecStart=`. The file has no `Environment`,
`EnvironmentFile`, `WorkingDirectory` and no `ExecStart*Pre/Post` lines. The
script's production defaults are the configuration.

## Goals

### G1 — `up` brings the live stack up, database first, idempotently

Pass conditions:

1. **Docker daemon.** Before anything else, `up` waits for the Docker daemon.
   While it is not reachable (any `docker` call fails, for example
   `docker info`), it retries every poll interval, up to
   `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS`. Once the daemon answers, `up`
   continues normally. When the timeout expires: exit 1 with `part=docker`,
   and no `docker start`.
2. **Database.**
   - Missing: exit 1 with `part=database`, the container name in the output,
     and no `docker start`, `run`, `create`, `pull`, `rm`, `update`, `rename`,
     `restart`, `kill` or `compose`.
   - Not running: `docker start <db>`, then wait for `healthy`.
   - Running: wait for `healthy`, and never stop or restart it.
   - Not healthy within `AICADDIE_DB_READY_TIMEOUT_SECONDS`: exit 1 with
     `part=database`, and the API container is not started.
   - The database container's configuration (`Config`, `HostConfig`,
     `Mounts`, image, id) is never changed. `AICADDIE_DB_CONTAINER` picks the
     name.
3. **API selection.**
   - If a container is running, select it with `find_current` (its existing
     fail-closed rules apply).
   - Otherwise select the stopped release container with the latest
     `FinishedAt`. It must: have a name with the release prefix, carry a
     40-hex `ai.caddie.source-revision` label, publish the configured port and
     pass `assert_layout`. `previous_release` without the sha exclusion is
     fine.
   - No candidate: exit 1 with `part=api`.
   - Older stopped releases are never started.
4. **API start.** Only after the database is healthy: if the selected
   container is not running, `docker start` it. Never `docker run` a new one
   and never stop a running one. Then `wait_health(local_health_url,
   <its revision>, …)`. If it does not report that revision: exit 1 with
   `part=api`.
5. **Nothing to change.** When the database is running and healthy and the API
   is running, `up` issues no `docker start` (or any other mutating command).
   It checks local health for the running revision and exits 0.
6. Usage and configuration errors exit 2 without calling `docker`. The usage
   text names `up`.

Recommended, not tested: take the existing `SyncLock` around the API start,
so `up` cannot race a concurrent `deploy` or `rollback`. If `docker start` of
the selected API container fails, log it and still wait for health, as
`restore_previous` does: a container in Docker's restart backoff can come up
by itself.

### G2 — `deploy` and `rollback` require a healthy database before touching containers

Pass conditions:

1. `deploy <sha>` and `rollback <sha>` check that the database container
   exists, is running and is `healthy`. They check before they stop, start,
   run or remove any container, and also before the already-live (idempotent)
   path of `deploy`, whose failure handling can stop containers. They may
   wait up to `AICADDIE_DB_READY_TIMEOUT_SECONDS`, but they never start the
   database themselves.
2. If the check fails: exit 1, the existing
   `result=failed … previous_untouched=true … reason=…` line with the database
   container name in the reason, and no `docker stop`, `start`, `run` or `rm`.
   The current container keeps running.
3. With a healthy database, `rollback` (and `deploy`) behave as before. The
   unit tests in `tests/test_agenthub_deploy.py` must stay green: add a
   running, healthy database container to `production_fixture()` and teach
   their fake `docker` about `.State.Health`. Change their exact
   command-set assertions only as far as the new `inspect` of the database
   requires. Do not weaken anything else.
4. `docs/operations/runbook.md` says that `deploy` and `rollback` refuse to
   run without a healthy database. The sandbox drill says it must point
   `AICADDIE_DB_CONTAINER` at a disposable container that has a healthcheck.

### G3 — A systemd user unit runs `up` at boot from the installed copy; the runbook explains it

Pass conditions:

1. `ops/systemd/aicaddie-stack-up.service` matches the "Systemd unit"
   interface above, exactly.
2. The unit's `ExecStart` works: with `%h` expanded to a home directory where
   the script is installed at `.local/lib/aicaddie/agenthub_deploy.py`, it
   brings a stopped database and an exited API back and exits 0. The test
   replaces only the interpreter with the test runtime.
3. `docs/operations/runbook.md` has a `## Boot recovery` (or `###`) section
   that mentions:
   - `ops/systemd/aicaddie-stack-up.service` and `agenthub_deploy.py up`;
   - the install location `.local/lib/aicaddie/agenthub_deploy.py`, a pinned
     copy rather than a checkout;
   - `systemctl --user` (enable the unit);
   - `loginctl enable-linger`, without which a user unit does not start at
     boot;
   - `journalctl --user -u aicaddie-stack-up` (read its journal).

   The runbook also documents the three new variables, for example in the
   existing Environment table.

### G4 — Public repository hygiene: no host paths or values

Pass conditions:

1. `up` prints no environment values, configured paths or URLs, temporary
   directories or install paths. The tests put canary strings in all of them
   and check the output.
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
