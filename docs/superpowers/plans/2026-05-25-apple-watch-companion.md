# Apple Watch Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an Apple Watch companion for current-hole glance, quick input, and iPhone sync.

**Architecture:** Watch app depends on the iOS live event model. It does not call backend directly in this plan; it exchanges compact events through iPhone.

**Tech Stack:** SwiftUI, WatchConnectivity, shared live event models.

---

## Files

Create:

- `mobile/ios/AICaddieWatch/Models/WatchRoundState.swift`
- `mobile/ios/AICaddieWatch/Services/WatchSyncClient.swift`
- `mobile/ios/AICaddieWatch/Views/WatchHoleView.swift`
- `mobile/ios/AICaddieWatch/Views/WatchInputView.swift`
- `mobile/ios/AICaddieWatch/Views/WatchCaddieGlanceView.swift`
- `mobile/ios/AICaddieWatchTests/WatchRoundStateTests.swift`

## Task 1: Watch State Model

- [ ] Add compact state:
  - round id
  - hole
  - par
  - distance
  - selected club
  - score
  - putts
  - penalty count
  - caddie confidence
- [ ] Add Swift tests for encode/decode.
- [ ] Commit:

```bash
git add mobile/ios/AICaddieWatch/Models mobile/ios/AICaddieWatchTests
git commit -m "feat: add watch round state model"
```

## Task 2: Watch Sync

- [ ] Implement WatchConnectivity client:
  - receive state from iPhone
  - send quick input event to iPhone
  - queue input when iPhone unavailable
- [ ] Add tests around queue serialization where possible.
- [ ] Commit:

```bash
git add mobile/ios/AICaddieWatch/Services mobile/ios/AICaddieWatchTests
git commit -m "feat: add watch sync client"
```

## Task 3: Watch Views

- [ ] Add:
  - current hole glance
  - club suggestion
  - score stepper
  - putt stepper
  - penalty button
  - selected club picker
- [ ] Keep text short enough for Watch display.
- [ ] Commit:

```bash
git add mobile/ios/AICaddieWatch/Views
git commit -m "feat: add watch companion views"
```

## Task 4: Verification

- [ ] On macOS:

```bash
xcodebuild test -scheme AICaddieWatch -destination 'platform=watchOS Simulator,name=Apple Watch Series 10 (46mm)'
```

- [ ] If macOS/watchOS simulator is unavailable, keep source committed and record environment blocker in final verification notes.
