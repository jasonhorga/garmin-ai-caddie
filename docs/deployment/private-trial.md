# Private Trial Deployment

The recommended trial path is staged and reversible.

## Staging First

Use a Render-style API service and a Vercel-style web frontend for early testing. Keep Garmin session material and AI provider keys in the platform secret manager. Do not upload private raw data unless the deployment is locked down and intentionally configured for it.

Machine-readable starting points are committed:

- API: `render.yaml`
- API container: `Dockerfile`
- API Fly.io starter: `fly.toml`
- Local container stack: `docker-compose.yml`
- Web: `web_v2/vercel.json`
- Local/private env template: `.env.example`

Required API environment for private staging:

- `AI_CADDIE_SECURITY_PROFILE=private`
- `AI_CADDIE_ADMIN_TOKEN=<random private token>`
- `AI_CADDIE_DATA_MODE=local_or_fixture`
- `AI_CADDIE_CORS_ORIGINS=<Vercel Web URL>`
- Optional for Vercel preview URLs: `AI_CADDIE_CORS_ORIGIN_REGEX=https://.*\.vercel\.app`
- Optional AI provider: `AI_CADDIE_LLM_PROVIDER=gemini_api_key` with `GEMINI_API_KEY`, or internal-only `AI_CADDIE_LLM_PROVIDER=gemini_cli_oauth` with `GEMINI_OAUTH_CREDENTIALS_B64` and `GOOGLE_CLOUD_PROJECT`. Gemini CLI OAuth refresh requires the credential payload to include its own OAuth client id and client credential fields.

Required Web environment for private staging:

- `VITE_AI_CADDIE_API_BASE_URL=<Render API URL>`
- `VITE_AI_CADDIE_API_BASE_URL=<Fly API URL>` if Fly is the API host

The Vercel Web URL must be allowed by the Render API through
`AI_CADDIE_CORS_ORIGINS`; the Web build must point at the Render API URL through
`VITE_AI_CADDIE_API_BASE_URL`. Without those paired settings, the static Web app
will either request its own Vercel origin or be blocked by browser CORS.

## Local Private Smoke

Before using Render, Fly, or Vercel, run the private API locally with the same
security profile and runtime root shape:

```bash
AI_CADDIE_SECURITY_PROFILE=private \
AI_CADDIE_ADMIN_TOKEN=replace-with-random-admin-token \
AI_CADDIE_DATA_MODE=local_or_fixture \
AI_CADDIE_PRIVATE_ROOT=/var/lib/ai-caddie \
uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9000
```

In another shell, run the protected-route smoke:

```bash
AI_CADDIE_ADMIN_TOKEN=replace-with-random-admin-token \
ops/smoke_private_trial.sh http://127.0.0.1:9000
```

Record a backup and prove snapshot portability before replacing private runtime
state:

```bash
ops/backup_data.sh
uv run python ops/export_snapshot.py --source-root . --output data/backups/private-snapshot.tar.gz
uv run python ops/import_snapshot.py data/backups/private-snapshot.tar.gz --target-root /tmp/ai-caddie-restore-check
```

## Container Staging

For a non-Render API trial, build and run the same container locally, on a NAS,
on Fly.io, or on a small VPS:

```bash
cp .env.example .env
# edit .env; do not commit it
docker compose up --build
```

Open:

- API: `http://127.0.0.1:9000`
- Web: `http://127.0.0.1:5173`

The compose API stores private runtime state in the `ai-caddie-private` volume
and maps it into the app through `AI_CADDIE_PRIVATE_ROOT`. This keeps Garmin
session material, downloaded Garmin data, generated output, logs, and backups
out of the image.

Fly.io can use the committed `fly.toml` as a starting point:

```bash
fly volumes create ai_caddie_private --size 3 --region sin
fly secrets set AI_CADDIE_ADMIN_TOKEN=<random private token>
fly deploy
```

Add AI provider keys with `fly secrets set ...` only when the corresponding
provider is needed. Garmin CN session material should still be imported through
the private Web/iOS flow, not committed into the image.

Render, Fly, and Vercel CLI deployment commands should only run when provider
credentials are already configured in the environment. Use the resulting
Render API URL or Fly API URL as `VITE_AI_CADDIE_API_BASE_URL`, and allow the
Vercel Web URL through API CORS.

TestFlight signing and distribution are excluded from routine private-trial
deployment. Run those workflows only after an explicit native release request
and Apple credential setup.

## Phase 6 External Release Preflight

After a backend host exists and before uploading a connected TestFlight build,
run the external release preflight. It prints only configuration state, host
names, status codes, and counts; it does not print secret values or tester email
addresses.

```bash
GH_TOKEN=<github-token-with-repo-metadata-read> \
AI_CADDIE_ADMIN_TOKEN=<deployed-api-admin-token> \
AI_CADDIE_TESTFLIGHT_TESTER_COUNT=<number-of-target-testers> \
AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED=0 \
uv run python ops/phase6_external_readiness.py \
  --api-base-url https://<Render API URL or Fly API URL> \
  --probe-backend
```

The preflight stays `incomplete` until all external gates are actually true:

- the six long-lived signing secrets are configured
- repo variable `AI_CADDIE_API_BASE_URL` points at the deployed API, or the
  TestFlight workflow `api_base_url` input is provided for that build
- the backend probe can reach `/api/v2/health` and authenticated
  `/api/v2/readiness`
- `TESTFLIGHT_FEEDBACK_EMAIL` is set or the Beta App feedback email is filled
  manually in App Store Connect
- target testers are added or internal tester coverage is confirmed
- iPhone/watch TestFlight installation has been verified

If feedback email or tester coverage is completed manually outside GitHub
secrets, record that in the preflight run with `--feedback-email-filled` and
`--tester-coverage-confirmed`.

When the phone/watch install has been verified, rerun with
`AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED=1` or `--install-verified` and record the
JSON output in the Phase 6 evidence.

## NAS Or Private Server

A NAS or private server is suitable once local use is stable:

- Run the FastAPI service on `127.0.0.1:9000` behind a reverse proxy or VPN.
- Keep `AI_CADDIE_SECURITY_PROFILE=private` enabled so protected routes fail closed if `AI_CADDIE_ADMIN_TOKEN` is accidentally removed.
- Keep `data/`, `.garmin_tokens/`, and backups on encrypted storage when possible.
- Use `ops/backup_data.sh` before changing sync or import workflows.
- Expose only HTTPS if using a public IP or port forwarding.

## SSH Tunnel Development

For remote development:

```bash
ssh -L 9000:127.0.0.1:9000 -L 5173:127.0.0.1:5173 user@server
```

Then open:

- API: `http://127.0.0.1:9000`
- Web: `http://127.0.0.1:5173`

## Offline-First Mobile Caveat

The iOS and Watch app path should cache a live round package before play. During a round, GPS and score/club input must continue without network. The backend sync can run after the phone regains network access.
