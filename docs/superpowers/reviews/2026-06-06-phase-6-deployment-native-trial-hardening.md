# Phase 6 Deployment Native Trial Hardening Evidence

- Date: 2026-06-06
- Branch: `integration/v2`

## Scope

Implemented the locally verifiable Phase 6 hardening work from
`docs/superpowers/specs/2026-06-06-phase-6-deployment-native-trial-hardening-design.md`.

## Evidence

- Deployment runbook documents local private API, Render, Fly, Vercel, smoke,
  backup, export, and import commands.
- Deployment manifests define private runtime roots, health checks,
  admin-token placeholders, and no Garmin credentials.
- Current `Dockerfile` builds a local API image that can serve health and
  readiness through the container entrypoint.
- Backup/export/import exclude secrets, reject unsafe paths, return portable
  manifest metadata, and expose snapshot acceptance evidence in readiness.
- Private trial smoke writes secret-free evidence with endpoint counts,
  admin-protected endpoint counts, media round-trip status, and redaction checks.
- Native workflows remain manual or native-path gated; TestFlight and signing
  bootstrap are manual only.
- Native build evidence writer rejects private paths and secret-looking markers.
- Readiness reports backup, smoke, snapshot acceptance, native evidence, and
  degraded reasons without private paths or credential material.
- `garmin-ai-caddie` is now public with default branch `integration/v2`, so the
  public-repo GitHub-hosted macOS workflow can run without private Actions
  minute pressure.
- TestFlight signing is isolated in private repo
  `jasonhorga/garmin-ai-caddie-signing`, not reused from `gomoku`.
- The repo has the required GitHub Actions secret names for signing:
  `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_PRIVATE_KEY`, `MATCH_GIT_URL`,
  `MATCH_GIT_PRIVATE_KEY`, `MATCH_PASSWORD`, and `MATCH_KEYCHAIN_PASSWORD`.
- `iOS Signing Bootstrap (one-time)` succeeded on `integration/v2`, proving
  App Store distribution cert/profile generation for `com.ai-caddie.mobile`
  and `com.ai-caddie.mobile.watchkitapp`.
- `iOS TestFlight (CD)` reached archive/export and produced a signed IPA
  artifact before upload. Upload is blocked only because App Store Connect does
  not yet have an app record for `com.ai-caddie.mobile`.

## GitHub Actions Guardrail

GitHub API inspection on 2026-06-06 showed:

- `iOS TestFlight (CD)` had 4 historical push-triggered runs, all failures.
- `CI` had 78 historical runs, including older push and PR runs.
- Action artifacts were not the storage issue: 51 artifacts totaled about 23 KB.
- Action caches were the storage issue: 38 caches totaled about 3.0 GB, mostly
  `setup-uv` and `node` caches on old `superpowers/*` refs.

Fix applied and pushed:

- `ios-testflight.yml` is now `workflow_dispatch` only.
- `ci.yml` remains `workflow_dispatch` and `pull_request` only.
- `native-mobile.yml` remains `workflow_dispatch` and native-path PR only.
- The push containing this fix did not create a new Actions run.

After the storage investigation, old Actions caches were cleaned by explicit
user request:

- `jasonhorga/gomoku`: 9 caches removed, about 6.21 GB released.
- `jasonhorga/garmin-ai-caddie` `refs/heads/superpowers/*`: 32 caches
  removed, about 2.78 GB released.
- No source branches, releases, packages, or code were deleted.

## Verification

```bash
AI_CADDIE_SECURITY_PROFILE=private AI_CADDIE_ADMIN_TOKEN=ci-admin-token AI_CADDIE_DATA_MODE=fixture uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9000
```

Result: PASS. Local private fixture API served `/api/v2/health` on
`http://127.0.0.1:9000`.

```bash
AI_CADDIE_ADMIN_TOKEN=ci-admin-token AI_CADDIE_PRIVATE_SMOKE_EVIDENCE=/tmp/ai-caddie-private-trial-smoke.json ops/smoke_private_trial.sh http://127.0.0.1:9000
```

