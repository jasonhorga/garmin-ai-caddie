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
- Provider selection is controlled by `AI_CADDIE_LLM_PROVIDER` (`static`, `anthropic`, `nvidia_nim`, `gemini_api_key`, or local/development `gemini_cli_oauth`).
- NVIDIA NIM uses `NVIDIA_NIM_BASE_URL` and `NVIDIA_NIM_MODEL` beside `NVIDIA_API_KEY`.
- Gemini API-key mode uses `GEMINI_API_KEY`, optional `GEMINI_API_BASE_URL`, and optional `GEMINI_MODEL`.
- Gemini CLI OAuth mode uses `GEMINI_OAUTH_CREDENTIALS_FILE`, `GEMINI_OAUTH_CREDENTIALS_JSON`, or `GEMINI_OAUTH_CREDENTIALS_B64` plus `GOOGLE_CLOUD_PROJECT` and optional `GEMINI_MODEL`.
- Gemini CLI OAuth credentials are token material, not a public login flow. Store them only in local protected files or deployment secret stores, and do not expose them through Web/iOS settings.
- Test fixtures use static providers and must not require external model keys.
- Provider errors should be redacted before returning through APIs or logs.

## Garmin OAuth Feasibility Probe

- Official Garmin OAuth remains a feasibility track until golf scorecards, shots, and course metadata are proven for a consented account.
- Probe configuration uses `AI_CADDIE_GARMIN_OAUTH_CLIENT_ID`, `AI_CADDIE_GARMIN_OAUTH_CLIENT_SECRET`, and `AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI`. `AI_CADDIE_GARMIN_OAUTH_AUTH_URL`, `AI_CADDIE_GARMIN_OAUTH_TOKEN_URL`, `AI_CADDIE_GARMIN_OAUTH_API_BASE_URL`, `AI_CADDIE_GARMIN_OAUTH_USER_ID_URL`, and `AI_CADDIE_GARMIN_OAUTH_PERMISSIONS_URL` are override hooks; the code defaults to Garmin's OAuth2 PKCE, token, user id, and permissions endpoints.
- `ops/probe_garmin_oauth.py authorize` prints a local PKCE consent URL and private code verifier. Keep the verifier private.
- `ops/probe_garmin_oauth.py exchange --code ... --code-verifier ...` sets `AI_CADDIE_GARMIN_OAUTH_LIVE_PROBE=1` for that local command and returns a secret-free result with token receipt booleans, user-id fingerprint, permissions, and capability findings.
- Sync status may expose boolean readiness, redacted consent-request preview, and the live-probe contract, but it must not echo the client id, client secret, authorization code, code verifier, tokens, redirect URI, or raw user id.
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
