import Foundation

/// One-hole review editor (B3 同屏改杆). Every gesture changes only this in-memory draft; Cancel
/// restores the original map and Save emits exactly one whole-hole correction event (plus one putt
/// correction when the putt count changed). The server diffs the whole-hole snapshot into the
/// per-change correction log, so the map, order, deletions and penalty stay on one source of truth.
@MainActor
public final class RoundEditModel: ObservableObject {
    @Published public var map: RoundHoleShotMap
    @Published public private(set) var isEditing = false
    @Published public private(set) var isSaving = false
    @Published public private(set) var hasUnsavedChanges = false
    @Published public var saveError: String?
    @Published public var draggingShotId: String?
    /// Only a full shot can be selected: putts are a count (推杆 −/+), never a shot to edit.
    @Published public var selectedShotId: String? {
        didSet {
            if let selectedShotId, !isEditableShot(selectedShotId) { self.selectedShotId = nil }
        }
    }
    /// The hole's putt count as the scorecard shows it (nil = not recorded). Edited with the bottom
    /// bar's 推杆 −/+ while no shot is selected; saved as a `putt_correction`.
    @Published public private(set) var putts: Int?
    /// A current prodgeometry revision plus its exact overlay owns the authoritative pixel frame.
    /// The PNG is transferred through the revision-bound topo URL rather than repeated inside every
    /// shot-map JSON response, so `map.image == nil` does not make that frame imprecise. CourseData
    /// and mapless states still edit ordered facts only and preserve source GPS endpoints.
    public var canEditPositions: Bool {
        guard !map.usesCourseDataFrame,
              map.geometryRevision != nil,
              let overlay = map.map?.overlay else { return false }
        return overlay.w > 0 && overlay.h > 0
    }

    private let sync: SyncClient
    private let roundRef: String
    /// The canonical round id for hole-level putt corrections (the stats read `{canonical}:{hole}`);
    /// the requested ref when the detail has not told us the canonical one.
    private let puttTargetRoundRef: String
    private let globalId: Int?
    private let backGlobalId: Int?
    private let nine: String?
    private let teeBox: String?
    private var originalMap: RoundHoleShotMap
    private var routeOrigin: [Int]?
    private var pendingSaveOp: RoundCorrectionOp?
    private var pendingPuttCorrection: HolePuttCorrection?
    private var originalPutts: Int?
    private var shotsChanged = false
    private let now: () -> Date

    public init(map: RoundHoleShotMap, sync: SyncClient, roundRef: String, globalId: Int? = nil, backGlobalId: Int? = nil, nine: String? = nil, teeBox: String? = nil,
                putts: Int? = nil, puttTargetRoundRef: String? = nil, now: @escaping () -> Date = Date.init) {
        self.map = map
        self.putts = putts
        self.originalPutts = putts
        self.now = now
        self.originalMap = map
        self.sync = sync
        self.roundRef = roundRef
        self.puttTargetRoundRef = puttTargetRoundRef.flatMap { $0.isEmpty ? nil : $0 } ?? roundRef
        self.globalId = globalId
        self.backGlobalId = backGlobalId
        self.nine = nine
        self.teeBox = teeBox
        self.routeOrigin = Self.resolvedRouteOrigin(in: map)
    }

    public func enterEdit() {
        guard !isSaving else { return }
        map = editableCopy(of: originalMap)
        routeOrigin = Self.resolvedRouteOrigin(in: originalMap)
        putts = originalPutts
        isEditing = true
        resetDraftState()
    }

    /// Discard the complete draft. No network request has occurred, so this is a real cancellation.
    public func cancelEdit() {
        guard !isSaving else { return }
        map = originalMap
        putts = originalPutts
        isEditing = false
        resetDraftState()
    }

    /// The scorecard can arrive after the map; adopt its putt count unless a draft is open.
    public func adoptRecordedPutts(_ value: Int?) {
        guard !isEditing, originalPutts != value else { return }
        originalPutts = value
        putts = value
    }

    /// Compatibility name for older call sites; leaving edit mode always means discarding its draft.
    public func exitEdit() { cancelEdit() }

    // MARK: - Draft-only operations

