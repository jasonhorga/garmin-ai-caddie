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

- Run the `iOS TestFlight (CD)` workflow manually from `integration/v2` with
  optional release notes and optional `api_base_url`. It runs `xcodegen generate` →
  `fastlane ios beta` → archives the app (with embedded watch app) → uploads to TestFlight.
  If `api_base_url` is blank, the workflow falls back to repo variable
  `AI_CADDIE_API_BASE_URL`; if both are blank, the app keeps the offline/fixture fallback.
- Run the `iOS TestFlight Testers` workflow manually:
  - `operation=list` shows uploaded builds, TestFlight groups, and currently visible testers.
  - `operation=add` adds comma-separated external tester emails to the configured group
    (default `Private Trial`).
  - `operation=distribute` assigns the latest or selected build to that external
    TestFlight group. External distribution may require Beta App Review before testers
    can install.
  - For automated external Beta App Review submission, set the
    `TESTFLIGHT_FEEDBACK_EMAIL` repo secret. It is intentionally secret-only
    because this repo is public. If you fill the Beta App feedback email
    manually in App Store Connect, this secret is not needed.
  This workflow calls fastlane's Spaceship/App Store Connect API directly instead of the
  `pilot builds/list/add/distribute` subcommands, because Apple's current API no longer
  accepts the legacy `buildDeliveries` relationship used by those listing paths.
- Install from TestFlight on your iPhone after the build is assigned to a tester/group;
  the watch app installs alongside it.

## Backend reachability (for the app to load data)

The phone needs the API reachable. `server_v2` ships via `fly.toml` / `render.yaml` /
`Dockerfile` — deploy it and point the TestFlight workflow `api_base_url` input or
repo variable `AI_CADDIE_API_BASE_URL` at the deployed host. The web app separately
uses `VITE_AI_CADDIE_API_BASE_URL`. Cloud deployment itself needs a fly.io or Render
token (the only other external switch).

## Verification Boundary

The archive/sign/upload path runs on the GitHub macOS runner, not in this Linux workspace.
Run `iOS TestFlight (CD)` and use the Actions log as the source of truth for signing,
archive, export, and App Store Connect upload status.
