import Foundation

/// The review-edit state machine for one hole. Holds a mutable copy of the shot map and applies each
/// edit **optimistically** (shows instantly — the "保存永远成功" feel), then POSTs it in the background
/// via ``SyncClient``. On post failure it keeps the local change (surfaces ``pendingError``); a later
/// ``refetch()`` reconciles with the authoritative server view. Mirrors the backend op semantics.
@MainActor
public final class RoundEditModel: ObservableObject {
    @Published public var map: RoundHoleShotMap
    @Published public var isEditing: Bool = false
    @Published public var pendingError: String?
    /// The shot currently being dragged (drives the drag handle highlight + magnifier).
    @Published public var draggingShotId: String?

    private let sync: SyncClient
    private let roundRef: String

    public init(map: RoundHoleShotMap, sync: SyncClient, roundRef: String) {
        self.map = map
        self.sync = sync
        self.roundRef = roundRef
    }

    public func enterEdit() { isEditing = true }
    public func exitEdit() { isEditing = false; draggingShotId = nil }

    // MARK: edits — optimistic local change first, then background POST

    /// Insert a shot at the tapped pixel, between the shot after `afterShotId` and its neighbour
    /// (assume-forward). Locally drawn immediately; the real stable id arrives on refetch.
    public func addShot(px: [Double], club: String?, lie: String?, afterShotId: String?) {
        let idx: Int
        if let after = afterShotId, let i = map.shots.firstIndex(where: { $0.id == after }) {
            idx = i + 1
        } else {
            idx = 0
        }
        let prevEnd = idx > 0 ? map.shots[idx - 1].end : nil
        let endPx = [Int(px[0].rounded()), Int(px[1].rounded())]
        let shot = RoundShot(shotId: "local-\(UUID().uuidString)", start: prevEnd ?? endPx, end: endPx,
                             club: club, lie: lie, endLie: nil, shotType: "MANUAL", order: nil,
                             clubSource: club != nil ? "manual" : nil,
                             lieSource: lie != nil ? "manual" : nil, synthetic: false)
        map.shots.insert(shot, at: idx)
        if idx + 1 < map.shots.count {
            map.shots[idx + 1] = withEndpoints(map.shots[idx + 1], start: endPx)
        }
        post(.add(px: px, club: club, lie: lie, after: afterShotId)) { await self.refetch() }
    }

    /// Live drag preview: reposition the landing locally on every drag frame so both connecting lines
    /// rubber-band under the finger. **No network** — the committed POST happens once on release (`move`).
    public func previewMove(shotId: String, px: [Double]) {
        applyLandingMove(shotId: shotId, px: px)
    }

    /// Drag a landing to a new pixel (on release): same local reposition as the live preview, then POST.
    public func move(shotId: String, px: [Double]) {
        applyLandingMove(shotId: shotId, px: px)
        #if DEBUG
        // Real-app screenshot tests must exercise the production drag gesture without mutating the
        // owner's Garmin history. Requiring BOTH flags keeps this narrowly scoped to the explicit
        // UI-test evidence run; Release builds always take the normal POST path below.
        let environment = ProcessInfo.processInfo.environment
        if environment["UITEST_MODE"] == "1",
           environment["UITEST_READ_ONLY_DRAG_PREVIEW"] == "1" {
            return
        }
        #endif
        post(.move(shotId, px: px))
    }

    /// Move a landing point locally: set this shot's `end` **and the next shot's `start`** (the same
    /// physical point) to the dragged pixel, so the incoming *and* outgoing lines follow the drag.
    private func applyLandingMove(shotId: String, px: [Double]) {
        guard let i = map.shots.firstIndex(where: { $0.id == shotId }) else { return }
        let endPx = [Int(px[0].rounded()), Int(px[1].rounded())]
        map.shots[i] = withEndpoints(map.shots[i], end: endPx)
        let next = i + 1
        if next < map.shots.count {
            map.shots[next] = withEndpoints(map.shots[next], start: endPx)
        }
    }

    private func withEndpoints(_ s: RoundShot, start: [Int]? = nil, end: [Int]? = nil) -> RoundShot {
        RoundShot(shotId: s.shotId, start: start ?? s.start, end: end ?? s.end, club: s.club, lie: s.lie,
                  endLie: s.endLie, shotType: s.shotType, order: s.order,
                  clubSource: s.clubSource, lieSource: s.lieSource, synthetic: s.synthetic)
    }

    public func editClub(shotId: String, _ v: String) {
        replaceShot(shotId) { s in
            RoundShot(shotId: s.shotId, start: s.start, end: s.end, club: v, lie: s.lie,
                      endLie: s.endLie, shotType: s.shotType, order: s.order,
                      clubSource: "manual", lieSource: s.lieSource, synthetic: s.synthetic)
        }
        post(.editClub(shotId, v))
    }

    public func editLie(shotId: String, _ v: String) {
        replaceShot(shotId) { s in
            RoundShot(shotId: s.shotId, start: s.start, end: s.end, club: s.club, lie: v,
                      endLie: s.endLie, shotType: s.shotType, order: s.order,
                      clubSource: s.clubSource, lieSource: "manual", synthetic: s.synthetic)
        }
        post(.editLie(shotId, v))
    }

    /// Delete a shot directly (no reason, no undo — design §8). Deleting every shot is fine: the hole
    /// never "bricks", you can tap the map to add one back.
    public func delete(shotId: String) {
        map.shots.removeAll { $0.id == shotId }
        post(.delete(shotId))
    }

    /// Reorder the landing list to the given shotId order.
    public func reorder(_ ids: [String]) {
        var byId: [String: RoundShot] = [:]
        for s in map.shots { byId[s.id] = s }
        let reordered = ids.compactMap { byId[$0] }
        if reordered.count == map.shots.count { map.shots = reordered }
        post(.reorder(ids))
    }

    /// Set this hole's manual penalty count (the +/− stepper).
    public func setPenalty(_ v: Int) {
        let clamped = max(0, v)
        map.manualPenalty = clamped
        post(.setPenalty(hole: map.hole, clamped))
    }

    /// Silently reconcile with the authoritative server shot map (keeps local on failure).
    public func refetch() async {
        if let fresh = try? await sync.fetchRoundShotMap(roundRef: roundRef, hole: map.hole) {
            map = fresh
        }
    }

    // MARK: helpers

    private func replaceShot(_ id: String, _ transform: (RoundShot) -> RoundShot) {
        if let i = map.shots.firstIndex(where: { $0.id == id }) {
            map.shots[i] = transform(map.shots[i])
        }
    }

    private func post(_ op: RoundCorrectionOp, then after: (() async -> Void)? = nil) {
        Task {
            do {
                try await sync.postRoundCorrection(roundRef: roundRef, op)
                if let after { await after() }
            } catch {
                pendingError = "这条改动先显示着,存的时候没成,稍后会自动对齐"
            }
        }
    }
}
