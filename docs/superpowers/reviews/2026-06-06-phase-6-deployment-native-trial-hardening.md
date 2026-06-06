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
- The TestFlight signing workflows require six long-lived GitHub Actions secret
  names:
  `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_PRIVATE_KEY`, `MATCH_GIT_URL`,
  `MATCH_GIT_PRIVATE_KEY`, and `MATCH_PASSWORD`. The CI keychain password is
  generated per run; a previously configured `MATCH_KEYCHAIN_PASSWORD` may still
  exist in GitHub settings but is no longer read by the workflows.
- `iOS Signing Bootstrap (one-time)` succeeded on `integration/v2`, proving
  App Store distribution cert/profile generation for `com.ai-caddie.mobile`
  and `com.ai-caddie.mobile.watchkitapp`.
- `iOS TestFlight (CD)` now archives, exports, and uploads the signed iOS +
  watch IPA to App Store Connect/TestFlight.
- `iOS TestFlight (CD)` can bake a public native backend URL into the iOS app
  through workflow input `api_base_url` or repo variable
  `AI_CADDIE_API_BASE_URL`; the app reads `AICaddieAPIBaseURL` from
  `Info.plist` and still falls back to offline/fixture mode when blank.
- `iOS TestFlight Testers` can now query App Store Connect/TestFlight through
  direct Spaceship ConnectAPI calls without the obsolete `pilot builds/list`
  paths.
- External TestFlight distribution now has an explicit secret-only feedback
  email guard: set `TESTFLIGHT_FEEDBACK_EMAIL` before submitting Beta App
  Review. The value is not accepted as workflow input because the repo is
  public.
- Export compliance is configured for the current app/watch build as exempt:
  both native `Info.plist` files declare `ITSAppUsesNonExemptEncryption=false`,
  the TestFlight tester workflow sets `usesNonExemptEncryption=false`, and the
  App Store Connect encryption form should use the option equivalent to none of
  the listed encryption algorithms for this build.

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

Result: PASS. GitHub returned 7 configured secret names:
`ASC_ISSUER_ID`, `ASC_KEY_ID`, `ASC_PRIVATE_KEY`, `MATCH_GIT_PRIVATE_KEY`,
`MATCH_GIT_URL`, `MATCH_KEYCHAIN_PASSWORD`, and `MATCH_PASSWORD`.
Only six of these are long-lived signing requirements:
`ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_PRIVATE_KEY`, `MATCH_GIT_URL`,
`MATCH_GIT_PRIVATE_KEY`, and `MATCH_PASSWORD`. `MATCH_KEYCHAIN_PASSWORD` is a
legacy configured secret; the workflows no longer read it because the keychain
password is generated per run.

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
GitHub Actions run 27068933612
Workflow: iOS TestFlight (CD)
Ref: integration/v2
Head SHA: 3a3d334888fd2ea1ffb2d6a200e7f75c922d2086
Conclusion: success
Artifact: AICaddie-ipa, 1,572,687 bytes, created 2026-06-06T17:26:49Z
App Store Connect app id: 6777484211
Version: 0.1.0
Build: 2
```

Result: PASS. The workflow installed match signing assets, archived the iOS +
watch app, exported a signed IPA at `build/ios/AICaddie.ipa`, and uploaded it to
App Store Connect/TestFlight. Fastlane logged:

```text
Successfully uploaded package to App Store Connect. It might take a few minutes until it's visible online.
Successfully uploaded the new binary to App Store Connect
fastlane.tools finished successfully
```

The uploaded IPA artifact was inspected after download. It contains:

```text
Payload/AICaddie.app/Assets.car
Payload/AICaddie.app/Watch/AICaddieWatch.app/Assets.car
Payload/AICaddie.app/live_round_package.fixture.json
```

Both app plists include `CFBundleIconName=AppIcon`; the iOS plist includes the
required iPad orientation declarations.

```text
GitHub Actions run 27069928781
Workflow: iOS TestFlight Testers
Ref: integration/v2
Head SHA: 1a9fc374856e0b51e63089385a4ef0080d3b463d
Operation: list
Conclusion: success
Completed: 2026-06-06T18:08:03Z
```

Result: PASS. The latest secret-only workflow authenticated to App Store
Connect, listed app `AI Caddie` (`com.ai-caddie.mobile`, id `6777484211`), and
found build `0.1.0 (2)` with:

```text
state=VALID
expired=false
usesNonExemptEncryption=false
internalState=IN_BETA_TESTING
externalState=READY_FOR_BETA_SUBMISSION
autoNotify=false
missingExportCompliance=false
```

The current TestFlight group list contains internal group `Jason's friends`
with `allBuilds=true` and external group `Private Trial`
(`internal=false`, `publicLinkEnabled=false`). The app tester list returned
2 existing testers; workflow logs redact tester email addresses.

```text
GitHub Actions run 27069707759
Workflow: iOS TestFlight Testers
Operation: distribute
Conclusion: failure
Completed: 2026-06-06T17:58:15Z
```

