# Phase 6 Deployment Native Trial Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the private single-user product deployable, operable, secret-safe, and ready for native release evidence without spending routine CI/native minutes.

**Architecture:** Use existing Render/Fly/container manifests and operations scripts. Readiness consumes secret-free evidence from backup, smoke, snapshot acceptance, and native build records; external cloud/TestFlight steps are gated by credentials and explicit user instruction.

**Tech Stack:** Python 3.12, FastAPI, unittest, uv, Docker/Render/Fly/Vercel manifests, shell ops scripts, GitHub Actions contracts, Swift/Xcode source contracts.

---

## Current Baseline

- Existing spec: `docs/superpowers/specs/2026-06-06-phase-6-deployment-native-trial-hardening-design.md`.
- Existing manifests and scripts:
  - `render.yaml`
  - `fly.toml`
  - `Dockerfile`
  - `docker-compose.yml`
  - `web_v2/vercel.json`
  - `ops/smoke_private_trial.sh`
  - `ops/backup_data.sh`
  - `ops/export_snapshot.py`
  - `ops/import_snapshot.py`
  - `ops/write_native_build_evidence.py`
- Existing verification tests:
  - `tests/test_deployment_manifests.py`
  - `tests/test_snapshot_import_export.py`
  - `tests/test_server_v2_readiness.py`
  - `tests/test_ci_workflow.py`
  - `tests/test_native_build_evidence.py`
- Known external constraints:
  - Cloud deploy requires provider credentials or an already configured CLI/session.
  - TestFlight signing/distribution must not run unless explicitly requested.
  - Linux cannot run Xcode simulator tests; native simulator evidence must come from macOS or native workflow evidence.

## File Structure

- Modify `docs/deployment/private-trial.md`
  - Document exact local, Render/Fly, Vercel, backup, import/export, and smoke steps.
- Modify `server_v2/readiness.py`
  - Ensure readiness reports backup, smoke, snapshot acceptance, native build evidence, and secret-safe degraded reasons.
- Modify `tests/test_server_v2_readiness.py`
  - Add regression coverage for stale/missing/current evidence.
- Modify `ops/smoke_private_trial.sh`
  - Ensure smoke records secret-free evidence and exercises protected routes with admin token.
- Modify `ops/backup_data.sh`
  - Ensure latest manifest points at a portable snapshot and includes hash/size timestamps.
- Modify `ops/export_snapshot.py` and `ops/import_snapshot.py`
  - Keep only portable private data, reject unsafe paths, exclude credentials.
- Modify `.github/workflows/ci.yml` and `.github/workflows/native-mobile.yml` only if tests reveal path-filter or minute-control drift.
- Create `docs/superpowers/reviews/2026-06-06-phase-6-deployment-native-trial-hardening.md`
  - Record verification and any external deployment/native constraints not runnable from Linux.
- Modify `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`
  - Mark Phase 6 complete only after verification and evidence are current.

### Task 1: Deployment Manifest And Documentation Gate

**Files:**
- Modify: `docs/deployment/private-trial.md`
- Modify if needed: `render.yaml`, `fly.toml`, `Dockerfile`, `docker-compose.yml`, `web_v2/vercel.json`
- Modify: `tests/test_deployment_manifests.py`

- [ ] **Step 1: Write failing docs/manifest contract test**

Add to `tests/test_deployment_manifests.py`:

```python
def test_private_trial_docs_include_local_and_cloud_smoke_commands(self) -> None:
    text = Path("docs/deployment/private-trial.md").read_text(encoding="utf-8")

    for required in [
        "uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9000",
        "ops/smoke_private_trial.sh http://127.0.0.1:9000",
        "ops/backup_data.sh",
        "ops/export_snapshot.py",
        "ops/import_snapshot.py",
        "Render API URL",
        "Fly API URL",
        "Vercel Web URL",
        "AI_CADDIE_ADMIN_TOKEN",
        "AI_CADDIE_PRIVATE_ROOT",
    ]:
        self.assertIn(required, text)
    self.assertNotIn("JWT_WEB", text)
    self.assertNotIn("connect-csrf-token", text)
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
uv run python -m unittest tests.test_deployment_manifests.DeploymentManifestTests.test_private_trial_docs_include_local_and_cloud_smoke_commands -v
```

Expected: FAIL if the docs omit any command or secret-safety statement.

- [ ] **Step 3: Update docs/manifests**

In `docs/deployment/private-trial.md`, include these command blocks:

```bash
AI_CADDIE_SECURITY_PROFILE=private \
AI_CADDIE_ADMIN_TOKEN=replace-with-random-admin-token \
AI_CADDIE_DATA_MODE=local_or_fixture \
AI_CADDIE_PRIVATE_ROOT=/var/lib/ai-caddie \
uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9000
```

```bash
AI_CADDIE_ADMIN_TOKEN=replace-with-random-admin-token \
ops/smoke_private_trial.sh http://127.0.0.1:9000
```

```bash
ops/backup_data.sh
uv run python ops/export_snapshot.py --source-root . --output data/backups/private-snapshot.tar.gz
uv run python ops/import_snapshot.py data/backups/private-snapshot.tar.gz --target-root /tmp/ai-caddie-restore-check
```

Document that Render/Fly/Vercel CLI deployment is allowed only when provider credentials are already configured in the environment, and TestFlight is excluded from routine Phase 6 unless explicitly requested.

- [ ] **Step 4: Run manifest suite**

Run:

```bash
uv run python -m unittest tests.test_deployment_manifests -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/deployment/private-trial.md render.yaml fly.toml Dockerfile docker-compose.yml web_v2/vercel.json tests/test_deployment_manifests.py
git commit -m "docs: harden private trial deployment runbook"
```

### Task 2: Backup, Export, Import, And Snapshot Acceptance Evidence

**Files:**
- Modify: `ops/backup_data.sh`
- Modify if needed: `ops/export_snapshot.py`, `ops/import_snapshot.py`, `ops/accept_private_snapshot.py`
- Modify: `tests/test_snapshot_import_export.py`
- Modify: `tests/test_server_v2_readiness.py`

- [ ] **Step 1: Write failing evidence tests**

Add to `tests/test_snapshot_import_export.py`:

```python
def test_export_snapshot_records_portable_manifest_without_private_paths(self) -> None:
    with TemporaryDirectory() as tmp:
        source = Path(tmp) / "source"
        source.mkdir()
        (source / "data" / "scorecards").mkdir(parents=True)
        (source / "data" / "scorecards" / "1.json").write_text("{}", encoding="utf-8")
        tarball = Path(tmp) / "snapshot.tar.gz"

        manifest = export_snapshot(source_root=source, output_path=tarball)

    self.assertEqual(manifest["schema"], "ai-caddie-export-snapshot-v1")
    self.assertGreater(manifest["sizeBytes"], 0)
    self.assertNotIn("/home/", json.dumps(manifest).lower())
    self.assertNotIn(".garmin_tokens", json.dumps(manifest).lower())
```

Add to `tests/test_server_v2_readiness.py` a readiness assertion for accepted private snapshot state:

```python
def test_readiness_reports_private_snapshot_acceptance_state(self) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir = root / "data" / "snapshots"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "accepted_private_snapshot.json").write_text(
            json.dumps({
                "schema": "ai-caddie-private-snapshot-acceptance-v1",
                "acceptedAt": "2026-06-06T00:00:00Z",
                "snapshotPath": "data/backups/private-snapshot.tar.gz",
                "secretFree": True,
            }),
            encoding="utf-8",
        )

        with patch("server_v2.readiness.RUNTIME_ROOT", root):
            payload = build_readiness_response()

    checks = {row["label"]: row for row in payload["checks"]}
    self.assertEqual(checks["private_snapshot_acceptance"]["state"], "ready")
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run python -m unittest tests.test_snapshot_import_export tests.test_server_v2_readiness -v
```

Expected: FAIL if manifest return/evidence fields are missing.

- [ ] **Step 3: Implement evidence shape**

In `ops/export_snapshot.py`, have `export_snapshot()` return:

```python
{
    "schema": "ai-caddie-export-snapshot-v1",
    "createdAt": created_at,
    "snapshotPath": _display_path(output_path),
    "sizeBytes": output_path.stat().st_size,
    "fileCount": len(names),
    "includedRoots": sorted(included_roots),
    "secretFree": True,
}
```

In `ops/backup_data.sh`, write `latest.json` with:

```json
{
  "schema": "ai-caddie-backup-manifest-v1",
  "createdAt": "...",
  "snapshotPath": "...",
  "sizeBytes": 123,
  "secretFree": true
}
```

