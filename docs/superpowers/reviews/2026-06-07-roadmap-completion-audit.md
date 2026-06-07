# Roadmap Completion Audit

- Date: 2026-06-07
- Branch: `integration/v2`
- Authoritative roadmap:
  `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`

## Scope

This audit maps the active goal, "complete the roadmap, make a full test plan,
and execute tests", to the current repo state. Older detailed implementation plans
under `docs/superpowers/plans/` still contain unchecked step templates from
their original task-by-task instructions. They are historical planning artifacts;
the authoritative current completion state is the consolidated roadmap and the
review evidence listed below.

## Current Roadmap State

Phases 1-5 are complete in the authoritative roadmap:

- Phase 1 real-data spine and geometry coverage.
- Phase 2 auth refresh and fetch automation.
- Phase 3 course reference and par/yardage store.
- Phase 4 end-to-end private pipeline.
- Phase 5 course prep productization.

Phase 6 is locally hardened and partially externally complete. The remaining
unchecked roadmap items are all external-state items:

- Deploy a phone-reachable backend host and point the native app at it.
- Submit external Beta App Review.
- Verify installation from TestFlight on iPhone/watch.

Target tester coverage is now closed in the authoritative roadmap: GitHub
Actions run `27082080178` assigned 2 external testers to the `Private Trial`
group.

## Evidence Map

- Full test strategy and execution record:
  `docs/superpowers/reviews/2026-06-05-test-execution.md`
- Phase 2 auth/fetch evidence:
  `docs/superpowers/reviews/2026-06-06-phase-2-auth-refresh-fetch-automation.md`
- Phase 3 course-reference evidence:
  `docs/superpowers/reviews/2026-06-06-phase-3-course-reference-store.md`
- Phase 4 private pipeline evidence:
  `docs/superpowers/reviews/2026-06-06-phase-4-private-pipeline.md`
- Phase 5 course-prep evidence:
  `docs/superpowers/reviews/2026-06-06-phase-5-course-prep-productization.md`
- Phase 6 deployment/native trial evidence:
  `docs/superpowers/reviews/2026-06-06-phase-6-deployment-native-trial-hardening.md`
- Latest external release readiness evidence:
  `logs/phase6_external_readiness_latest.json`, surfaced through
  `/api/v2/readiness` as the `external_release` check.
- Machine-readable completion summary:
  `uv run python ops/roadmap_completion_status.py --no-fail`, which reads the
  authoritative roadmap and latest Phase 6 evidence without network access and
  emits grouped `phase6Gates` for backend reachability, Beta Review submission,
  target tester coverage, and device install, plus `roadmapGateAlignment` to
  catch roadmap/evidence drift.

## Latest Verification Summary

- Backend deterministic fixture discovery passed: 662 tests, 8 intentional
  local-only skips.
- Web verification passed under Node 24: Vitest 24 files / 180 tests, ESLint,
  TypeScript, Vite build, and two Playwright browser smokes.
- Private trial smoke passed against a local fixture/private API with
  `endpointCount=14`, `adminProtectedEndpointCount=11`,
  `mediaRoundTrip=true`, and `secretFree=true`.
- Phase 6 external readiness preflight currently reports `incomplete` in
  `logs/phase6_external_readiness_latest.json`: public repo and six required
  signing secrets are ready, `READY_FOR_BETA_SUBMISSION` is proven, and
  `Private Trial` tester coverage is ready; backend URL, native API URL
  configuration, Beta App feedback email, external Beta App Review submission,
  and iPhone/watch install verification remain external.

## Latest Local Continuation Evidence

The 2026-06-07 continuation work keeps heavyweight validation on manual GitHub
Actions dispatch while using targeted local checks for quick code-review
sanity:

- The private-trial smoke was hardened for cold `/api/v2/readiness` startup by
  giving only that endpoint a longer configurable timeout. A fresh local fixture
  smoke then passed with `endpointCount=14`,
  `adminProtectedEndpointCount=11`, `mediaRoundTrip=true`, and
  `secretFree=true`.
- Targeted local verification passed:
  `uv run python -m unittest tests.test_phase6_external_readiness tests.test_server_v2_readiness tests.test_deployment_manifests tests.test_roadmap_completion_status -v`
  reported 49 tests OK.
- The roadmap completion audit test now parses multiline checklist items, so
  open Phase 6 items are not truncated when proving what remains open.
- The Phase 6 preflight parser now ignores GitHub Actions script-source echo
  lines and only treats real `Beta App test info...` output as evidence that
  feedback email metadata is configured.
- These local checks improve evidence quality and keep private-trial readiness
  current, but they do not replace the three remaining external Phase 6 gates
  listed above.

## No-Quota External Audit

Read-only GitHub API and existing Actions-log checks on 2026-06-07 confirm:

- Repository visibility is public and the default branch is `integration/v2`.
- The six long-lived signing secrets are present:
  `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_PRIVATE_KEY`, `MATCH_GIT_URL`,
  `MATCH_GIT_PRIVATE_KEY`, and `MATCH_PASSWORD`.
- `MATCH_KEYCHAIN_PASSWORD` is still configured remotely but is legacy unused
  by the current workflows.
- GitHub Actions variables are empty, so `AI_CADDIE_API_BASE_URL` is not yet
  configured for connected native builds.
- `TESTFLIGHT_FEEDBACK_EMAIL` is not configured as a repo secret, and current
  successful Actions logs do not prove the Beta App feedback email is filled.
- The latest successful `iOS TestFlight (CD)` run uploaded and processed build
  `0.1.0 (3)`.
- The latest successful `iOS TestFlight Testers` list run shows build
  `0.1.0 (3)` as `VALID`, `usesNonExemptEncryption=false`,
  `internalState=IN_BETA_TESTING`, and
  `externalState=READY_FOR_BETA_SUBMISSION`.
- `READY_FOR_BETA_SUBMISSION` proves App Store Connect considers the build ready
  to submit for external Beta Review; it does not prove the review submission
  has happened.
- External group `Private Trial` exists, and run `27082080178` assigned 2
  external testers to that group. That is strong enough to prove target tester
  coverage, but it does not prove iPhone/watch installation.
- A later distribute attempt failed before external distribution because the
  Beta App feedback email was not proven configured.

## Completion Decision

The active goal is not complete yet. Current evidence proves the roadmap is
implemented and tested up to the external release boundary, but it does not
prove that a phone-reachable backend is deployed, that external Beta Review has
been submitted, that Beta App feedback email metadata is configured, or that
iPhone/watch installation works from TestFlight.
