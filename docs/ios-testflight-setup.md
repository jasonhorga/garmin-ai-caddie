# iOS + Watch → TestFlight (no Mac needed)

This uses GitHub `macos-15` runners + fastlane `match` (certs/profiles in a private git
repo) + an App Store Connect API key. No local Mac and no interactive Apple login are
needed. Signing is isolated from other apps in `jasonhorga/garmin-ai-caddie-signing`.

## One-time turn-on (≈5 min)

1. **Add the signing secrets to this repo** (Settings → Secrets and variables → Actions):
   - `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_PRIVATE_KEY`  (App Store Connect API key, `.p8` content)
   - `MATCH_GIT_URL`, `MATCH_GIT_PRIVATE_KEY`, `MATCH_PASSWORD`  (fastlane match)
   The match repo is private and project-specific:
   `git@github.com:jasonhorga/garmin-ai-caddie-signing.git`.
   The CI keychain password is generated per run and is not a GitHub secret.
2. **Create the App Store Connect app record once** at
   `https://appstoreconnect.apple.com/apps`:
   - Platform: `iOS`
   - Name: `AI Caddie` (or another available display name)
   - Bundle ID: `com.ai-caddie.mobile`
   - SKU: `com.ai-caddie.mobile`
   Do not create a separate watch app record.
3. **Run the `iOS Signing Bootstrap` workflow** once (Actions → iOS Signing Bootstrap → Run
   workflow). It registers the app + watch Apple Developer Bundle IDs and writes the
   certs/profiles into the match repo. (Idempotent — safe if the app IDs already exist.)

After step 3, signing is ready. The App Store Connect app record must exist before
`upload_to_testflight` can upload the IPA; Apple's API key can manage existing app records
but does not create a new app record for this account.

## Shipping a build

Candidate and production are separate gates. Every IPA is accompanied by
`release-provenance.json` containing the 40-character commit, workflow run,
marketing/build numbers, API origin host, backend revision, IPA SHA-256, and
upload flag. Tester/install assertions must name the build number and remain
manual evidence. An `upload=false` manifest is allowed for artifact-only
builds, but it never satisfies the release gate.

Current branch: `codex/release-hardening-20260827`.

- Before uploading a connected build, run the external release preflight from
  `docs/deployment/private-trial.md` and keep the generated evidence file:
  ```bash
  uv run python ops/phase6_external_readiness.py \
    --api-base-url https://<api-host> \
    --probe-backend \
    --output logs/phase6_external_readiness_latest.json
  ```
  A fully connected external trial should not be considered ready until this
  reports `state=ready`.
- Run the `iOS TestFlight (CD)` workflow manually from the intended release branch with
  optional release notes and optional origin-only `api_base_url`. It runs
  `xcodegen generate` → `fastlane ios beta` → archives the app (with embedded
  watch app) → uploads to TestFlight.
  If `api_base_url` is blank, the workflow falls back to repo variable
  `AI_CADDIE_API_BASE_URL`; if both are blank, the app keeps the offline/fixture fallback.
  Upload mode requires the six signing secrets, an origin-only public HTTPS API
  URL, an admin token for authenticated `/api/v2/health` + `/api/v2/readiness`
  preflight, and a backend revision that matches the deployed host.
  The iPhone app also has a runtime Backend screen for an origin-only `https://`
  API URL and private admin token, so a tester can point an already uploaded
  TestFlight build at a deployed backend without another upload.
