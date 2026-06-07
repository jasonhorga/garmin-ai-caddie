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

Phase 6 is locally hardened and partially externally complete. The
phone-reachable backend gate is now proven through the NAS VM and Cloudflare
Quick Tunnel, but that URL is temporary and should be replaced by a named
Cloudflare Tunnel or Tailscale Funnel before relying on a long-lived connected
TestFlight build. The remaining unchecked roadmap items are external-state
items:

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
  signing secrets are ready, native API base URL configuration is ready,
  `READY_FOR_BETA_SUBMISSION` is proven, `Private Trial` tester coverage is
  ready, and the NAS VM backend URL plus authenticated backend probe are ready.
  Beta App feedback email, external Beta App Review submission, and
  iPhone/watch install verification remain external.
- Latest GitHub evidence on commit `80a3d53`: CI run `27088735570` passed,
  `iOS TestFlight Testers` list run `27088735595` passed, and Phase 6
  Readiness run `27088735593` passed with `fail_when_incomplete=false`
  while reporting `state=incomplete`.

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
- Targeted workflow/readiness regression verification after the TestFlight
  evidence hardening passed:
  `uv run python -m unittest tests.test_ci_workflow tests.test_phase6_external_readiness tests.test_roadmap_completion_status tests.test_roadmap_completion_audit -v`
  reported 56 tests OK.
- The roadmap completion audit test now parses multiline checklist items, so
  open Phase 6 items are not truncated when proving what remains open.
- The Phase 6 preflight parser now ignores GitHub Actions script-source echo
  lines and only treats real `Beta App test info...` output as evidence that
  feedback email metadata is configured.
- The `iOS TestFlight Testers` list workflow now prints safe Beta App metadata
  booleans. Run `27088348501` proves the current ASC localization has
  `descriptionConfigured=true` and `feedbackEmailConfigured=false`.
- The `Phase 6 Readiness` workflow now passes safe secret-presence booleans for
  the required signing secrets and `TESTFLIGHT_FEEDBACK_EMAIL`, so a limited
  `github.token` no longer turns those checks into ambiguous `unknown` states.
- The `iOS TestFlight Testers` workflow now has `operation=submit_review`, a
  focused Beta Review path that selects the build, sets export compliance,
  ensures Beta App test info from the `TESTFLIGHT_FEEDBACK_EMAIL` secret, and
  submits Beta App Review without changing tester/group membership. Its success
  log line is parsed as `betaReviewSubmitted` evidence, while script-source echo
  is explicitly ignored.
- The manual `Backend Fly Deploy` GitHub workflow now covers the next backend
  release step once `FLY_API_TOKEN` and `AI_CADDIE_ADMIN_TOKEN` exist: create
  the Fly app/volume if needed, deploy the container, update
  `AI_CADDIE_API_BASE_URL`, run remote private-trial smoke, and upload Phase 6
  preflight artifacts.
- The manual `Phase 6 Readiness` workflow now reruns external preflight and
  roadmap completion evidence from GitHub after backend, review, or device
  install state changes.
- These local checks improve evidence quality and keep private-trial readiness
  current, but they do not replace the remaining external Phase 6 gates listed
  above.

## NAS VM Backend Evidence

The 2026-06-07 VM continuation moved the backend gate from missing to ready:

- Connected to the isolated NAS VM through a temporary `tmate` session as the
  restricted `codex` user, not through the NAS host SSH service.
- Installed Docker and Compose v2 in the VM. The Ubuntu source uses
  `docker-compose-v2`, so `ops/bootstrap_nas_vm_api.sh` was updated to fall
  back from `docker-compose-plugin` to `docker-compose-v2`.
- Bootstrapped the API from `integration/v2` in
  `/home/codex/garmin-ai-caddie`.
- Verified the container is healthy and bound only to `127.0.0.1:9000`.
- Ran the local private-trial smoke from the VM container:
  `private trial smoke ok: http://127.0.0.1:9000`.
- Started a Cloudflare Quick Tunnel and verified public health from outside the
  VM at `https://track-commercial-add-phd.trycloudflare.com/api/v2/health`.
- Set GitHub repo variable `AI_CADDIE_API_BASE_URL` to that HTTPS origin and
  updated `AI_CADDIE_ADMIN_TOKEN` to match the VM `.env` token without printing
  the token in repo artifacts.
- GitHub CI run `27087967058` on commit `598d8c4` completed successfully.
- GitHub Phase 6 Readiness run `27088479370` completed successfully and its
  artifact reports:
  `native_api_base_url_configuration=ready`,
  `phone_reachable_backend_url=ready`, `backend_probe=ready`, and
  `external_testers=ready`.

The Quick Tunnel URL is evidence that the backend gate is technically reachable
from the phone/GitHub side, not a durable production endpoint. A named
Cloudflare Tunnel or Tailscale Funnel remains the correct next operational step
before a stable connected TestFlight build.

## No-Quota External Audit

Read-only GitHub API and existing Actions-log checks on 2026-06-07 confirm:

- Repository visibility is public and the default branch is `integration/v2`.
- The six long-lived signing secrets are present:
  `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_PRIVATE_KEY`, `MATCH_GIT_URL`,
  `MATCH_GIT_PRIVATE_KEY`, and `MATCH_PASSWORD`.
- `MATCH_KEYCHAIN_PASSWORD` is still configured remotely but is legacy unused
  by the current workflows.
- GitHub Actions variable `AI_CADDIE_API_BASE_URL` is configured to the current
  Cloudflare Quick Tunnel origin. This satisfies the Phase 6 backend probe but
  should be replaced with a stable named tunnel origin before long-lived
  connected native distribution.
- `TESTFLIGHT_FEEDBACK_EMAIL` is now proven not configured in GitHub Actions by
  the safe secret-presence boolean in Phase 6 Readiness run `27088479370`.
  App Store Connect is also missing the Beta App feedback email:
  `iOS TestFlight Testers` run `27088348501` reports
  `descriptionConfigured=true` and `feedbackEmailConfigured=false`.
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
  Beta App feedback email was not configured.

## Completion Decision

The active goal is not complete yet. Current evidence proves the roadmap is
implemented and tested through the phone-reachable backend gate, but it does not
prove that Beta App feedback email metadata is configured; in fact, the latest
GitHub and ASC evidence proves it is missing. It also does not prove that
external Beta Review has been submitted, or that iPhone/watch installation works
from TestFlight. The temporary Quick Tunnel should also be replaced with a
stable named tunnel before relying on a long-lived connected TestFlight backend.
