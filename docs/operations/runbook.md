# Operations Runbook

> **Since the agenthub cutover, production backend deploys are made only by the
> agenthub executor after a merge** (see "agenthub executor deploy" below and
> [AGENTS.md](../../AGENTS.md)). The root [RUNBOOK.md](../../RUNBOOK.md) is an
> index of the agenthub development, review, release and TestFlight workflow.
> The candidate and manual switch steps in "Build the Sync Image" are kept as
> reference for the pre-cutover flow and for owner-run recovery; agents do not
> run them.

## Start Services

Fixture-only API:

```bash
ops/run_local_fixture.sh
```

Private/local API:

```bash
ops/run_local_private.sh
```

Frontend:

```bash
cd web_v2
npx -y -p node@24 -c 'npm run dev -- --host 127.0.0.1'
```

Container stack:

```bash
cp .env.example .env
# edit .env with a private AI_CADDIE_ADMIN_TOKEN before exposing the API
docker compose up --build
```

The container entrypoint honors `AI_CADDIE_PRIVATE_ROOT` and symlinks private
runtime directories from that root into `/app` before starting FastAPI. Use this
for NAS/Fly/VPS deployments so downloaded Garmin data and session material are
kept on persistent storage instead of inside the image.

### Failure and restart behavior

The Compose API uses a bounded `on-failure:3` policy and Postgres uses
`on-failure:5`; neither service is allowed to retry forever. The API entrypoint
waits for a PostgreSQL readiness probe before running migrations, serializes
schema/identity initialization with a lock on the private volume, and applies a
bounded migration timeout. This matters after a database outage or host reboot:
starting a broken dependency must produce a stopped, inspectable container rather
than a CPU/IO restart storm. The JSON log driver is capped at three 10 MiB files
per container. Resource limits are environment-overridable for a larger host:
`AI_CADDIE_API_MEMORY_LIMIT`, `AI_CADDIE_API_CPUS`,
`AI_CADDIE_DB_MEMORY_LIMIT`, and `AI_CADDIE_DB_CPUS`.

For a home-only NAS VM, use `docs/deployment/nas-vm-tunnel.md`: keep the API on
`127.0.0.1:9000`, publish it through Cloudflare Tunnel or Tailscale Funnel, and
set GitHub `AI_CADDIE_API_BASE_URL` to the public HTTPS origin.
The helper `ops/bootstrap_nas_vm_api.sh --install-system` performs the VM-side
API bootstrap and keeps `AI_CADDIE_API_PUBLISH_HOST=127.0.0.1`.

## Stop Services

Stop foreground dev servers with `Ctrl-C`. For background processes, find and stop the process explicitly:

```bash
pgrep -af 'uvicorn server_v2.main:app'
```

## Refresh Garmin Session

Use browser session import first:

```bash
uv run python -m ai_caddie.garmin.garmin_auth
uv run python -m ai_caddie.garmin.fetch --refresh-auth
```

If auth is expired, API sync status should report `reauth_required`.

## Probe Official Garmin OAuth

OAuth is a feasibility track only. CN Web Session remains the primary connector until OAuth proves scorecards, golf shots, and course metadata.

```bash
export AI_CADDIE_GARMIN_OAUTH_CLIENT_ID=<client-id>
export AI_CADDIE_GARMIN_OAUTH_CLIENT_SECRET=<client-credential>
export AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI=<registered-redirect-uri>
uv run python ops/probe_garmin_oauth.py status
uv run python ops/probe_garmin_oauth.py authorize
uv run python ops/probe_garmin_oauth.py exchange --code <returned-code> --code-verifier <printed-verifier>
```

The exchange output is intentionally secret-free: it reports whether bearer material was received, a one-way user-id fingerprint, granted permissions, and whether any golf replacement capability is proven.

## Configure Gemini CLI OAuth

For local/dev AI provider testing, set:

```bash
export AI_CADDIE_LLM_PROVIDER=gemini_cli_oauth
export GEMINI_OAUTH_CREDENTIALS_FILE=/path/to/oauth.json
export GOOGLE_CLOUD_PROJECT=<project-id>
```

Use `GEMINI_OAUTH_CREDENTIALS_JSON` or `GEMINI_OAUTH_CREDENTIALS_B64` instead of a file path only when a deployment secret manager requires inline values.
If the access token can expire during use, the credential JSON must include its own OAuth client id and client credential fields for refresh. AI Caddie intentionally has no embedded Gemini client credential fallback.

## Run Tests

Backend:

```bash
uv run python -m unittest discover -s tests -v
```

Mobile contract/static checks:

```bash
uv run python -m unittest tests.test_mobile_contracts -v
```

## Backup And Restore

Backup:

```bash
ops/backup_data.sh
```

