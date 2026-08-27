import Foundation

/// One-hole review editor. Every gesture changes only this in-memory draft; Cancel restores the
/// original map and Save emits exactly one whole-hole correction event. This keeps the visible map,
/// numbered list, order, deletions and penalty count on one source of truth without partial writes.
@MainActor
public final class RoundEditModel: ObservableObject {
    @Published public var map: RoundHoleShotMap
    @Published public private(set) var isEditing = false
    @Published public private(set) var isSaving = false
    @Published public private(set) var hasUnsavedChanges = false
    @Published public var saveError: String?
    @Published public var draggingShotId: String?
    @Published public var selectedShotId: String?
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
    private let globalId: Int?
    private let backGlobalId: Int?
    private let nine: String?
    private let teeBox: String?
    private var originalMap: RoundHoleShotMap
    private var routeOrigin: [Int]?
    private var pendingSaveOp: RoundCorrectionOp?

    public init(map: RoundHoleShotMap, sync: SyncClient, roundRef: String, globalId: Int? = nil, backGlobalId: Int? = nil, nine: String? = nil, teeBox: String? = nil) {
        self.map = map
        self.originalMap = map
        self.sync = sync
        self.roundRef = roundRef
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
        isEditing = true
        hasUnsavedChanges = false
        saveError = nil
        draggingShotId = nil
        selectedShotId = nil
        pendingSaveOp = nil
    }

    /// Discard the complete draft. No network request has occurred, so this is a real cancellation.
    public func cancelEdit() {
        guard !isSaving else { return }
        map = originalMap
        isEditing = false
        hasUnsavedChanges = false
        saveError = nil
        draggingShotId = nil
        selectedShotId = nil
        pendingSaveOp = nil
    }

    /// Compatibility name for older call sites; leaving edit mode always means discarding its draft.
    public func exitEdit() { cancelEdit() }

    // MARK: - Draft-only operations

    /// Add a position to the draft immediately. It goes after the selected/explicit shot, otherwise at
    /// the end; the numbered list can then reorder it. No modal confirmation and no server write.
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
           let index = map.shots.firstIndex(where: { $0.id == afterShotId }) {
            insertIndex = index + 1
        } else {
            insertIndex = map.shots.count
        }
        let previous = insertIndex > 0 ? map.shots[insertIndex - 1] : nil
        let shotId = "draft-\(UUID().uuidString.lowercased())"
        let shot = RoundShot(
            shotId: shotId,
            start: previous?.end ?? routeOrigin ?? end,
            end: end,
            club: normalizedOptional(club),
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
        guard canEditPositions else { return }
        if applyLandingMove(shotId: shotId, px: px) { markChanged() }
    }

    /// Finish a long-press drag locally. Save, not finger-up, owns persistence.
    public func move(shotId: String, px: [Double]) {
        guard canEditPositions else { return }
        guard applyLandingMove(shotId: shotId, px: px) else { return }
        selectedShotId = shotId
        markChanged()
    }

    public func editClub(shotId: String, _ value: String?) {
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
        guard map.shots.contains(where: { $0.id == shotId }) else { return }
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

    // MARK: - Commit / refresh

    /// Persist the whole approved draft in one idempotent request. Returns true only after the server
    /// accepted it; a failure leaves the complete draft editable and retryable.
    public func save() async -> Bool {
        guard isEditing, !isSaving else { return false }
        guard hasUnsavedChanges else {
            map = originalMap
            isEditing = false
            selectedShotId = nil
            return true
        }

        isSaving = true
        saveError = nil
        let operation = pendingSaveOp ?? (
            canEditPositions
                ? RoundCorrectionOp.replaceHoleShots(
                    hole: map.hole,
                    shots: map.shots,
                    manualPenalty: map.manualPenalty,
                    geometryRevision: map.geometryRevision
                )
                : RoundCorrectionOp.replaceHoleFacts(
                    hole: map.hole,
                    shots: map.shots,
                    manualPenalty: map.manualPenalty
                )
        )
        pendingSaveOp = operation
        do {
            try await sync.postRoundCorrection(roundRef: roundRef, operation)
            if let fresh = try? await sync.fetchRoundShotMap(roundRef: roundRef, hole: map.hole, globalId: globalId, backGlobalId: backGlobalId, nine: nine, teeBox: teeBox) {
                map = fresh
                originalMap = fresh
            } else {
                originalMap = map
            }
            routeOrigin = Self.resolvedRouteOrigin(in: originalMap)
            isSaving = false
            isEditing = false
            hasUnsavedChanges = false
            draggingShotId = nil
            selectedShotId = nil
            pendingSaveOp = nil
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
        hasUnsavedChanges = true
        saveError = nil
        pendingSaveOp = nil
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

    private func reconnectDraft() {
        var previousEnd: [Int]?
        for index in map.shots.indices {
            let shot = map.shots[index]
            let start = canEditPositions
                ? (index == 0 ? (routeOrigin ?? shot.start) : (previousEnd ?? shot.start))
                : shot.start
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
            previousEnd = canEditPositions ? shot.end : nil
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