Result: PASS. Evidence schema `ai-caddie-private-trial-smoke-evidence-v1`,
`endpointCount=14`, `adminProtectedEndpointCount=11`, `mediaRoundTrip=true`,
`secretFree=true`.

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/source/data/scorecards" "$tmp/source/data/shots" "$tmp/source/output/prodgeometry_hazards" "$tmp/source/.garmin_tokens"
printf '{}' > "$tmp/source/data/scorecards/1.json"
printf '{}' > "$tmp/source/data/shots/1.json"
printf '{"hazards":[]}' > "$tmp/source/output/prodgeometry_hazards/gid1_h01_hazards.json"
printf 'cookie' > "$tmp/source/.garmin_tokens/web_cookie.txt"
printf 'SECRET=1' > "$tmp/source/.env"
uv run python ops/export_snapshot.py --source-root "$tmp/source" --output "$tmp/snapshot.tar.gz"
uv run python ops/import_snapshot.py "$tmp/snapshot.tar.gz" --target-root "$tmp/restore"
```

Result: PASS. Exported archive contained only:

```text
data/scorecards/1.json
data/shots/1.json
output/prodgeometry_hazards/gid1_h01_hazards.json
```

The `.garmin_tokens` and `.env` files were not restored.

```bash
uv run python -m unittest tests.test_deployment_manifests tests.test_snapshot_import_export tests.test_server_v2_readiness tests.test_ci_workflow tests.test_native_build_evidence -v
```

Result: PASS, 41 tests in 23.064s.

```bash
git diff --check
```

Result: PASS.

```bash
curl -fsS -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/jasonhorga/garmin-ai-caddie/actions/secrets
```

Result: PASS. GitHub returned 7 signing secret names:
`ASC_ISSUER_ID`, `ASC_KEY_ID`, `ASC_PRIVATE_KEY`, `MATCH_GIT_PRIVATE_KEY`,
`MATCH_GIT_URL`, `MATCH_KEYCHAIN_PASSWORD`, and `MATCH_PASSWORD`.

```bash
curl -fsS -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/jasonhorga/garmin-ai-caddie-signing/commits?per_page=3
```

Result: PASS. Signing repo latest commit:
`722f989440a4ced8ddec2e098587a5b39c06a449`, message
`[fastlane] Updated appstore and platform ios`, dated
`2026-06-06T16:59:22Z`.

```text
GitHub Actions run 27068364435
Workflow: iOS Signing Bootstrap (one-time)
Ref: integration/v2
Conclusion: success
Started: 2026-06-06T16:58:40Z
Completed: 2026-06-06T16:59:26Z
```

Result: PASS. Job `bootstrap` completed successfully. Steps
`Validate signing secrets` and `fastlane bootstrap_signing` both succeeded.

```text
GitHub Actions run 27068471126
Workflow: iOS TestFlight (CD)
Ref: integration/v2
Conclusion: failure
Artifact: AICaddie-ipa, 1,236,710 bytes, created 2026-06-06T17:04:29Z
```

Result: PARTIAL PASS. The workflow installed match signing assets, archived the
iOS + watch app, and exported a signed IPA at `build/ios/AICaddie.ipa`.
It failed only at `upload_to_testflight` with:

```text
Couldn't find app 'com.ai-caddie.mobile' on the account of '' on App Store Connect
```

The successful bootstrap log also showed why the app record must be created
manually:

```text
The resource 'apps' does not allow 'CREATE'. Allowed operations are:
GET_COLLECTION, GET_INSTANCE, UPDATE
```

```bash
docker run --rm --name ai-caddie-api-smoke -p 127.0.0.1:9000:9000 -e AI_CADDIE_SECURITY_PROFILE=private -e AI_CADDIE_ADMIN_TOKEN=container-smoke-token -e AI_CADDIE_DATA_MODE=fixture -e AI_CADDIE_LLM_PROVIDER=static ai-caddie-api:config-check
curl -fsS http://127.0.0.1:9000/api/v2/health
curl -fsS -H 'X-AI-Caddie-Admin-Token: container-smoke-token' http://127.0.0.1:9000/api/v2/readiness
```

Result: PASS using the pre-existing local `ai-caddie-api:config-check` image.
Health returned schema `ai-caddie-health-v2` with status `ok`; readiness returned
schema `ai-caddie-readiness-v1` with 12 checks and status `degraded`.

```bash
docker build -t ai-caddie-api:phase6-current .
docker run --rm --name ai-caddie-api-phase6-current -p 127.0.0.1:9000:9000 -e AI_CADDIE_SECURITY_PROFILE=private -e AI_CADDIE_ADMIN_TOKEN=container-smoke-token -e AI_CADDIE_DATA_MODE=fixture -e AI_CADDIE_LLM_PROVIDER=static ai-caddie-api:phase6-current
curl -fsS http://127.0.0.1:9000/api/v2/health
curl -fsS -H 'X-AI-Caddie-Admin-Token: container-smoke-token' http://127.0.0.1:9000/api/v2/readiness
```

Result: PASS. Current Dockerfile built image
`sha256:8eda589e6f296d3f7ab0e64a8d3623b900834910dd1d35668a82ca252e6a1192`
at `2026-06-06T07:14:46Z`, size about 396 MB. Health returned schema
`ai-caddie-health-v2` with status `ok`; readiness returned schema
`ai-caddie-readiness-v1` with 13 checks and status `degraded`. Root filesystem
usage remained 52% after the build.

## Not Run

- Full private-root snapshot export/import with `--source-root .` was not
  completed in this pass after the GitHub storage investigation. Local private
  roots are about 4.3 GB before compression (`data` about 1.2 GB and `output`
  about 3.1 GB), so the evidence above uses a bounded CLI smoke plus the full
  deterministic unit suite. Run `ops/backup_data.sh` on the deployment host
  before replacing live private runtime state.
- Cloud deployment to Render/Fly/Vercel was not run because provider
  credentials or an already configured deploy session were not available in
  this workspace.
- Xcode simulator tests require macOS/Xcode and were not executable in this
  Linux workspace. The GitHub macOS TestFlight workflow did compile/archive the
  release app after signing was configured.
- TestFlight upload is blocked until a one-time App Store Connect app record
  exists for bundle ID `com.ai-caddie.mobile`. Create it in App Store Connect,
  then rerun `iOS TestFlight (CD)` on `integration/v2`; signing bootstrap does
  not need to be rerun.