The script writes `backups/latest.json` with the snapshot filename, size, and
SHA-256. `/api/v2/readiness` only treats backup evidence as current when that
manifest is fresh and the referenced tarball is still present and unchanged.

Restore:

```bash
uv run python ops/import_snapshot.py backups/ai-caddie-snapshot-YYYYMMDDTHHMMSSZ.tar.gz --target-root .
```

## Inspect Sync Status

```bash
curl -s http://127.0.0.1:9000/api/v2/sync/status
```

The response should never include cookie, CSRF, token, `.env`, or absolute private paths.

### Build the Sync Image

The homeserver sync job is a one-shot container. The API deployment is not
complete until the matching sync image exists. Build the matching image **before
switching the API container**, so a scheduled sync cannot see a new revision
whose sync toolchain is still downloading. Use the already built, revision-labelled
candidate API image explicitly:

```bash
API_IMAGE=<the-built-candidate-api-image> bash ops/build_sync_image.sh
```

Verify that `aicaddie-sync:<candidate-full-SHA>` exists and has the same
`ai.caddie.source-revision` label. Only then switch the healthy API container to
the production port. Immediately run the mandatory post-switch deployment gate
from this checkout; the matching image's cached build should finish quickly:

```bash
AICADDIE_API_CONTAINER=<the-container-on-the-production-port> \
  AICADDIE_API_PORT=39055 \
  bash ops/complete_homeserver_api_deploy.sh
```

The gate checks `/api/v2/health`, then invokes `ops/build_sync_image.sh` and
verifies the resulting immutable tag. It deliberately refuses to infer a
candidate when multiple `aicaddie-release-*` containers are running. If the
API was already switched and only the image is missing, the lower-level helper
can be run directly:

The current homeserver also keeps a pinned operational copy at
`/home/jason/garmin-ai-caddie-data/operations/deploy-tools/ops/`; its
`SOURCE_REVISION` file records the reviewed source commit. Use the checkout
version for normal development and refresh this host copy as part of the same
reviewed deployment change.

```bash
bash ops/build_sync_image.sh
```

It resolves the active API image, requires its full
`ai.caddie.source-revision` label, and creates
`aicaddie-sync:<same-full-SHA>`, which is the only tag the cron job accepts.
When building before the candidate is started, pass the labelled image
explicitly with `API_IMAGE=...`. The helper does not silently fall back to a
moving `:latest` tag; `PUBLISH_LATEST=1` is an explicit compatibility alias
only and is not used by cron.

### Homeserver Sync Cron

The production homeserver cron uses the installed copy of
`ops/homeserver_sync.sh` (currently `/home/jason/aicaddie-sync.sh`), not the
developer-only `ops/auto_sync.sh` entrypoint. The wrapper resolves the API
container on `AICADDIE_API_PORT` (default `39055`) and refuses an absent or
mismatched `aicaddie-sync:<full-SHA>` image before touching the private volume.
On a contract failure it always writes syslog and, when configured, sends a
deduplicated desktop/webhook alert:

```bash
export AICADDIE_SYNC_ALERT_WEBHOOK_URL=<private-webhook-url>
export AICADDIE_SYNC_ALERT_COOLDOWN_SECONDS=21600
```

The webhook value belongs in the host's protected cron environment, never in
Git or a container label. A successful run ends with `sync ok` and `done`; a
later successful run sends a single recovery alert and clears the failure
state.

## agenthub executor deploy

`ops/agenthub_deploy.py` (Python 3 standard library only) is the single-command
homeserver deploy/rollback used by the agenthub executor after a merge. The
executor exports the merged revision with `git archive <sha>`, runs the pinned
script from the root of that tree (no `.git`), and then polls
`/api/v2/health` until `revision == <sha>`. The manual exact-revision flow
above (build, switch, `ops/complete_homeserver_api_deploy.sh`) stays valid
until the agenthub cutover is complete.

### Contract

`deploy` and `rollback` refuse to run without a healthy `AICADDIE_DB_CONTAINER`; they check it again after acquiring the sync lock.

```bash
ops/agenthub_deploy.py deploy <40-lowercase-hex-sha>
ops/agenthub_deploy.py rollback <40-lowercase-hex-sha>
```

| Exit | Meaning |
|---|---|
| `0` | Success, including an idempotent re-run for the revision already serving. |
| `1` | Failed; the previous container serves again or was never stopped. |
| `2` | Invalid arguments/configuration (or the sha differs from `AGENTHUB_DEPLOY_SHA`); nothing touched. |
| `3` | Failed and the previous container could not be confirmed healthy; page a human. |

`deploy <sha>`:

1. Fails fast unless exactly one running container whose name starts with the
   prefix publishes the configured port, it mounts only the configured private
   volume read-write at `/var/lib/ai-caddie`, and it is on the configured
   network. A container outside the prefix on that port is also refused.