Result: FAIL, expected setup gap. App Store Connect rejected Beta App Review
submission because the Beta App Description was missing. The workflow was then
updated to create a minimal secret-free beta app description automatically.

```text
GitHub Actions run 27069752243
Workflow: iOS TestFlight Testers
Operation: distribute
Conclusion: failure
Completed: 2026-06-06T18:00:16Z
```

Result: FAIL, expected setup gap. The workflow created the `en-US` Beta App
Description, but App Store Connect still rejected submission because beta app
localization metadata was not yet accepted by the review-submission endpoint.
The workflow was then updated to retry metadata propagation.

```text
GitHub Actions run 27069792150
Workflow: iOS TestFlight Testers
Operation: distribute
Conclusion: failure
Completed: 2026-06-06T18:02:19Z
```

Result: FAIL, expected setup gap. Retrying proved the remaining missing external
TestFlight test-information requirement is the Beta App feedback email. The
workflow now requires the repo secret `TESTFLIGHT_FEEDBACK_EMAIL` before
external Beta App Review submission. GitHub secret inspection after the change
showed this secret is not currently configured.

GitHub API inspection after commit `36e8f57` showed the repo is public and the
currently configured secret names are `ASC_ISSUER_ID`, `ASC_KEY_ID`,
`ASC_PRIVATE_KEY`, `MATCH_GIT_PRIVATE_KEY`, `MATCH_GIT_URL`,
`MATCH_KEYCHAIN_PASSWORD`, and `MATCH_PASSWORD`. The actionable long-lived
signing set remains six secrets; `MATCH_KEYCHAIN_PASSWORD` is an unused leftover
after the workflow simplification. `TESTFLIGHT_FEEDBACK_EMAIL` is still absent
and is not part of signing; it is only needed for automated external Beta App
Review submission when the feedback email is not filled manually in App Store
Connect. No GitHub Actions repo variables are configured yet, so
`AI_CADDIE_API_BASE_URL` is also absent remotely.

```bash
uv run python -m unittest tests.test_ci_workflow -v
uv run python -m unittest tests.test_mobile_contracts -v
uv run python -m py_compile tests/test_ci_workflow.py tests/test_mobile_contracts.py
git diff --check
```

Result: PASS. `tests.test_ci_workflow` ran 17 tests in 0.159s, and
`tests.test_mobile_contracts` ran 58 tests in 106.834s. These checks cover the
six-secret signing boundary, TestFlight feedback-email guard, build-time native
API URL wiring, iOS `Info.plist` key, XcodeGen build setting, and Swift fallback
behavior.

Follow-up export-compliance contract checks now parse the iOS and Watch
`Info.plist` files to verify `ITSAppUsesNonExemptEncryption=false`, and assert
that the TestFlight setup guide documents the App Store Connect encryption-form
selection for the current build.

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

```bash
AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests -v
```

Result: PASS under a 60 minute cap after isolating local/private Garmin and
prodgeometry tests behind explicit opt-in environment variables. The full
deterministic fixture discovery ran 662 tests in 1670.478s with 8 intentional
skips for local-only Garmin/prodgeometry checks.

```bash
cd web_v2 && npm exec --yes --package=node@24 -- npm test -- --run
cd web_v2 && npx -y -p node@24 node node_modules/eslint/bin/eslint.js .
cd web_v2 && npx -y -p node@24 node node_modules/typescript/bin/tsc -b
cd web_v2 && npx -y -p node@24 node node_modules/vite/bin/vite.js build
cd web_v2 && npx -y -p node@24 node node_modules/@playwright/test/cli.js test
```

Result: PASS. Vitest ran 24 files / 180 tests; ESLint, TypeScript, Vite build,
and two Playwright browser smokes all passed under temporary Node 24.

```bash
AI_CADDIE_ADMIN_TOKEN=local-smoke-token AI_CADDIE_PRIVATE_SMOKE_EVIDENCE=/tmp/ai-caddie-private-trial-smoke-2026-06-06.json ops/smoke_private_trial.sh http://127.0.0.1:9011
```

Result: PASS. Evidence schema `ai-caddie-private-trial-smoke-evidence-v1`,
`endpointCount=14`, `adminProtectedEndpointCount=11`, `mediaRoundTrip=true`,
`secretFree=true`, created at `2026-06-06T23:44:51Z`.

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
- A new TestFlight IPA was not uploaded after adding build-time native API URL
  wiring because no phone-reachable backend URL was available yet.
- Xcode simulator tests require macOS/Xcode and were not executable in this
  Linux workspace. The GitHub macOS TestFlight workflow did compile, archive,
  sign, export, and upload the release app.
- Installation from TestFlight on the user's iPhone/watch was not verified from
  this workspace. The latest TestFlight list shows internal state
  `IN_BETA_TESTING`, but no device-side install confirmation has been captured.
  External group `Private Trial` exists, but external distribution remains
  `READY_FOR_BETA_SUBMISSION` until `TESTFLIGHT_FEEDBACK_EMAIL` is configured
  and Beta App Review is submitted. External tester emails are still needed
  before populating that group.