    /// Add a position to the draft immediately. It goes after the selected/explicit shot, otherwise at
    /// the end; ‹ › can then reorder it. Without an explicit club the club is guessed from the
    /// distance the new shot travelled (README §7) and left unconfirmed (no `manual` source) until
    /// the player picks one. No modal confirmation and no server write.
    @discardableResult
    public func addShot(
        px: [Double],
        club: String? = nil,
        lie: String? = nil,
        afterShotId: String? = nil
    ) -> String {
        guard canEditPositions else { return "" }
        let end = clampedPixel(px)
        let insertIndex: Int
        if let afterShotId,
           isEditableShot(afterShotId),
           let index = map.shots.firstIndex(where: { $0.id == afterShotId }) {
            insertIndex = index + 1
        } else {
            // Nothing selected: the new full shot goes after the last full shot, before any putts.
            insertIndex = map.shots.firstIndex(where: roundShotIsPutt) ?? map.shots.count
        }
        let previous = insertIndex > 0 ? map.shots[insertIndex - 1] : nil
        let shotId = "draft-\(UUID().uuidString.lowercased())"
        let start = previous?.end ?? routeOrigin ?? end
        let guessed = normalizedOptional(club) == nil
            ? RoundClubGuess.club(forYards: Self.yards(from: start, to: end, ppm: map.map?.overlay.ppm))
            : nil
        let shot = RoundShot(
            shotId: shotId,
            start: start,
            end: end,
            club: normalizedOptional(club) ?? guessed,
            lie: normalizedOptional(lie) ?? previous?.endLie,
            endLie: nil,
            shotType: "MANUAL",
            order: insertIndex + 1,
            clubSource: normalizedOptional(club) == nil ? nil : "manual",
            lieSource: normalizedOptional(lie) == nil ? nil : "manual",
            synthetic: false
        )
        map.shots.insert(shot, at: insertIndex)
        reconnectDraft()
        selectedShotId = shotId
        markChanged()
        return shotId
    }

    /// Live long-press drag preview. It remains local and is discarded with the rest of the draft.
    public func previewMove(shotId: String, px: [Double]) {
        guard canEditPositions, isEditableShot(shotId) else { return }
        if applyLandingMove(shotId: shotId, px: px) { markChanged() }
    }

    /// Finish a long-press drag locally. Save, not finger-up, owns persistence.
    public func move(shotId: String, px: [Double]) {
        guard canEditPositions, isEditableShot(shotId) else { return }
        guard applyLandingMove(shotId: shotId, px: px) else { return }
        selectedShotId = shotId
        markChanged()
    }

    public func editClub(shotId: String, _ value: String?) {
        guard isEditableShot(shotId) else { return }
        let changed = replaceShot(shotId) { shot in
            RoundShot(
                shotId: shot.shotId,
                start: shot.start,
                end: shot.end,
                club: normalizedOptional(value),
                lie: shot.lie,
                endLie: shot.endLie,
                shotType: shot.shotType,
                order: shot.order,
                clubSource: "manual",
                lieSource: shot.lieSource,
                synthetic: shot.synthetic,
                gpsAvailable: shot.gpsAvailable
            )
        }
        if changed { markChanged() }
    }

    public func editLie(shotId: String, _ value: String?) {
        guard isEditableShot(shotId) else { return }
        let changed = replaceShot(shotId) { shot in
            RoundShot(
                shotId: shot.shotId,
                start: shot.start,
                end: shot.end,
                club: shot.club,
                lie: normalizedOptional(value),
                endLie: shot.endLie,
                shotType: shot.shotType,
                order: shot.order,
                clubSource: shot.clubSource,
                lieSource: "manual",
                synthetic: shot.synthetic,
                gpsAvailable: shot.gpsAvailable
            )
        }
        if changed { markChanged() }
    }

    public func delete(shotId: String) {
        guard isEditableShot(shotId) else { return }
        map.shots.removeAll { $0.id == shotId }
        if selectedShotId == shotId { selectedShotId = nil }
        reconnectDraft()
        markChanged()
    }

    public func reorder(_ ids: [String]) {
        let byId = Dictionary(uniqueKeysWithValues: map.shots.map { ($0.id, $0) })
        guard ids.count == map.shots.count,
              Set(ids) == Set(byId.keys) else { return }
        guard ids != map.shots.map(\.id) else { return }
        // Putt rows keep their places; only full shots are reordered.
        for (index, shot) in map.shots.enumerated() where roundShotIsPutt(shot) {
            guard ids[index] == shot.id else { return }
        }
        map.shots = ids.compactMap { byId[$0] }
        reconnectDraft()
        markChanged()
    }

