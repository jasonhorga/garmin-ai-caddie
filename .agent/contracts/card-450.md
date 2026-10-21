# Card #450 — Deploy and rollback refuse to touch containers without a healthy database

Card #443 split this out as its goal G2. Today `deploy <sha>` and `rollback <sha>` ignore the
database. A deploy during a database outage stops the serving container, and then the new one
cannot come up. After this card, `deploy` and `rollback` check the database container first. They
stop, start, run or switch nothing until it is running and `healthy`, and they never start it
themselves.

Touches: `ops/agenthub_deploy.py`, `tests/test_agenthub_deploy.py`, `docs/operations/runbook.md`, `tests/acceptance/test_card_450_deploy_db_guard.py`, `.agent/contracts/card-450.md`

Acceptance tests (Claude-owned; Codex must not edit `tests/acceptance/`):
`tests/acceptance/test_card_450_deploy_db_guard.py` (6 tests). They run offline and call the real
script as a subprocess, with fake `docker` and `curl` executables first on `PATH`. The real
`ops/complete_homeserver_api_deploy.sh` runs as the check-only gate. No sync script and no public
URL are configured.

`ops/agenthub_deploy.py` is a pinned file. The PR body must say
**"re-pin required: ops/agenthub_deploy.py"**.

## Interface

### Configuration

`deploy` and `rollback` now read the two database variables that `up` already reads, with the same
defaults and the same parsing:

| Variable | Meaning | Default |
|---|---|---|
| `AICADDIE_DB_CONTAINER` | Exact name of the database container | `garmin-ai-caddie-db-1` |
| `AICADDIE_DB_READY_TIMEOUT_SECONDS` | Longest wait for that container to be running and `healthy` | `180` |

How `up` uses them does not change.

### What "healthy" means

The database is healthy only when all of these hold:
- a container named **exactly** `AICADDIE_DB_CONTAINER` exists. Look it up by exact name (for
  example `docker inspect <name>`). Do not use a `docker ps --filter name=` substring or regex
  match: `garmin-ai-caddie-db-1-old`, `old-garmin-ai-caddie-db-1` and `garmin-ai-caddie-db-10`
  are not the database;
- its `.State.Running` is `true`;
- its `.State.Health.Status` is `healthy`. A container without a healthcheck (no `.State.Health`)
  is **not** healthy.

The check polls every `AICADDIE_DEPLOY_POLL_SECONDS` until the database is healthy or
`AICADDIE_DB_READY_TIMEOUT_SECONDS` has passed. It never runs `docker start`, `run`, `create` or
`restart` on the database or on anything else. You may reuse the inspect format of
`wait_up_database` (`{"running":{{json .State.Running}},"health":{{json .State.Health}}}`), but not
its start step.

The fake `docker` renders only these template actions: `{{json <path>}}`, `{{.<path>}}` and
`{{index <path> "<key>"}}`. It answers `inspect`, `container inspect`, `ps`/`container ls`
(filters `name`, `publish`, `status`, `id`), `image inspect`, `info`, `version`, `run`, `stop`,
`start` and `rm`. Any other command or template action fails with exit 2.

### Where the check runs

- **The deciding check runs under the sync lock.** It runs after `SyncLock` is acquired and before
  any of these, on **every** path:
  - `deploy`: `switch` (including the bootstrap switch with nothing serving) and `verify_live`
    (the revision already serves);
  - `rollback`: its `docker stop`/`docker start`, its already-live `wait_health`, and a rollback
    with nothing serving.

  So when the check refuses, no container has changed and the API health URL has not been fetched.
- **An earlier fail-fast check** before `ensure_images` may stay. If you keep one, it must wait up
  to `AICADDIE_DB_READY_TIMEOUT_SECONDS` before it refuses, just like the deciding check: a
  database that is `starting` when the script begins and turns `healthy` 3 s later must not be
  refused. A healthy result from it never replaces the check under the lock.

### Refusal

A failed check raises a plain `DeployError`, not `CutoverFailed`. `main()` then prints the existing
line and returns **1**:

```
agenthub-deploy: result=failed action=<deploy|rollback> revision=<sha> previous_untouched=true elapsed_s=<n> reason=<text>
```

- `<text>` contains the configured database container name (for example
  `database garmin-ai-caddie-db-1 is not healthy`). The wording is free.
- There is exactly one `result=` line, and it has no `previous_restored=` field.
- Every docker call is a read: `ps`, `inspect`, `container inspect|ls|list|ps`, `image inspect`,
  `info`, `version`. No container or image changes (the fake's model is compared before and after),
  and `curl` is never called.
- The output has no traceback and no environment values (the fixtures carry canaries in container
  `Env`, the lock path and the bootstrap env-file path).

### Healthy database → unchanged behaviour

With a running, healthy database every path does what it does on `main`, with the same
container-changing docker calls in the same order:

| Path | Container changes | Result `container=` |
|---|---|---|
| `deploy` switch | `stop <old>`, `run <prefix><sha8>` | `<prefix><sha8>` |
| `deploy` of the revision already serving | none | the serving container |
| `deploy` bootstrap (nothing serving, bootstrap env file) | `run <prefix><sha8>` | `<prefix><sha8>` |
| `rollback` switch | `stop <current>`, `start <target>` | the target |
| `rollback` to the live revision | none | the live container |
| `rollback` with nothing serving | `start <target>` | the target |

When the first container change happens, the database is running and `healthy` and the sync lock
is held. The database is never started.

### Unit test file (card item 3)

Keep `tests/test_agenthub_deploy.py` green:
- add a running, healthy database container named `garmin-ai-caddie-db-1` to `production_fixture()`
  and to the empty fixtures (`{"containers": [], ...}`) that the bootstrap and missing-container
  tests write;
- teach its fake docker `.State.Health` (and any option or template action your check uses);
- change exact command-set assertions (`test_missing_current_container_fails_before_building`,
  `test_rollback_without_matching_container_fails`) only as far as the new `inspect` requires.

Do not weaken any other assertion. Unit tests for the new helper are welcome.

### Runbook (card item 4)

In `docs/operations/runbook.md`, `### Contract` under `## agenthub executor deploy` gets one
sentence in prose. Code blocks and table rows do not count; it may be its own paragraph or a list
item. The test splits each paragraph and list item into sentences at `.`, `!` or `?` followed by
whitespace and a capital letter, a backtick or `(`. One sentence must match all of these:

| Must contain | Pattern |
|---|---|
| `` `AICADDIE_DB_CONTAINER` `` (with backticks) | literal |
| deploy | `\bdeploy\b` |
| rollback | `\brollback\b` |
| refuse / refuses / refused | `(?i)\brefus` |
| healthy (not only "unhealthy") | `(?i)\bhealthy\b` |
| sync lock | `(?i)\bsync lock\b` |

A sentence that passes:

> `deploy` and `rollback` refuse to stop, start or switch any container unless the container named
> exactly `AICADDIE_DB_CONTAINER` is running and `healthy` (waiting up to
> `AICADDIE_DB_READY_TIMEOUT_SECONDS`), and they check it again under the sync lock right before
> the switch; they never start the database.

## Goals and pass conditions

### G1 — Without a healthy database, deploy and rollback refuse and change no container

1. `test_switches_are_refused_without_a_healthy_database`: `deploy <new>` (old release serving) and
   `rollback <prev>` (old serving, prev stopped) are each run against seven database states.
   `AICADDIE_DB_READY_TIMEOUT_SECONDS=0.5`. The states:
   - missing;
   - stopped, with a stale `healthy`;
   - running `unhealthy`;
   - running and still `starting`;
   - running without a healthcheck;
   - only `garmin-ai-caddie-db-1-old`, `old-garmin-ai-caddie-db-1` and `garmin-ai-caddie-db-10`
     exist, all running and healthy;
   - `AICADDIE_DB_CONTAINER=drill-db-1` is missing while the default-named database is healthy.

   Each run finishes in under 20 s and meets every refusal condition above: exit 1,
   `previous_untouched=true`, the reason names the configured database (`drill-db-1` in the last
   state), reads only, no change, no `curl`.
2. `test_every_path_is_refused_without_a_healthy_database`: the same refusal on the other paths,
   each with two of those states:
   - `deploy` of the revision already serving (unhealthy; missing);
   - bootstrap `deploy` (stopped; no healthcheck);
   - `rollback` to the live revision (unhealthy; missing). This proves the check runs before the
     already-live health check;
   - `rollback` with nothing serving (stopped; only similarly named).
3. `test_database_failing_while_waiting_for_the_sync_lock_is_noticed`: the test holds the sync lock
   and starts `deploy <new>` (or `rollback <prev>`) with a healthy database. It waits until the
   script has made no docker call for 1 s, which means it is blocked on the lock. Then it makes the
   database `unhealthy` (deploy) or stopped (rollback) and releases the lock. The run must refuse
   as in 1, against the model as it was after that change.

### G2 — A healthy database leaves deploy and rollback unchanged

4. `test_database_that_turns_healthy_within_the_timeout_is_waited_for`: the database is running,
   `starting`, and turns `healthy` 3 s after the fixture is written, with
   `AICADDIE_DB_READY_TIMEOUT_SECONDS=20`. Then:
   - `deploy <new>` and `rollback <prev>` succeed with the container changes in the table above;
   - at the first change the database is running and `healthy` and the sync lock is held;
   - with `AICADDIE_DB_CONTAINER=drill-db-1`, `drill-db-1` is the container waited for, and the
     unhealthy default-named container neither blocks the run nor gets started.
5. `test_healthy_database_leaves_every_path_unchanged` (`# pinned`): all six paths in the table
   succeed with exactly those container changes and that `container=`. The same holds for a
   `deploy` with a healthy `drill-db-1` configured and no default-named database.
6. CI: `tests/test_agenthub_deploy.py` stays green with its fixture changes (card item 3).

### G3 — The runbook states the guard

7. `test_runbook_contract_states_the_database_guard`: `### Contract` has a sentence matching the
   table above. The test then runs `deploy <new>` against an unhealthy database and expects the
   refusal from G1.

## Free choices (not tested)

- The helper's name and shape, for example `wait_database(cfg)`, shared by `up`'s non-starting
  path or separate. Where `db_name`/`db_ready_timeout` live, for example moved from `UpConfig` to
  `Config`.
- Whether an invalid `AICADDIE_DB_CONTAINER` makes `deploy`/`rollback` exit 2 (a configuration
  error, nothing touched). This is recommended and consistent with `up`.
- Whether a missing container is refused at once or after the timeout.
- The reason wording, and log lines such as `database <name> healthy`.
- Updating the Meaning cells of the two `AICADDIE_DB_*` rows in `### Environment` so they also
  mention deploy and rollback. This is welcome. Keep exactly one row per variable with the default
  first in backticks; card #451's acceptance test checks that.
- Where in `### Contract` the sentence goes. The numbered `deploy <sha>` steps and the
  `rollback <sha>` paragraph may also mention the check.

## Not covered (do not change here)

- How `up` behaves (#447, #448, #451), apart from sharing a helper without changing its results.
- Starting or repairing the database from `deploy`/`rollback`.
- `docker-compose.yml`, the images, the gate and sync scripts, and the other pinned files.

## Gate notes

All tests except test 5 (`# pinned`) fail on `main` (`69627e4`):
- 1, 2 and 3: `main` never checks the database. It switches (`stop` + `run`/`start`), or on the
  idempotent paths exits 0, so the run does not exit 1 or makes container changes.
- 4: `main` stops the old container about 0.5 s in, while the database is still `starting`.
- 7: `### Contract` does not mention `AICADDIE_DB_CONTAINER`.

Entry-point tests: G1 uses 1–3, G2 uses 4–5 and G3 uses 7. All of them run
`ops/agenthub_deploy.py` as a subprocess. Running Python was refused in this contract sandbox, so I
checked the tests by tracing them against `main`'s `deploy`, `switch`, `verify_live`, `rollback`,
`SyncLock`, `cleanup` and the gate script. The gate's run is the authority. If a case looks wrong
against this contract, report it on the card. Never edit the tests.
