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
- Backup/export/import exclude secrets, reject unsafe paths, return portable
  manifest metadata, and expose snapshot acceptance evidence in readiness.
- Private trial smoke writes secret-free evidence with endpoint counts,
  admin-protected endpoint counts, media round-trip status, and redaction checks.
- Native workflows remain manual or native-path gated; TestFlight and signing
  bootstrap are manual only.
- Native build evidence writer rejects private paths and secret-looking markers.
- Readiness reports backup, smoke, snapshot acceptance, native evidence, and
  degraded reasons without private paths or credential material.

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

No GitHub cache or artifact deletion was performed.

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
  Linux workspace.
- TestFlight signing/distribution was not run because it requires explicit
  release instruction and Apple credentials.
