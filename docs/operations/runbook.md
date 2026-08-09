# Operations Runbook

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

The shared API entrypoint honors `AI_CADDIE_PRIVATE_ROOT` and symlinks private
runtime directories from that root into the application root before starting
FastAPI. It then runs the Alembic migrations and the idempotent identity seeder;
Render, Fly, Docker, and direct script starts therefore use the same cold-start
path. Use this
for NAS/Fly/VPS deployments so downloaded Garmin data and session material are
kept on persistent storage instead of inside the image.

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
The exporter excludes `.garmin_tokens` at every directory depth and re-opens the
finished tarball before setting `secretFree=true`.

The identity store is included as well:

- A file-backed SQLite identity database is copied with SQLite's online backup
  API into `data/identity.db`, including committed WAL state.
- A configured PostgreSQL identity database is dumped with `pg_dump` into
  `data/identity.pg_dump`. If `pg_dump` is unavailable or the dump fails, the
  entire backup fails instead of publishing an incomplete manifest. Run the
  script from the API container or another trusted machine with a compatible
  PostgreSQL client.

Restore:

```bash
uv run python ops/import_snapshot.py backups/ai-caddie-snapshot-YYYYMMDDTHHMMSSZ.tar.gz --target-root .
```

Stop the API before replacing a live SQLite database. For PostgreSQL, import the
tarball into a staging directory and restore the extracted custom-format dump
into the intended empty database with `pg_restore`; use a libpq-compatible
`postgresql://...` value in `PGDATABASE`. Restoring files alone does not modify
an external PostgreSQL service.

## Inspect Sync Status

```bash
curl -s http://127.0.0.1:9000/api/v2/sync/status
```

The response should never include cookie, CSRF, token, `.env`, or absolute private paths.

## GitHub Actions

The default CI can be run manually from GitHub Actions because the workflow has
`workflow_dispatch`. It runs fixture-backed backend/frontend checks on Ubuntu
and native iOS/Watch simulator tests on `macos-15`; it must not receive real
Garmin session material.
