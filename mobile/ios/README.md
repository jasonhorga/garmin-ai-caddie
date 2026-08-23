# AI Caddie iOS

This folder contains the native SwiftUI source for offline-first live round capture.

Linux verification in this repo covers shared JSON contracts and fixture consistency:

```bash
uv run python -m unittest tests.test_mobile_contracts -v
```

Native build and unit tests require macOS with Xcode:

```bash
xcodegen generate --spec mobile/ios/project.yml --project-root .
xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddie -destination "platform=iOS Simulator,name=iPhone 16,OS=latest"
xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddieWatch -destination "platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest"
python3 ops/write_native_build_evidence.py
```

The iOS app should cache a live round package before play, append local events while offline, and sync the event log when network access returns.

For TestFlight builds, provide a public backend URL through the `iOS TestFlight (CD)`
workflow `api_base_url` input or the repo variable `AI_CADDIE_API_BASE_URL`. The value
is baked into the iOS `Info.plist` as `AICaddieAPIBaseURL`; leaving it blank preserves
the offline/fixture fallback.

TestFlight/Release builds never embed the owner admin token. They authenticate
through Sign in with Apple and forward that scoped session to the Watch. The
runtime Backend screen remains a DEBUG/CI aid for simulator verification; its
admin-token fallback is not part of the Release credential path.
