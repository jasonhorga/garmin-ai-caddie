# Club-bag Manual Setup — iOS Slice Implementation Plan

> **For agentic workers:** iOS only validates on macOS CI (`native-mobile.yml`, xcodebuild test) — you CANNOT compile locally. Make precise, compiling Swift. The ONE locally-runnable gate is `tests/test_mobile_contracts.py` (it greps the iOS source) — TDD that. The design-snapshot (`DesignSnapshotTests`) renders the screen to a PNG artifact on CI for visual review.

**Goal:** Wire the existing iOS `ClubSettingsView` (today: toggle list, saves only to UserDefaults) to PERSIST the manual bag via the new backend `PUT /api/v2/players/me/clubs/bag`, and add an optional per-club DISTANCE input. The owner (admin token) edits "me"'s bag; members editing their own waits on the deferred Apple-sign-in slice.

**Architecture:** A new `zhName → backend token` table bridges the iOS catalog (Chinese display names) to the backend token vocabulary. `ClubSettingsContent` (presentational) gains a per-club editable distance (yards); `ClubSettingsView` gains `saveToBackend()` that builds a `[ManualClubInput]` (token + yards→metres) and PUTs it. The toggle path keeps calling `ClubBagStore.save(selected)` (local cache) unchanged.

**Tech Stack:** Swift / SwiftUI, `URLSession` (admin token header), stdlib `unittest` for the contract.

---

## File Structure
- **Create** `mobile/ios/AICaddie/Models/EffectiveClubBag.swift` — `ManualClubInput`, `EffectiveClubBagResponse`, `EffectiveClubBagClub` Codable structs.
- **Modify** `mobile/ios/AICaddie/Views/ClubBag.swift` — add `zhNameToBackendToken` (31 entries) + `backendToken(forZhName:)`; `ClubBagStore` manual-distance persistence (`manualDistances()`/`saveManualDistances()`, key `"ai-caddie.club-bag-distances-v1"`, `[String:Int]` zhName→yards) + `manualClubInputs(selected:distancesYd:)` payload builder.
- **Modify** `mobile/ios/AICaddie/Services/SyncClient.swift` — `putManualClubBag(playerId:String="me", clubs:[ManualClubInput])` (PUT) + `fetchEffectiveClubBag(playerId:String="me")` (GET).
- **Modify** `mobile/ios/AICaddie/Views/ClubSettingsView.swift` — `ClubSettingsContent` gains `@Binding var distancesYd: [String:Int]` + an editable distance `TextField` per SELECTED club; `ClubSettingsView` gains `@State distancesYd`, `saveToBackend()`, and a "保存到云端" button; keep `ClubBagStore.save(selected)` on toggle.
- **Modify** `tests/test_mobile_contracts.py` — add assertions for the new wiring; keep the 16 existing club-bag assertions.
- **Modify** `mobile/ios/AICaddieTests/DesignSnapshotTests.swift` — update the `ClubSettingsContent` snapshot call with sample `distancesYd`.

---

## Task 1: Models (`EffectiveClubBag.swift`)
- [ ] Create the file:
```swift
import Foundation

public struct ManualClubInput: Codable, Equatable {
    public let token: String
    public let customName: String?
    public let distanceM: Double?
    public init(token: String, customName: String? = nil, distanceM: Double? = nil) {
        self.token = token; self.customName = customName; self.distanceM = distanceM
    }
}

public struct EffectiveClubBagClub: Codable, Equatable, Identifiable {
    public var id: String { token }
    public let token: String
    public let zhName: String?
    public let customName: String?
    public let clubTypeId: Int?
    public let distanceM: Double?
    public let distanceSource: String?
}

public struct EffectiveClubBagResponse: Codable, Equatable {
    public let schema: String?
    public let source: String      // "manual" | "garmin" | "none"
    public let found: Bool
    public let clubs: [EffectiveClubBagClub]
}
```
- [ ] Commit: `feat(ios-clubs): effective club-bag + manual-input models`