    public func setPenalty(_ value: Int) {
        let clamped = min(max(0, value), 100)
        guard clamped != map.manualPenalty else { return }
        map.manualPenalty = clamped
        markChanged()
    }

    /// ‹ › in the bottom bar: move one shot one place earlier (-1) or later (+1). The numbers, the
    /// chained starts and the selection follow the shot.
    public func moveShot(_ shotId: String, by offset: Int) {
        guard let index = map.shots.firstIndex(where: { $0.id == shotId }) else { return }
        let target = index + offset
        guard offset != 0, map.shots.indices.contains(target),
              isEditableShot(shotId), !roundShotIsPutt(map.shots[target]) else { return }
        var ids = map.shots.map(\.id)
        ids.swapAt(index, target)
        reorder(ids)
        selectedShotId = shotId
    }

    /// 推杆 −/+ (only while no shot is selected). An unrecorded count starts from zero.
    public func adjustPutts(by delta: Int) {
        let next = min(max(0, (putts ?? 0) + delta), Self.maximumPutts)
        guard putts == nil || next != putts else { return }
        putts = next
        pendingPuttCorrection = nil
        refreshUnsavedState()
    }

    /// 罚杆 −/+ on the same bar; the stored manual penalty stays within the server's 0...100.
    public func adjustPenalty(by delta: Int) {
        setPenalty(map.manualPenalty + delta)
    }

    public static let maximumPutts = 9

    /// The number a shot carries on the map: its place among the full shots (putts are counted by
    /// 推杆 −/+, not numbered), so read and edit mode show the same numbers.
    public func displayNumber(of shotId: String) -> Int? {
        let fullShots = map.shots.filter { !roundShotIsPutt($0) }
        if let index = fullShots.firstIndex(where: { $0.id == shotId }) { return index + 1 }
        return map.shots.firstIndex(where: { $0.id == shotId }).map { $0 + 1 }
    }

    public var fullShotCount: Int { map.shots.filter { !roundShotIsPutt($0) }.count }

    /// Straight-line yards of one draft shot (the bottom bar's "第 N 杆 · D 码").
    public func yards(of shotId: String) -> Int? {
        guard let shot = map.shots.first(where: { $0.id == shotId }) else { return nil }
        return Self.yards(from: shot.start, to: shot.end, ppm: map.map?.overlay.ppm)
    }

    // MARK: - Commit / refresh

    /// Persist the whole approved draft in one idempotent request. Returns true only after the server
    /// accepted it; a failure leaves the complete draft editable and retryable.
    public func save() async -> Bool {
        guard isEditing, !isSaving else { return false }
        guard hasUnsavedChanges else {
            map = originalMap
            putts = originalPutts
            isEditing = false
            resetDraftState()
            return true
        }

        isSaving = true
        saveError = nil
        let clientTime = RoundCorrectionClock.now(now())
        // Both writes are prepared once and reused on retry, so their idempotency keys never change
        // and an already-accepted half is simply acknowledged again by the server.
        if shotsChanged, pendingSaveOp == nil {
            pendingSaveOp = canEditPositions
                ? RoundCorrectionOp.replaceHoleShots(
                    hole: map.hole,
                    shots: map.shots,
                    manualPenalty: map.manualPenalty,
                    geometryRevision: map.geometryRevision,
                    clientTime: clientTime
                )
                : RoundCorrectionOp.replaceHoleFacts(
                    hole: map.hole,
                    shots: map.shots,
                    manualPenalty: map.manualPenalty,
                    clientTime: clientTime
                )
        }
        if let putts, putts != originalPutts, pendingPuttCorrection == nil {
            pendingPuttCorrection = HolePuttCorrection(
                roundRef: puttTargetRoundRef, hole: map.hole, to: putts, from: originalPutts, clientTime: clientTime
            )
        }
        do {
            if let operation = pendingSaveOp {
                try await sync.postRoundCorrection(roundRef: roundRef, operation)
            }
            if let correction = pendingPuttCorrection {
                try await sync.postHolePuttCorrection(correction)
            }
            originalPutts = putts
            if !shotsChanged {
                map = originalMap
            } else if let fresh = try? await sync.fetchRoundShotMap(roundRef: roundRef, hole: map.hole, globalId: globalId, backGlobalId: backGlobalId, nine: nine, teeBox: teeBox) {
                map = fresh
                originalMap = fresh
            } else {
                originalMap = map
            }
            routeOrigin = Self.resolvedRouteOrigin(in: originalMap)
            isSaving = false
            isEditing = false
            resetDraftState()
            return true
        } catch {
            isSaving = false
            saveError = "没有保存成功，草稿仍在；请检查网络后重试"
            return false
        }
    }

