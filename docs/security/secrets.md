# Secret Handling

This project is designed for private golf data first. Secrets must stay local or inside the deployment provider's secret manager.

## Garmin Auth

- Do not store a Garmin username or password in cloud config.
- The CN connector uses a web session cookie plus `connect-csrf-token`.
- Local session material belongs under `.garmin_tokens/` with restrictive permissions.
- API responses must never echo cookie, CSRF, token, or absolute local paths.
- If Garmin auth expires, the connector should return `reauth_required`; unrelated fixture and history tests must still pass.

## AI Provider Keys

- `NVIDIA_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, and `ANTHROPIC_API_KEY` belong in local `.env` files or hosted secret stores.
- Test fixtures use static providers and must not require external model keys.
- Provider errors should be redacted before returning through APIs or logs.

## Snapshot Exports

`ops/export_snapshot.py` includes only:

- `data/summary.json`
- `data/scorecards`
- `data/shots`
- `data/snapshots`
- `data/sync`
- `data/annotations`
- `data/media` metadata and local uploaded media files

It excludes by default:

- `.garmin_tokens`
- `.env` and `.env.*`
- `clubs.json`

Use `--include-clubs` only for a private backup target you control.

## Local Ignore Rules

The following should remain ignored by git:

- `.garmin_tokens/`
- `.env`
- `clubs.json`
- `data/`
- `output/`
- `logs/`
- `backups/`