- Run the `iOS TestFlight Testers` workflow manually:
  - `operation=list` shows uploaded builds, TestFlight groups, and currently visible testers.
  - `operation=add` adds comma-separated external tester emails to the configured group
    (default `Private Trial`).
  - `operation=assign_existing` assigns currently visible app-level TestFlight testers
    to the configured group without printing raw email addresses. Use this when the
    testers already exist in App Store Connect and only group membership is missing.
  - For automated external Beta App Review submission, set the
    `TESTFLIGHT_FEEDBACK_EMAIL` repo secret. It is intentionally secret-only
    because this repo is public. If you fill the Beta App feedback email
    manually in App Store Connect, this secret is not needed.
  - Apple also requires Beta App Review contact details for external testing.
    The workflow reads existing App Store Connect values first and only fills
    blanks from `TESTFLIGHT_REVIEW_CONTACT_EMAIL`,
    `TESTFLIGHT_REVIEW_CONTACT_FIRST_NAME`,
    `TESTFLIGHT_REVIEW_CONTACT_LAST_NAME`, and
    `TESTFLIGHT_REVIEW_CONTACT_PHONE`. The contact email falls back to
    `TESTFLIGHT_FEEDBACK_EMAIL`; the other fields can also be filled manually
    in App Store Connect instead of storing more repo secrets.
  - `operation=configure_review` fills Beta App test info and Beta App Review
    details without submitting a build. Its log prints only configured/not
    configured booleans, not raw contact values.
  - `operation=submit_review` sets export compliance, fills the Beta App test
    info and Beta App Review details from configured secrets when needed, and
    submits the selected build for external Beta App Review without changing
    tester/group membership.
  - `operation=distribute` assigns the latest or selected build to that external
    TestFlight group. External distribution may require Beta App Review before testers
    can install.
  This workflow calls fastlane's Spaceship/App Store Connect API directly instead of the
  `pilot builds/list/add/distribute` subcommands, because Apple's current API no longer
  accepts the legacy `buildDeliveries` relationship used by those listing paths.
- Install from TestFlight on your iPhone after the build is assigned to a tester/group;
  the watch app installs alongside it.

## Export compliance

The current iOS and Watch apps declare `ITSAppUsesNonExemptEncryption=false` in
their `Info.plist` files. They do not ship proprietary encryption; network
transport uses Apple/system HTTPS stacks, and the only explicit CryptoKit use is
a local SHA-256 fingerprint for Garmin session deduplication.

If App Store Connect asks which encryption algorithms the app uses, choose the
option equivalent to **none of the algorithms listed above**. Do not select
proprietary/custom encryption, and do not upload an export compliance document
for the current build. The `iOS TestFlight Testers` workflow also sets
`usesNonExemptEncryption=false` on the selected TestFlight build before external
distribution.

## Backend reachability (for the app to load data)

The phone needs the API reachable. `server_v2` ships via `fly.toml` / `render.yaml` /
`Dockerfile` — deploy it and point the TestFlight workflow `api_base_url` input or
repo variable `AI_CADDIE_API_BASE_URL` at the deployed host. The web app separately
uses `VITE_AI_CADDIE_API_BASE_URL`. Cloud deployment itself needs a fly.io or Render
token (the only other external switch). `VITE_AI_CADDIE_API_BASE_URL` is not a
native build setting.

Set `AI_CADDIE_API_BASE_URL` / `api_base_url` to the API origin only, for example
`https://api.example.com`; do not include a path, query string, fragment, or URL
credentials. If the URL is supplied after upload through the runtime Backend
screen, record the manual evidence with
`ops/phase6_external_readiness.py --native-runtime-api-configured
--native-runtime-api-source testflight_backend_screen`.

## Verification Boundary

The archive/sign/upload path runs on the GitHub macOS runner, not in this Linux workspace.
Run `iOS TestFlight (CD)` and use the Actions log as the source of truth for signing,
archive, export, and App Store Connect upload status.

Each build also emits `build/ios/release-provenance.json` beside the IPA. It binds
the IPA SHA-256, app/backend 40-character revisions, workflow run, marketing
version, build number, and API origin host. Phase 6 accepts this manifest only
when it is fresh and marked `uploadToTestflight: true`; artifact-only (`false`)
builds remain incomplete candidates. Manual review, tester, and install evidence
must name the same TestFlight build number. The runtime Backend-screen checkbox
is always a manual attestation and is never inferred from the build URL.

Before an upload, Fastlane requires all six signing secrets, a public HTTPS
origin, and an authenticated `/api/v2/health` plus `/api/v2/readiness` preflight
with the expected backend revision. Tokens are passed to curl through the
environment and are not written to logs or provenance.
