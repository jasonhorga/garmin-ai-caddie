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
- Provider selection is controlled by `AI_CADDIE_LLM_PROVIDER` (`static`, `anthropic`, `nvidia_nim`, `gemini_api_key`, or internal-only `gemini_cli_oauth`).
- NVIDIA NIM uses `NVIDIA_NIM_BASE_URL` and `NVIDIA_NIM_MODEL` beside `NVIDIA_API_KEY`.
- Gemini API-key mode uses `GEMINI_API_KEY`, optional `GEMINI_API_BASE_URL`, and optional `GEMINI_MODEL`.
- Test fixtures use static providers and must not require external model keys.
- Provider errors should be redacted before returning through APIs or logs.

## Garmin OAuth Feasibility Probe

- Official Garmin OAuth remains a feasibility track until golf scorecards, shots, and course metadata are proven for a consented account.
- Probe configuration uses `AI_CADDIE_GARMIN_OAUTH_CLIENT_ID`, `AI_CADDIE_GARMIN_OAUTH_CLIENT_SECRET`, `AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI`, `AI_CADDIE_GARMIN_OAUTH_AUTH_URL`, `AI_CADDIE_GARMIN_OAUTH_TOKEN_URL`, and `AI_CADDIE_GARMIN_OAUTH_SCOPES`.
- `AI_CADDIE_GARMIN_OAUTH_LIVE_PROBE=1` only marks that a manual live probe is allowed; automated tests must not call Garmin OAuth.
- Sync status may expose boolean readiness and a redacted consent-request preview, but it must not echo the client id, client secret, tokens, redirect URI, or raw scopes.
- OAuth feasibility must not replace the CN Web Session connector until it can sync the required golf history data.

## Admin Protection

- Set `AI_CADDIE_ADMIN_TOKEN` for any private, staging, or production deployment.
- Set `AI_CADDIE_SECURITY_PROFILE=private`, `staging`, or `production` to make protected routes fail closed if the admin token is missing.
- Protected mobile, media, annotation, report, sync, weather-persist, geometry-ensure, and caddie mutation routes require `X-AI-Caddie-Admin-Token` when an admin token is configured.
- Do not reuse the Garmin cookie, CSRF token, or an AI provider key as the admin token.

## Snapshot Exports

`ops/export_snapshot.py` includes only:

- `data/summary.json`
- `data/scorecards`
- `data/shots`
- `data/snapshots`
- `data/sync`
- `data/annotations`
- `data/media` metadata and local uploaded media files
- `data/mobile_events`
- `data/weather`
- `data/reports`
- `data/decision_audits`

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