2. Builds `garmin-ai-caddie-api:<sha>` (label
   `ai.caddie.source-revision=<sha>`) and, through `ops/build_sync_image.sh`,
   `aicaddie-sync:<sha>`. An existing image with the correct label is reused.
3. Takes the sync cron's flock, so no sync runs during the switch.
4. If the current container already runs `<sha>`, it only re-checks health
   and step 7 (idempotent re-run). Otherwise it re-verifies both images and
   copies the current container's environment, minus entries inherited
   unchanged from the old image (so the new image's `ENV` defaults apply),
   overriding `AI_CADDIE_BUILD_REVISION`, `AI_CADDIE_PRIVATE_ROOT`, `PORT` and
   `AI_CADDIE_TOPO_RENDER_PROCESSES`. The values are written to a 0600 file in
   a private tmpfs directory immediately before `docker run` and deleted right
   after it. The switch is refused if less time is left before
   `AICADDIE_DEPLOY_DEADLINE_SECONDS` than a switch plus a restore can take.
5. `docker stop --time 30` the current container, then starts
   `<prefix><sha8>` with `--init`, `--restart on-failure:3`, capped json-file
   logs, `--pull never`, the revision label, the same network, CPU/memory limits (defaults
   when the old container had none), `127.0.0.1:<port>:9000` and the private
   volume. A stopped leftover with that name and revision is replaced.
6. Waits for local health `status=ok` and `revision=<sha>`.
7. Post-switch checks: `ops/complete_homeserver_api_deploy.sh` with
   `AICADDIE_DEPLOY_GATE_CHECK_ONLY=1`; the installed sync script with
   `AICADDIE_SYNC_CHECK_ONLY=1` (it must log `sync contract ok (check-only)`);
   the public health URL. Each optional check prints `skipped` when it is not
   configured.
8. Any failure or SIGTERM/SIGINT/SIGHUP in steps 5–7 removes the new
   container, restarts the previous one, re-checks its health and returns `1`
   (or `3`); further signals are ignored until the restore finishes. On the
   idempotent path a failure stops the live container and restarts the most
   recently stopped release of another revision instead (`3` if there is
   none; the live container is then left running). The post-switch checks
   also roll back: a failing sync contract means the cron job would stop
   syncing, and a failing public check means users are not served the new
   revision, even though the restored release can share the same ingress
   problem. A failed sync check prints the check-only log lines (names,
   revisions and the reason only); it uses a private lock, log and alert-state
   file so it cannot disturb the real cron state.
9. Still under the lock, keeps the newest `AICADDIE_DEPLOY_KEEP_STOPPED` stopped
   prefix containers, removes older ones with `docker rm -v`, and removes
   their `garmin-ai-caddie-api`/`aicaddie-sync` image tags only when no
   remaining container (of any name) uses the image or its revision and the
   image carries no other repository's tag. A cleanup failure is reported
   as a warning; the deploy still succeeds. Then the lock is released.

`rollback <sha>` picks the most recently stopped prefix container labelled
`<sha>`, requires its layout and port to match and `aicaddie-sync:<sha>` to
exist, takes the sync lock, stops the current container, starts the target
and waits for health. On failure it stops the target and restarts the previous
container. It never builds and never removes anything.

A run killed with `SIGKILL` mid-switch cannot restore anything. If the new
container is running, re-running `deploy <sha>` verifies it (and restores the
previous release if it fails). If the kill landed between `docker stop` and
`docker run`, nothing serves and a re-run refuses to guess; run
`rollback <previous-sha>`, which accepts an empty port.

### Environment

The executor passes only `PATH`, `HOME`, `LANG`, `AGENTHUB_PROJECT`,
`AGENTHUB_DEPLOY_SHA` and the non-secret values from its configuration. The
script never prints environment values, env-file contents, or the configured
paths and URLs; it prints container/image names and revisions only.

| Variable | Meaning | Default |
|---|---|---|
| `AICADDIE_API_PORT` | Loopback host port of the production API | `39055` |
| `AICADDIE_CONTAINER_PREFIX` | Release container name prefix (cron and gates match `aicaddie-release-`) | `aicaddie-release-` |
| `AICADDIE_DEPLOY_NETWORK` | Docker network of the API container | `garmin-ai-caddie_default` |
| `AICADDIE_PRIVATE_VOLUME` | Private named volume mounted at `/var/lib/ai-caddie` | `garmin-ai-caddie_ai-caddie-private` |
| `AICADDIE_SYNC_LOCK` | flock shared with the sync cron | `/tmp/aicaddie-sync.lock` |
| `AICADDIE_SYNC_SCRIPT` | Absolute path of the installed sync cron script, run check-only | unset: skipped |
| `AICADDIE_DEPLOY_PUBLIC_HEALTH_URL` | Public `/api/v2/health` URL | unset: skipped |
| `AICADDIE_DEPLOY_KEEP_STOPPED` | Stopped release containers kept for rollback (≥ 1) | `2` |
| `AICADDIE_DEPLOY_DEFAULT_CPUS` | CPU limit when the current container has none | `2` |
| `AICADDIE_DEPLOY_DEFAULT_MEMORY_BYTES` | Memory limit when the current container has none | `3221225472` (3 GiB) |
| `AICADDIE_DEPLOY_BOOTSTRAP_ENV_FILE` | Absolute path of an env file used only when no current container exists | unset: refuse |
| `AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS` | Local health wait (new and restored container) | `180` |
| `AICADDIE_DEPLOY_PUBLIC_HEALTH_TIMEOUT_SECONDS` | Public health wait | `60` |
| `AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS` | Wait for a running sync to release the lock | `600` |
| `AICADDIE_DEPLOY_DEADLINE_SECONDS` | Overall budget; no switch starts unless a switch plus restore still fits (keep below the executor timeout) | `2280` (38 min) |
| `AICADDIE_DEPLOY_POLL_SECONDS` | Health/lock poll interval | `2` |
| `AICADDIE_DB_CONTAINER` | Database container used during boot recovery | `garmin-ai-caddie-db-1` |
| `AICADDIE_DB_READY_TIMEOUT_SECONDS` | Maximum wait for the database to become healthy during boot recovery | `180` |
| `AICADDIE_UP_DOCKER_TIMEOUT_SECONDS` | Maximum wait for Docker during boot recovery | `300` |
| `XDG_RUNTIME_DIR` | tmpfs directory for the private env file | `/dev/shm` |

The executor must pin (sha256) every repository file that runs on the host:
`ops/agenthub_deploy.py`, `ops/build_sync_image.sh` and
`ops/complete_homeserver_api_deploy.sh`. `Dockerfile` and `Dockerfile.sync`
are build inputs that only run inside `docker build`; pinning them is optional
and would require an executor configuration change for every image change.

### Manual invocation

Run from a clean export of the merged revision, with the same environment the
executor uses:

```bash
git archive <sha> | tar -x -C <empty-dir>
cd <empty-dir>
ops/agenthub_deploy.py deploy <sha>
```

Roll back to an earlier release that is still kept as a stopped container:

```bash
ops/agenthub_deploy.py rollback <previous-sha>
```

## Boot recovery

The pinned boot unit at `ops/systemd/aicaddie-stack-up.service` runs
`agenthub_deploy.py up` from the installed copy at
`~/.local/lib/aicaddie/agenthub_deploy.py`. Install that copy and the user unit
under `~/.config/systemd/user` from the root of a clean export of the deployed
revision:

```bash
mkdir -p ~/.local/lib/aicaddie ~/.config/systemd/user
install -m 0755 ops/agenthub_deploy.py ~/.local/lib/aicaddie/agenthub_deploy.py
install -m 0644 ops/systemd/aicaddie-stack-up.service ~/.config/systemd/user/aicaddie-stack-up.service
systemctl --user daemon-reload
systemctl --user enable aicaddie-stack-up.service
loginctl enable-linger
```

Reinstall the pinned copy whenever `ops/agenthub_deploy.py` changes. Enabling
linger lets the user unit run at boot, and `agenthub_deploy.py up` waits for the
Docker daemon, the database, and the sync lock before starting a stopped API.
Read the boot recovery log with:

```bash
journalctl --user -u aicaddie-stack-up
```

### Sandbox drill

The same script can be exercised without touching production by changing
every host binding: a different `AICADDIE_API_PORT`, a different
`AICADDIE_CONTAINER_PREFIX` (for example `agenthub-drill-`), a disposable
`AICADDIE_PRIVATE_VOLUME`, `AICADDIE_DEPLOY_NETWORK=bridge`, a private
`AICADDIE_SYNC_LOCK`, no `AICADDIE_DEPLOY_PUBLIC_HEALTH_URL`, and a
`AICADDIE_DEPLOY_BOOTSTRAP_ENV_FILE` with fixture-only settings (for example a
SQLite `AI_CADDIE_DATABASE_URL`, `AI_CADDIE_DATA_MODE=fixture`, a
throwaway admin token) for the first run. Images are keyed by revision and
are shared with production; cleanup never removes an image that a remaining
container uses, but do not run a drill concurrently with a production
deploy. If a drill's cleanup removes images a production deploy has just
built, the deploy notices under the lock and fails without switching; a
re-run rebuilds them.

## GitHub Actions

The default CI can be run manually from GitHub Actions because the workflow has
`workflow_dispatch`. It runs fixture-backed backend/frontend checks on Ubuntu
and native iOS/Watch simulator tests on `macos-15`; it must not receive real
Garmin session material.
