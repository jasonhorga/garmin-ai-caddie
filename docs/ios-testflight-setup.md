# iOS + Watch → TestFlight (no Mac needed)

This uses GitHub `macos-15` runners + fastlane `match` (certs/profiles in a private git
repo) + an App Store Connect API key. No local Mac and no interactive Apple login are
needed. Signing is isolated from other apps in `jasonhorga/garmin-ai-caddie-signing`.

## One-time turn-on (≈5 min)

1. **Add the signing secrets to this repo** (Settings → Secrets and variables → Actions):
   - `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_PRIVATE_KEY`  (App Store Connect API key, `.p8` content)
   - `MATCH_GIT_URL`, `MATCH_GIT_PRIVATE_KEY`, `MATCH_PASSWORD`, `MATCH_KEYCHAIN_PASSWORD`  (fastlane match)
   The match repo is private and project-specific:
   `git@github.com:jasonhorga/garmin-ai-caddie-signing.git`.
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
  optional release notes. It runs `xcodegen generate` →
  `fastlane ios beta` → archives the app (with embedded watch app) → uploads to TestFlight.
- Run the `iOS TestFlight Testers` workflow manually:
  - `operation=list` shows uploaded builds and currently visible testers.
  - `operation=add` adds comma-separated external tester emails to the configured group
    (default `Private Trial`).
  - `operation=distribute` assigns the latest or selected build to that external
    TestFlight group. External distribution may require Beta App Review before testers
    can install.
- Install from TestFlight on your iPhone after the build is assigned to a tester/group;
  the watch app installs alongside it.

## Backend reachability (for the app to load data)

The phone needs the API reachable. `server_v2` ships via `fly.toml` / `render.yaml` /
`Dockerfile` — deploy it and point the app's `VITE_AI_CADDIE_API_BASE_URL` / mobile base URL
at the deployed host. That needs a fly.io or Render token (the only other external switch).

## Verification Boundary

The archive/sign/upload path runs on the GitHub macOS runner, not in this Linux workspace.
Run `iOS TestFlight (CD)` and use the Actions log as the source of truth for signing,
archive, export, and App Store Connect upload status.
