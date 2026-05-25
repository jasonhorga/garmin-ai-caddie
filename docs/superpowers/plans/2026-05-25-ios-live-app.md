# iOS Live App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the iOS live app path for offline-first round packages, GPS/event capture, score/club input, photo/video capture, and sync.

**Architecture:** Create a native SwiftUI app under `mobile/ios`. The Linux remote can maintain contracts and source files, but native build/test execution requires macOS/Xcode. Non-native API contracts remain tested in this repo.

**Tech Stack:** SwiftUI, Swift Concurrency, CoreLocation, URLSession, local JSON event log, Python contract tests for shared fixtures.

---

## Files

Create:

- `mobile/contracts/live_round_package.schema.json`
- `mobile/contracts/live_round_event.schema.json`
- `tests/test_mobile_contracts.py`
- `mobile/ios/AICaddie/Models/LiveRoundPackage.swift`
- `mobile/ios/AICaddie/Models/LiveRoundEvent.swift`
- `mobile/ios/AICaddie/Services/OfflineStore.swift`
- `mobile/ios/AICaddie/Services/SyncClient.swift`
- `mobile/ios/AICaddie/Views/RoundHomeView.swift`
- `mobile/ios/AICaddie/Views/CurrentHoleView.swift`
- `mobile/ios/AICaddie/Views/CaddiePlanView.swift`

## Task 1: Shared Mobile Contracts

- [ ] Add JSON schema for `LiveRoundPackage`:
  - player profile
  - course id/name
  - holes
  - geometry coverage
  - club profiles
  - caddie decision endpoint URL
  - generated at
- [ ] Add JSON schema for `LiveRoundEvent`:
  - event id
  - round id
  - timestamp
  - hole
  - kind: `score|club|putt|penalty|note|location|photo|video|sync_marker`
  - payload
- [ ] Add Python tests validating fixture examples.
- [ ] Commit:

```bash
git add mobile/contracts tests/test_mobile_contracts.py
git commit -m "feat: add mobile live round contracts"
```

## Task 2: Swift Models

- [ ] Add Swift `Codable` models matching the JSON schemas.
- [ ] Include deterministic sample JSON in `mobile/ios/AICaddie/Fixtures/`.
- [ ] Add notes in `mobile/ios/README.md` with macOS verification command:

```bash
xcodebuild test -scheme AICaddie -destination 'platform=iOS Simulator,name=iPhone 16'
```

- [ ] Commit:

```bash
git add mobile/ios/AICaddie/Models mobile/ios/AICaddie/Fixtures mobile/ios/README.md
git commit -m "feat: add iOS live round models"
```

## Task 3: Offline Store And Sync Client

- [ ] Implement append-only local event log in `OfflineStore.swift`.
- [ ] Implement `SyncClient` with:
  - fetch round package
  - post event batch
  - retry with idempotency key
- [ ] Add Swift unit tests on macOS runner.
- [ ] Commit:

```bash
git add mobile/ios/AICaddie/Services mobile/ios/AICaddieTests
git commit -m "feat: add iOS offline event store"
```

## Task 4: Live Views

- [ ] Build SwiftUI views:
  - round home
  - current hole
  - caddie plan
  - quick score/putt/penalty/club input
  - sync status
- [ ] No marketing landing page.
- [ ] Commit:

```bash
git add mobile/ios/AICaddie/Views
git commit -m "feat: add iOS live round views"
```

## Task 5: Verification

- [ ] On Linux: run `uv run python -m unittest tests.test_mobile_contracts -v`.
- [ ] On macOS: run Xcode build/test command in `mobile/ios/README.md`.
- [ ] If macOS is unavailable, mark native build as environment-blocked, not product-blocked.
