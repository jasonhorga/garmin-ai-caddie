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