In `server_v2/readiness.py`, ensure the private snapshot check reads `data/snapshots/accepted_private_snapshot.json`, redacts paths, and degrades when missing or stale.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
uv run python -m unittest tests.test_snapshot_import_export tests.test_server_v2_readiness -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ops/backup_data.sh ops/export_snapshot.py ops/import_snapshot.py ops/accept_private_snapshot.py server_v2/readiness.py tests/test_snapshot_import_export.py tests/test_server_v2_readiness.py
git commit -m "feat: record portable private snapshot readiness"
```

### Task 3: Private Trial Smoke Evidence

**Files:**
- Modify: `ops/smoke_private_trial.sh`
- Modify: `server_v2/readiness.py`
- Modify: `tests/test_ci_workflow.py`
- Modify: `tests/test_server_v2_readiness.py`

- [ ] **Step 1: Write failing smoke evidence tests**

Add to `tests/test_ci_workflow.py`:

```python
def test_private_trial_smoke_writes_secret_free_evidence_file(self) -> None:
    text = Path("ops/smoke_private_trial.sh").read_text(encoding="utf-8")

    self.assertIn("AI_CADDIE_PRIVATE_SMOKE_EVIDENCE", text)
    self.assertIn("ai-caddie-private-trial-smoke-evidence-v1", text)
    self.assertIn("secretFree", text)
    self.assertIn("endpointCount", text)
    self.assertIn("adminProtectedEndpointCount", text)
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
uv run python -m unittest tests.test_ci_workflow.CIWorkflowTests.test_private_trial_smoke_writes_secret_free_evidence_file -v
```

Expected: FAIL if smoke evidence output is not documented/implemented.

- [ ] **Step 3: Implement smoke evidence**

In `ops/smoke_private_trial.sh`, after all endpoint probes pass, write JSON to `${AI_CADDIE_PRIVATE_SMOKE_EVIDENCE:-data/smoke/private-trial-smoke.json}`:

```json
{
  "schema": "ai-caddie-private-trial-smoke-evidence-v1",
  "createdAt": "...",
  "baseUrl": "http://127.0.0.1:9000",
  "endpointCount": 12,
  "adminProtectedEndpointCount": 3,
  "mediaRoundTrip": true,
  "secretFree": true
}
```

Keep response scanning for forbidden markers:

```text
password=
secret=
/home/
/users/
.garmin_tokens
cookie
csrf
```

Update readiness to consume this evidence and degrade when stale/missing.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
uv run python -m unittest tests.test_ci_workflow tests.test_server_v2_readiness -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ops/smoke_private_trial.sh server_v2/readiness.py tests/test_ci_workflow.py tests/test_server_v2_readiness.py
git commit -m "feat: record private trial smoke evidence"
```

### Task 4: Native Release Gate And Evidence

**Files:**
- Modify if needed: `.github/workflows/native-mobile.yml`, `.github/workflows/ios-signing-bootstrap.yml`, `.github/workflows/ios-testflight.yml`
- Modify: `ops/write_native_build_evidence.py`
- Modify: `tests/test_ci_workflow.py`
- Modify: `tests/test_native_build_evidence.py`
- Modify: `mobile/ios/README.md`

- [ ] **Step 1: Write failing native gate tests**

Add to `tests/test_ci_workflow.py`:

```python
def test_testflight_workflows_are_manual_only_and_secret_driven(self) -> None:
    for name in ["ios-signing-bootstrap.yml", "ios-testflight.yml"]:
        workflow = yaml.safe_load((Path(".github/workflows") / name).read_text(encoding="utf-8"))
        triggers = workflow[True]
        self.assertIn("workflow_dispatch", triggers)
        self.assertNotIn("push", triggers)
        text = (Path(".github/workflows") / name).read_text(encoding="utf-8")
        self.assertIn("secrets.", text)
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN=", text)
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run python -m unittest tests.test_ci_workflow.CIWorkflowTests.test_testflight_workflows_are_manual_only_and_secret_driven tests.test_native_build_evidence -v
```

Expected: FAIL if workflows are not manual/secret-driven.

- [ ] **Step 3: Harden workflows/evidence**

Ensure:

- `.github/workflows/native-mobile.yml` runs only on `workflow_dispatch` and native path PRs.
- `.github/workflows/ios-signing-bootstrap.yml` is `workflow_dispatch` only.
- `.github/workflows/ios-testflight.yml` is `workflow_dispatch` only.
- `ops/write_native_build_evidence.py` rejects private paths, token markers, and non-sanitized destinations.
- `mobile/ios/README.md` documents local macOS verification:

```bash
xcodegen generate --spec mobile/ios/project.yml --project-root .
xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddie -destination "platform=iOS Simulator,name=iPhone 16,OS=latest"
xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddieWatch -destination "platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest"
python3 ops/write_native_build_evidence.py
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
uv run python -m unittest tests.test_ci_workflow tests.test_native_build_evidence -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/native-mobile.yml .github/workflows/ios-signing-bootstrap.yml .github/workflows/ios-testflight.yml ops/write_native_build_evidence.py tests/test_ci_workflow.py tests/test_native_build_evidence.py mobile/ios/README.md
git commit -m "test: harden native release gates"
```

### Task 5: Local Private Trial Smoke

**Files:**
- Create: `docs/superpowers/reviews/2026-06-06-phase-6-deployment-native-trial-hardening.md`
- Modify: `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`

- [ ] **Step 1: Start local private API**

Run in a background shell:

```bash
AI_CADDIE_SECURITY_PROFILE=private \
AI_CADDIE_ADMIN_TOKEN=ci-admin-token \
AI_CADDIE_DATA_MODE=fixture \
uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9000
```

Expected: server listens on `http://127.0.0.1:9000`.

- [ ] **Step 2: Run private trial smoke**

Run:

```bash
AI_CADDIE_ADMIN_TOKEN=ci-admin-token \
AI_CADDIE_PRIVATE_SMOKE_EVIDENCE=/tmp/ai-caddie-private-trial-smoke.json \
ops/smoke_private_trial.sh http://127.0.0.1:9000
```

Expected: PASS and evidence file exists.

- [ ] **Step 3: Run backup/export/import verification**

Run:

```bash
uv run python ops/export_snapshot.py --source-root . --output /tmp/ai-caddie-private-snapshot.tar.gz
uv run python ops/import_snapshot.py /tmp/ai-caddie-private-snapshot.tar.gz --target-root /tmp/ai-caddie-restore-check
```

Expected: PASS; no credentials, `.garmin_tokens`, local private paths, or `clubs.json` unless explicitly included.

- [ ] **Step 4: Run Phase 6 target tests**

Run:

```bash
uv run python -m unittest tests.test_deployment_manifests tests.test_snapshot_import_export tests.test_server_v2_readiness tests.test_ci_workflow tests.test_native_build_evidence -v
git diff --check
```

Expected: PASS.

- [ ] **Step 5: Record evidence**

Create `docs/superpowers/reviews/2026-06-06-phase-6-deployment-native-trial-hardening.md`:

```markdown
# Phase 6 Deployment Native Trial Hardening Evidence

- Date: 2026-06-06
- Branch: `integration/v2`

## Scope

Implemented Phase 6 from `docs/superpowers/specs/2026-06-06-phase-6-deployment-native-trial-hardening-design.md`.

## Evidence

- Deployment manifests define private runtime roots, health checks, admin-token placeholders, and no Garmin credentials.
- Backup/export/import exclude secrets and reject unsafe paths.
- Private trial smoke writes secret-free evidence.
- Native workflows remain manual or native-path gated; TestFlight is manual only.
- Readiness reports backup, smoke, snapshot acceptance, native evidence, and degraded reasons.

## Verification

```bash
uv run python -m unittest tests.test_deployment_manifests tests.test_snapshot_import_export tests.test_server_v2_readiness tests.test_ci_workflow tests.test_native_build_evidence -v
```

Result: PASS.

```bash
AI_CADDIE_ADMIN_TOKEN=ci-admin-token AI_CADDIE_PRIVATE_SMOKE_EVIDENCE=/tmp/ai-caddie-private-trial-smoke.json ops/smoke_private_trial.sh http://127.0.0.1:9000
```

Result: PASS.

## Not Run On Linux

- Xcode simulator tests require macOS.
- TestFlight signing/distribution requires explicit user instruction and Apple credentials.
- Cloud deploy requires provider credentials or an already configured CLI session.
```

- [ ] **Step 6: Mark roadmap Phase 6 complete**

In `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`, mark Phase 6 checkboxes complete only after local smoke and target tests pass. If cloud deployment or TestFlight cannot run because credentials are absent, record the exact skipped item in the evidence and leave only that item unchecked.

- [ ] **Step 7: Commit evidence**

```bash
git add docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md docs/superpowers/reviews/2026-06-06-phase-6-deployment-native-trial-hardening.md
git commit -m "docs: record phase 6 trial hardening evidence"
```

## Final Verification

Run:

```bash
uv run python -m unittest tests.test_deployment_manifests tests.test_snapshot_import_export tests.test_server_v2_readiness tests.test_ci_workflow tests.test_native_build_evidence -v
git diff --check
```

Expected: all commands exit 0.

External deployment/TestFlight completion requires credentials and explicit release instruction; do not fabricate those results.
