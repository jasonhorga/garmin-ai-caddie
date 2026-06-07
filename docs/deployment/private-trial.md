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

The smoke keeps ordinary endpoint requests on a short timeout. If the first
`/api/v2/readiness` call is cold on a small host, raise only that budget with
`AI_CADDIE_SMOKE_READINESS_TIMEOUT_SECONDS=90`; `AI_CADDIE_SMOKE_TIMEOUT_SECONDS`
controls the default per-request timeout.

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

The same Fly deployment can run from GitHub after these repo secrets exist:

- `FLY_API_TOKEN`
- `AI_CADDIE_ADMIN_TOKEN`

Run the manual `Backend Fly Deploy` workflow with the target `app_name`. It
creates the Fly app if needed using the selected `fly_org`, creates the
`ai_caddie_private` volume if needed,
sets the private runtime secrets, runs `flyctl deploy --remote-only`, updates
the repo variable `AI_CADDIE_API_BASE_URL` to the deployed HTTPS origin, then
runs the remote private-trial smoke and Phase 6 preflight. The workflow uploads
`private-trial-smoke.json` and `phase6_external_readiness_latest.json` as
evidence artifacts and does not print secret values.

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
AI_CADDIE_TESTFLIGHT_TESTER_COUNT=<confirmed-target-tester-count> \
AI_CADDIE_TESTFLIGHT_BETA_REVIEW_READY=0 \
AI_CADDIE_TESTFLIGHT_BETA_REVIEW_SUBMITTED=0 \
AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED=0 \
uv run python ops/phase6_external_readiness.py \
  --api-base-url https://<Render API URL or Fly API URL origin> \
  --probe-backend \
  --output logs/phase6_external_readiness_latest.json
```

The API readiness endpoint reports this file as the `external_release` check.

The preflight stays `incomplete` until all external gates are actually true:

- the six long-lived signing secrets are configured
- repo variable `AI_CADDIE_API_BASE_URL` points at the deployed API origin, or
  the TestFlight workflow `api_base_url` input is provided for that build, or
  the iPhone app runtime Backend screen is confirmed configured for the deployed
  API origin
- the backend probe can reach `/api/v2/health` and authenticated
  `/api/v2/readiness`
- `TESTFLIGHT_FEEDBACK_EMAIL` is set or the Beta App feedback email is filled
  manually in App Store Connect
- App Store Connect reports the build as ready for external Beta Review
  submission (`READY_FOR_BETA_SUBMISSION`)
- external Beta App Review has been submitted or the build is already
  externally reviewable
- target testers are added or internal tester coverage is confirmed
- iPhone/watch TestFlight installation has been verified

`VITE_AI_CADDIE_API_BASE_URL` only proves the Web build can target the deployed
API. It does not satisfy native TestFlight configuration; the iOS/watch build
must use `AI_CADDIE_API_BASE_URL`, the TestFlight workflow `api_base_url`
input, or the iPhone app runtime Backend screen.

Use an origin-only API URL such as `https://api.example.com`, with no path,
query string, fragment, or URL credentials. The preflight rejects values such as
`https://api.example.com/private`, `https://api.example.com?token=...`, and
`https://user:pass@api.example.com` so secret-bearing URLs cannot leak into
build settings or readiness evidence.

When `GH_TOKEN` can read GitHub Actions variables, the preflight uses the
`AI_CADDIE_API_BASE_URL` repo variable value as the probe URL and reports only
its host. If that value is unavailable to the GitHub API, pass the same URL with
`--api-base-url` for the preflight run.

With the same read-only GitHub metadata token, the preflight also inspects recent
`iOS TestFlight Testers` workflow logs and records a safe summary when App Store
Connect reports `READY_FOR_BETA_SUBMISSION`. It stores only build/status enums
and a run-id source, never tester email addresses or raw log lines.
The same log summary can record that app-level TestFlight tester records and the
`Private Trial` group exist, but app-level tester records alone do not satisfy
target tester coverage; the gate stays open until group assignment or internal
coverage is confirmed.
If the target testers already exist at the app level, run the GitHub
`iOS TestFlight Testers` workflow with `operation=assign_existing` and
`groups=Private Trial`. Its successful log records the group assignment count
without exposing raw tester email addresses, and that count can satisfy target
tester coverage.

The backend probe does not count as ready unless `AI_CADDIE_ADMIN_TOKEN` is
provided; public `/api/v2/readiness` alone is not enough for the external
release gate. The probed API must also return the expected
`ai-caddie-health-v2` and `ai-caddie-readiness-v1` schemas.

If feedback email, native runtime backend setup, or tester coverage is completed
manually outside GitHub secrets/variables, record that in the preflight run with
`--feedback-email-filled`, `--native-runtime-api-configured`,
`--beta-review-ready`, `--beta-review-submitted`,
`--assigned-tester-count <count>`, and `--tester-coverage-confirmed`.
Use the matching source-label flags (`--feedback-email-source`,
`--native-runtime-api-source`, `--beta-review-ready-source`,
`--beta-review-source`, `--assigned-tester-source`,
`--tester-coverage-source`, and `--install-source`) to identify safe evidence
such as `testflight_backend_screen`,
`app_store_connect_beta_review_submitted`, or
`testflight_iphone_watch_install`.
Do not put tester email addresses, tokens, or local filesystem paths in source
labels; the preflight redacts those values before printing JSON.
`--assigned-tester-count` is only for target testers confirmed assigned to
`Private Trial` or otherwise covered internally; do not pass app-level
`observedAppTesterCount` here. `--beta-review-ready` records
`READY_FOR_BETA_SUBMISSION` when the GitHub log summary is unavailable; it does
not prove the Beta App feedback email is configured and does not replace `--beta-review-submitted`.
After `READY_FOR_BETA_SUBMISSION` is known and the feedback-email gate is ready,
the remaining review action is only to submit external Beta App Review.
Manual confirmations are recorded with a confirmation source in the JSON
evidence so they are distinguishable from GitHub secrets, repo variables, and
backend probe results. A numeric `AI_CADDIE_TESTFLIGHT_TESTER_COUNT` is treated
as a confirmed target tester count and recorded with a source so the evidence
distinguishes CLI-entered counts from environment-provided counts. The older
`--tester-count` flag remains a compatibility alias for this confirmed-target
meaning, not for app-level tester records.

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
