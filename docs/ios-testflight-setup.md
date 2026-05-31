# iOS + Watch → TestFlight (no Mac needed)

This mirrors the sibling **gomoku** setup: GitHub `macos-15` runners + fastlane `match`
(certs/profiles in a private git repo) + an App Store Connect API key. No local Mac, no
interactive Apple login. Same Apple account as gomoku (**Team `6HB84897DJ`**), so the
**existing gomoku signing secrets are reused** — you do not create a new Apple setup.

## One-time turn-on (≈5 min)

1. **Add the 6 signing secrets to this repo** (Settings → Secrets and variables → Actions),
   copying the **same values already configured for gomoku** — or, cleaner, promote them to
   **organization-level secrets** shared by both repos:
   - `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_PRIVATE_KEY`  (App Store Connect API key, `.p8` content)
   - `MATCH_GIT_URL`, `MATCH_PASSWORD`, `MATCH_KEYCHAIN_PASSWORD`  (fastlane match)
   `match` stores multiple app identifiers in one repo, so gomoku's match repo works as-is.
2. **Run the `iOS Signing Bootstrap` workflow** once (Actions → iOS Signing Bootstrap → Run
   workflow). It now **auto-creates the App Store Connect app record** (via `create_app_online`
   using the API key — no manual registration) for `com.ai-caddie.mobile`, registers the app +
   watch App IDs, and writes the certs/profiles into the match repo. (Idempotent — safe if the
   app already exists.)

That's it — no manual App Store Connect form. After step 2, the app is registered and signing
is ready.

## Shipping a build

- Push a change under `mobile/ios/**` to `integration/v2`, **or** run the `iOS TestFlight (CD)`
  workflow manually (with optional release notes). It runs `xcodegen generate` →
  `fastlane ios beta` → archives the app (with embedded watch app) → uploads to TestFlight.
- Install from TestFlight on your iPhone; the watch app installs alongside it.

## How it maps to gomoku

| | gomoku | AI Caddie |
|---|---|---|
| Runner | `macos-15` | `macos-15` |
| Signing | fastlane `match` (git) + ASC API key | same secrets, same match repo |
| Team | `6HB84897DJ` | `6HB84897DJ` |
| Project | Godot export → `gomoku.xcodeproj` | `xcodegen` → `AICaddieNative.xcodeproj` |
| Scheme / bundle | `gomoku` / `com.jasonhorga.gomoku` | `AICaddie` / `com.ai-caddie.mobile` (+ `.watchkitapp`) |
| Lanes | `bootstrap_signing`, `beta` | same |

## Backend reachability (for the app to load data)

The phone needs the API reachable. `server_v2` ships via `fly.toml` / `render.yaml` /
`Dockerfile` — deploy it and point the app's `VITE_AI_CADDIE_API_BASE_URL` / mobile base URL
at the deployed host. That needs a fly.io or Render token (the only other external switch).

## Not verifiable from Linux

The fastlane lanes + workflows are a faithful mirror of gomoku's working setup, but the
archive/sign/upload only runs on the macOS runner. Expect the **first** `iOS TestFlight` run to
surface a small project-specific tweak (watch-app provisioning, entitlements, or build settings);
relay that CI log and it's a quick fix.
