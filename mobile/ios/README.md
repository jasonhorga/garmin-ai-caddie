# AI Caddie iOS

This folder contains the native SwiftUI source for offline-first live round capture.

Linux verification in this repo covers shared JSON contracts and fixture consistency:

```bash
uv run python -m unittest tests.test_mobile_contracts -v
```

Native build and unit tests require macOS with Xcode:

```bash
xcodebuild test -scheme AICaddie -destination 'platform=iOS Simulator,name=iPhone 16'
```

The iOS app should cache a live round package before play, append local events while offline, and sync the event log when network access returns.
