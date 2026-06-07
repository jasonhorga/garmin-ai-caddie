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
TestFlight build. External Beta App Review has now been submitted, so the
`Submit external Beta App Review.` roadmap item is closed. The remaining
unchecked roadmap item is external-state device verification:

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
  Beta App feedback email is configured and external Beta App Review submission
  is now proven. `iOS TestFlight Testers` run `27091302402` logged
  `Beta App Review submission requested`, and Phase 6 Readiness run
  `27091323640` reports `external_beta_review_submission=ready`. The remaining
  external blocker is iPhone/watch install verification.
- Recent GitHub evidence on commit `71c58b1`: `iOS TestFlight Testers` run
  `27091501698` completed successfully, Phase 6 Readiness run `27091642937`
  completed successfully with `fail_when_incomplete=false` while reporting only
  `device_install=manual_required`, and CI run `27091661099` completed
  successfully.

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
  reported 57 tests OK.
- The roadmap completion audit test now parses multiline checklist items, so
  open Phase 6 items are not truncated when proving what remains open.
- The Phase 6 preflight parser now ignores GitHub Actions script-source echo
  lines and only treats real `Beta App test info...` output as evidence that
  feedback email metadata is configured.
- The `iOS TestFlight Testers` list workflow now prints safe Beta App metadata
  booleans. Run `27088348501` proves the current ASC localization has
  `descriptionConfigured=true` and `feedbackEmailConfigured=false`.
- After `TESTFLIGHT_FEEDBACK_EMAIL` was configured, run `27090974230` proved the
  localization now has `descriptionConfigured=true` and
  `feedbackEmailConfigured=true`.
- The TestFlight tester workflow now also prints safe Beta App Review Detail
  booleans and has `operation=configure_review` for filling review metadata
  without submitting a build. Run `27091094309` shows
  `contactFirstNameConfigured=false`, `contactLastNameConfigured=false`,
  `contactEmailConfigured=false`, `contactPhoneConfigured=false`,
  `demoAccountRequired=nil`, and `notesConfigured=false`.
- After the review contact secrets were configured, `iOS TestFlight Testers` run
  `27091281932` updated the Beta App Review Detail fields and confirmed
  `contactFirstNameConfigured=true`, `contactLastNameConfigured=true`,
  `contactEmailConfigured=true`, `contactPhoneConfigured=true`,
  `demoAccountRequired=false`, and `notesConfigured=true`.
- `iOS TestFlight Testers` run `27091302402` selected build `0.1.0 (3)`,
  confirmed export compliance and review details, and logged
  `Beta App Review submission requested`.
- `iOS TestFlight Testers` list run `27091440783` shows the submitted build is
  now `externalState=WAITING_FOR_BETA_REVIEW`, which means Apple has the build
  in the Beta Review queue.
- `iOS TestFlight Testers` distribute run `27091501698` set external tester
  auto-notify to false and logged
  `Assigned build 0.1.0 (3) to group(s): Private Trial`; it skipped
  resubmission because `ready_for_beta_submission=false` after the first
  submission.
- Phase 6 Readiness run `27091323640` now reports
  `external_beta_review_feedback=ready`,
  `external_beta_review_submission_ready=ready`, and
  `external_beta_review_submission=ready`; its only missing external action is
  iPhone/watch install verification.
- The `Phase 6 Readiness` workflow now passes safe secret-presence booleans for
  the required signing secrets and `TESTFLIGHT_FEEDBACK_EMAIL`, so a limited
  `github.token` no longer turns those checks into ambiguous `unknown` states.
- The `iOS TestFlight Testers` workflow now has `operation=submit_review`, a
  focused Beta Review path that selects the build, sets export compliance,
  ensures Beta App test info and Beta App Review Detail metadata from configured
  secrets, and submits Beta App Review without changing tester/group membership.
  Its success log line is parsed as `betaReviewSubmitted` evidence, while
  script-source echo is explicitly ignored.
- The TestFlight Actions log scan now reads up to 100 recent workflow runs and
  scans the first 50 successful tester workflow logs, preserving older
  `Private Trial` assignment evidence after repeated review/list/distribute
  dispatches. Phase 6 Readiness run `27091642937` confirms
  `external_testers=ready` again.
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
- `TESTFLIGHT_FEEDBACK_EMAIL` has since been configured in GitHub Actions, and
  App Store Connect now has Beta App localization feedback metadata:
  `iOS TestFlight Testers` run `27090974230` reports
  `descriptionConfigured=true` and `feedbackEmailConfigured=true`.
- App Store Connect previously had empty Beta App Review Detail contact
  metadata: `iOS TestFlight Testers` run `27091094309` reports
  `contactFirstNameConfigured=false`, `contactLastNameConfigured=false`,
  `contactEmailConfigured=false`, `contactPhoneConfigured=false`,
  `demoAccountRequired=nil`, and `notesConfigured=false`.
- That metadata was then filled by `iOS TestFlight Testers` run `27091281932`,
  which reports all four contact fields configured, `demoAccountRequired=false`,
  and `notesConfigured=true`.
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
- A `submit_review` attempt, run `27090920249`, selected build `0.1.0 (3)`,
  confirmed export compliance, updated Beta App test info, and then failed with
  Apple's `Missing required information to submit for external testing` response.
  The follow-up list run above identified the then-empty Beta App Review Detail
  contact fields as the next data to provide.
- After those fields were configured, `iOS TestFlight Testers` run `27091302402`
  successfully submitted external Beta App Review for build `0.1.0 (3)`.
- Follow-up `iOS TestFlight Testers` run `27091440783` reports
  `externalState=WAITING_FOR_BETA_REVIEW`.
- `iOS TestFlight Testers` run `27091501698` assigned build `0.1.0 (3)` to
  external group `Private Trial` with tester notifications disabled.
- Phase 6 Readiness run `27091642937` proves the current external gate state:
  `external_beta_review_feedback=ready`,
  `external_beta_review_submission_ready=ready`,
  `external_beta_review_submission=ready`, `external_testers=ready`, and
  `device_install=manual_required`.

## Completion Decision

The active goal is not complete yet. Current evidence proves the roadmap is
implemented and tested through the phone-reachable backend gate, and it now
proves that Beta App localization feedback metadata is configured, Beta App
Review Detail contact fields are configured, and external Beta Review has been
submitted. It does not yet prove that iPhone/watch installation works from
TestFlight. The temporary Quick Tunnel should also be replaced with a stable
named tunnel before relying on a long-lived connected TestFlight backend.