## Task 2: Token mapping + store (`ClubBag.swift`)
- [ ] Add, next to `garminClubTypeZh`, the full reverse table (exactly these 31 entries):
```swift
public let zhNameToBackendToken: [String: String] = [
    "一号木": "driver", "三号木": "wood3", "五号木": "wood5", "七号木": "wood7",
    "一号小鸡腿": "hybrid1", "二号小鸡腿": "hybrid2", "三号小鸡腿": "hybrid3",
    "四号小鸡腿": "hybrid4", "五号小鸡腿": "hybrid5", "六号小鸡腿": "hybrid6",
    "一号铁": "iron1", "二号铁": "iron2", "三号铁": "iron3", "四号铁": "iron4",
    "五号铁": "iron5", "六号铁": "iron6", "七号铁": "iron7", "八号铁": "iron8", "九号铁": "iron9",
    "P 杆": "pw", "A 杆": "gw", "S 杆": "sw", "L 杆": "lw",
    "50° 挖起杆": "wedge50", "52° 挖起杆": "wedge52", "54° 挖起杆": "wedge54",
    "56° 挖起杆": "wedge56", "58° 挖起杆": "wedge58", "60° 挖起杆": "wedge60",
    "推杆": "putter",
]

public func backendToken(forZhName zhName: String) -> String? { zhNameToBackendToken[zhName] }
```
  (Verify each key string byte-for-byte equals the corresponding `CatalogClub.zhName` — including the spaces in `"P 杆"`, `"50° 挖起杆"`.)
- [ ] In `ClubBagStore`, add manual-distance persistence + the payload builder:
```swift
private static let distancesKey = "ai-caddie.club-bag-distances-v1"
static func manualDistancesYd() -> [String: Int] {
    (UserDefaults.standard.dictionary(forKey: distancesKey) as? [String: Int]) ?? [:]
}
static func saveManualDistancesYd(_ d: [String: Int]) {
    UserDefaults.standard.set(d, forKey: distancesKey)
}
// Build the PUT payload: backend token + yards->metres (the bag stores metres).
static func manualClubInputs(selected: Set<String>, distancesYd: [String: Int]) -> [ManualClubInput] {
    selected.compactMap { zh in
        guard let token = backendToken(forZhName: zh) else { return nil }
        let m = distancesYd[zh].map { Double(($0)) * 0.9144 }
        return ManualClubInput(token: token, customName: nil, distanceM: m.map { ($0).rounded() })
    }
}
```
- [ ] Commit: `feat(ios-clubs): zhName->backend token map + manual-distance store`