    /// Refresh only outside edit mode; an async read must never overwrite an unsaved draft.
    public func refetch() async {
        guard !isEditing,
              let fresh = try? await sync.fetchRoundShotMap(roundRef: roundRef, hole: map.hole, globalId: globalId, backGlobalId: backGlobalId, nine: nine, teeBox: teeBox) else {
            return
        }
        map = fresh
        originalMap = fresh
        routeOrigin = Self.resolvedRouteOrigin(in: fresh)
    }

    // MARK: - Helpers

    private func markChanged() {
        shotsChanged = true
        pendingSaveOp = nil
        refreshUnsavedState()
    }

    private func refreshUnsavedState() {
        hasUnsavedChanges = shotsChanged || putts != originalPutts
        saveError = nil
    }

    private func resetDraftState() {
        shotsChanged = false
        hasUnsavedChanges = false
        saveError = nil
        draggingShotId = nil
        selectedShotId = nil
        pendingSaveOp = nil
        pendingPuttCorrection = nil
    }

    nonisolated static func yards(from start: [Int]?, to end: [Int]?, ppm: Double?) -> Int? {
        guard let start, start.count >= 2, let end, end.count >= 2, let ppm, ppm > 0 else { return nil }
        let dx = Double(end[0] - start[0])
        let dy = Double(end[1] - start[1])
        return Int(((dx * dx + dy * dy).squareRoot() / ppm * 1.09361).rounded())
    }

    @discardableResult
    private func applyLandingMove(shotId: String, px: [Double]) -> Bool {
        guard let index = map.shots.firstIndex(where: { $0.id == shotId }) else { return false }
        let end = clampedPixel(px)
        let shot = map.shots[index]
        guard shot.end != end else { return false }
        map.shots[index] = RoundShot(
            shotId: shot.shotId,
            start: shot.start,
            end: end,
            club: shot.club,
            lie: shot.lie,
            endLie: shot.endLie,
            shotType: shot.shotType,
            order: shot.order,
            clubSource: shot.clubSource,
            lieSource: shot.lieSource,
            synthetic: shot.synthetic,
            gpsAvailable: shot.gpsAvailable
        )
        reconnectDraft()
        return true
    }

    @discardableResult
    private func replaceShot(_ id: String, transform: (RoundShot) -> RoundShot) -> Bool {
        guard let index = map.shots.firstIndex(where: { $0.id == id }) else { return false }
        let replacement = transform(map.shots[index])
        guard replacement != map.shots[index] else { return false }
        map.shots[index] = replacement
        return true
    }

    /// A full shot of the draft (putt rows are handled by the putts counter, fail-closed here).
    private func isEditableShot(_ id: String) -> Bool {
        guard let shot = map.shots.first(where: { $0.id == id }) else { return false }
        return !roundShotIsPutt(shot)
    }

    private func reconnectDraft() {
        var previousEnd: [Int]?
        var isFirstFullShot = true
        for index in map.shots.indices {
            let shot = map.shots[index]
            // Putt rows are never re-chained: their recorded positions stay as they were.
            let isPutt = roundShotIsPutt(shot)
            let start: [Int]?
            if isPutt || !canEditPositions {
                start = shot.start
            } else if isFirstFullShot {
                start = routeOrigin ?? shot.start
            } else {
                start = previousEnd ?? shot.start
            }
            map.shots[index] = RoundShot(
                shotId: shot.shotId,
                start: start,
                end: shot.end,
                club: shot.club,
                lie: shot.lie,
                endLie: shot.endLie,
                shotType: shot.shotType,
                order: index + 1,
                clubSource: shot.clubSource,
                lieSource: shot.lieSource,
                synthetic: shot.synthetic,
                gpsAvailable: shot.gpsAvailable
            )
            if !isPutt {
                isFirstFullShot = false
                previousEnd = canEditPositions ? shot.end : nil
            }
        }
    }

