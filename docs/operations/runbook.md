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

## Stop Services

Stop foreground dev servers with `Ctrl-C`. For background processes, find and stop the process explicitly:

```bash
pgrep -af 'uvicorn server_v2.main:app'
```

## Refresh Garmin Session

Use browser session import first:

```bash
uv run python garmin_auth.py
uv run python fetch.py --refresh-auth
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

Restore:

```bash
uv run python ops/import_snapshot.py backups/ai-caddie-snapshot-YYYYMMDDTHHMMSSZ.tar.gz --target-root .
```

## Inspect Sync Status

```bash
curl -s http://127.0.0.1:9000/api/v2/sync/status
```

The response should never include cookie, CSRF, token, `.env`, or absolute private paths.