## Task 3: SyncClient methods (`SyncClient.swift`)
- [ ] Add (mirroring `fetchClubBag`'s exact pattern — `endpointURL`, admin-token header, `decoder`/`encoder`):
```swift
public func putManualClubBag(playerId: String = "me", clubs: [ManualClubInput]) async throws -> EffectiveClubBagResponse {
    var request = URLRequest(url: endpointURL("/api/v2/players/\(playerId)/clubs/bag"))
    request.httpMethod = "PUT"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    if let adminToken { request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token") }
    request.httpBody = try encoder.encode(ManualBagBody(clubs: clubs))
    let (data, response) = try await session.data(for: request)
    try validate(response: response, data: data)
    return try decoder.decode(EffectiveClubBagResponse.self, from: data)
}

public func fetchEffectiveClubBag(playerId: String = "me") async throws -> EffectiveClubBagResponse {
    var request = URLRequest(url: endpointURL("/api/v2/players/\(playerId)/clubs/bag"))
    if let adminToken { request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token") }
    let (data, response) = try await session.data(for: request)
    try validate(response: response, data: data)
    return try decoder.decode(EffectiveClubBagResponse.self, from: data)
}

private struct ManualBagBody: Encodable { let clubs: [ManualClubInput] }
```
  (The PUT body is `{"clubs":[...]}` — wrap in `ManualBagBody`. Confirm the client has an `encoder`; if not, add `private let encoder = JSONEncoder()` next to `decoder`.)
- [ ] Commit: `feat(ios-clubs): SyncClient put/fetch effective club bag`

## Task 4: ClubSettingsView — distance input + save
- [ ] `ClubSettingsContent`: add `@Binding var distancesYd: [String: Int]`. In `row(_:)`, when `isOn`, replace the read-only `Text(distanceText(...))` with an editable yards field prefilled from `distancesYd[zhName]` ?? the history `distanceText` number ?? "" — e.g. a `TextField("码", value:)`-style numeric entry bound to `distancesYd[zhName]` with `.keyboardType(.numberPad)`; keep the read-only `Text` for clubs not selected. Keep `Text(distanceText(...))` available (do not delete `distanceText`).
- [ ] `ClubSettingsView`: add `@State private var distancesYd: [String: Int] = ClubBagStore.manualDistancesYd()`; thread `distancesYd: $distancesYd` into `ClubSettingsContent`; add a `saveToBackend()` async method:
```swift
private func saveToBackend() async {
    ClubBagStore.saveManualDistancesYd(distancesYd)
    guard let apiBaseURL else { return }
    let client = SyncClient(baseURL: apiBaseURL, adminToken: adminToken)
    let inputs = ClubBagStore.manualClubInputs(selected: selected, distancesYd: distancesYd)
    _ = try? await client.putManualClubBag(clubs: inputs)
}
```
  and a "保存到云端" `Button` (next to / after the reset button) that calls it (e.g. `Task { await saveToBackend() }`); keep the existing per-toggle `ClubBagStore.save(selected)`.
- [ ] Commit: `feat(ios-clubs): editable per-club distance + 保存到云端 (PUT to backend)`

## Task 5: Contract test (`tests/test_mobile_contracts.py`) — TDD locally
- [ ] In `test_ios_live_views_define_expected_controls`, ADD (keep the 16 existing):
```python
self.assertIn("zhNameToBackendToken", club_bag)
self.assertIn("func manualClubInputs(", club_bag)
self.assertIn("func putManualClubBag(", sync_client)
self.assertIn("/api/v2/players/", sync_client)
self.assertIn("struct ManualClubInput", _read_required_source(self, IOS_DIR / "Models" / "EffectiveClubBag.swift"))
self.assertIn("struct EffectiveClubBagResponse", _read_required_source(self, IOS_DIR / "Models" / "EffectiveClubBag.swift"))
self.assertIn("保存到云端", club_settings)
self.assertIn("saveToBackend(", club_settings)
```
- [ ] Run locally: `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest tests.test_mobile_contracts -v` → expect PASS (and FAIL first if you run it before the Swift changes — TDD).
- [ ] Commit: `test(mobile-contracts): assert the iOS manual-bag-to-backend wiring`

## Task 6: Design snapshot (`DesignSnapshotTests.swift`)
- [ ] Update the single `captureScreen(ClubSettingsContent(...), named: "club-settings")` call to pass the new `distancesYd` binding with sample values (e.g. `["七号铁": 140, "P 杆": 110]`) via a local `@State`-like constant binding (`.constant([...])`). Match the new `ClubSettingsContent` signature.
- [ ] Commit: `test(ios-snapshot): render updated club-settings with distance inputs`

## Self-Review
- **Token table:** all 31 `zhName` keys byte-for-byte match `CatalogClub.zhName` (mind `"P 杆"`/`"50° 挖起杆"` spacing).
- **Units:** UI is yards; `distanceM` payload is metres (`yards*0.9144`); prefill metres→yards. Backend validates `0 < distanceM <= 400` m (≈437 yd cap).
- **Contract:** the 16 existing assertions still pass (toggle still calls `ClubBagStore.save(selected)`; `用 Garmin 球包重置` + `clearManual()` kept).
- **No backend change** — this slice is iOS + the contract test only. macOS CI (compile + snapshot) + `test_mobile_contracts` are the gates; no homeserver deploy.