    private func editableCopy(of source: RoundHoleShotMap) -> RoundHoleShotMap {
        var seen = Set<String>()
        let candidates = canEditPositions
            ? source.shots
            : source.shots.filter { shot in
                guard !shot.synthetic,
                      let id = shot.shotId?.trimmingCharacters(in: .whitespacesAndNewlines) else {
                    return false
                }
                return !id.isEmpty
            }
        let shots = candidates.enumerated().map { index, shot -> RoundShot in
            let existing = shot.shotId?.trimmingCharacters(in: .whitespacesAndNewlines)
            let stableId: String
            if let existing, !existing.isEmpty, seen.insert(existing).inserted {
                stableId = existing
            } else {
                stableId = "draft-existing-\(UUID().uuidString.lowercased())"
                seen.insert(stableId)
            }
            return RoundShot(
                shotId: stableId,
                start: shot.start,
                end: shot.end,
                club: shot.club,
                lie: shot.lie,
                endLie: shot.endLie,
                shotType: shot.shotType,
                order: index + 1,
                clubSource: shot.clubSource,
                lieSource: shot.lieSource,
                synthetic: shot.synthetic,
                gpsAvailable: shot.gpsAvailable
            )
        }
        return RoundHoleShotMap(
            found: source.found,
            hole: source.hole,
            par: source.par,
            globalId: source.globalId,
            localHole: source.localHole,
            sourceRef: source.sourceRef,
            geometryRevision: source.geometryRevision,
            mapKind: source.mapKind,
            map: source.map,
            shots: shots,
            manualPenalty: source.manualPenalty,
            missingData: source.missingData
        )
    }

    private func clampedPixel(_ value: [Double]) -> [Int] {
        let x = value.indices.contains(0) && value[0].isFinite ? value[0] : 0
        let y = value.indices.contains(1) && value[1].isFinite ? value[1] : 0
        let roundedX = max(Int(x.rounded()), 0)
        let roundedY = max(Int(y.rounded()), 0)
        guard let overlay = map.map?.overlay else { return [roundedX, roundedY] }
        let width = max(overlay.w, 1)
        let height = max(overlay.h, 1)
        return [
            min(roundedX, width - 1),
            min(roundedY, height - 1),
        ]
    }

    private func normalizedOptional(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty || trimmed.caseInsensitiveCompare("unknown") == .orderedSame
            ? nil
            : trimmed
    }

    private static func resolvedRouteOrigin(in map: RoundHoleShotMap) -> [Int]? {
        if let start = map.shots.first?.start, start.count >= 2 { return start }
        guard let first = map.map?.overlay.route.first, first.count >= 2 else { return nil }
        return [Int(first[0].rounded()), Int(first[1].rounded())]
    }
}

/// Club guess for a shot added on the map (README §7 "球杆按距离预猜"): the club whose typical carry
/// is closest to the shot's straight-line yards. The table is the design prototype's; the bottom bar
/// lists the guess first and the player can always pick another club.
public enum RoundClubGuess {
    public static let typicalCarryYards: [(club: String, yards: Int)] = [
        ("一号木", 231), ("三号木", 210), ("五号木", 195), ("四号铁", 180), ("五号铁", 170),
        ("六号铁", 160), ("七号铁", 150), ("八号铁", 140), ("九号铁", 128), ("PW", 115),
        ("GW", 100), ("SW", 85), ("LW", 65),
    ]

    public static func club(forYards yards: Int?) -> String? {
        guard let yards, yards > 0 else { return nil }
        return typicalCarryYards.min { abs($0.yards - yards) < abs($1.yards - yards) }?.club
    }

    /// The pill row: the guess first, then the rest in bag order, the recorded club kept even when
    /// it is not in the list.
    public static func orderedClubs(guess: String?, current: String?, clubs: [String]) -> [String] {
        var options = roundEditClubOptions(current: current, clubs: clubs)
        if let guess, let index = options.firstIndex(of: guess) {
            options.remove(at: index)
            options.insert(guess, at: 0)
        } else if let guess {
            options.insert(guess, at: 0)
        }
        return options
    }
}
