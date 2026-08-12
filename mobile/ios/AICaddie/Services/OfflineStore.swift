import Foundation

public struct PendingMediaAttachment: Codable, Equatable, Identifiable {
    public let id: String
    public let eventId: String
    public let roundId: String
    public let hole: Int
    public let targetId: String
    public let assetLocalId: String
    public let mediaKind: String
    public let fileName: String
    public let fileURL: URL
    public let capturedAt: String
}

public struct LiveRoundStateSnapshot: Codable, Equatable {
    public let roundId: String
    public let activeHole: Int
    public let holes: [LiveHoleStateSnapshot]
    /// Hole numbers with an explicit score event. `holes` also contains default UI state for every
    /// package hole, so its count is not round progress.
    public let scoredHoles: [Int]

    public init(roundId: String, activeHole: Int, holes: [LiveHoleStateSnapshot], scoredHoles: [Int] = []) {
        self.roundId = roundId
        self.activeHole = activeHole
        self.holes = holes
        self.scoredHoles = scoredHoles
    }

    public func holeState(for hole: Int) -> LiveHoleStateSnapshot? {
        holes.first { state in
            state.hole == hole
        }
    }
}

public struct LiveHoleStateSnapshot: Codable, Equatable, Identifiable {
    public var id: Int { hole }

    public let roundId: String
    public let hole: Int
    public let par: Int
    public var score: Int
    public var putts: Int
    public var penaltyCount: Int
    public var selectedClub: String
    public var selectedShotType: String
    public var selectedStrategyMode: String
    public var distanceToPinM: Double?
    public var lie: String
    public var latitude: Double?
    public var longitude: Double?
    public var horizontalAccuracyM: Double?
    public var targetLatitude: Double?
    public var targetLongitude: Double?
    public var targetKind: String?
    public var updatedAt: String?

    public func hasSameRestorableFields(as other: LiveHoleStateSnapshot) -> Bool {
        roundId == other.roundId
            && hole == other.hole
            && par == other.par
            && score == other.score
            && putts == other.putts
            && penaltyCount == other.penaltyCount
            && selectedClub == other.selectedClub
            && selectedShotType == other.selectedShotType
            && selectedStrategyMode == other.selectedStrategyMode
            && distanceToPinM == other.distanceToPinM
            && lie == other.lie
            && latitude == other.latitude
            && longitude == other.longitude
            && horizontalAccuracyM == other.horizontalAccuracyM
            && targetLatitude == other.targetLatitude
            && targetLongitude == other.targetLongitude
            && targetKind == other.targetKind
    }

    /// Save-only fields — score / putts / penalty — are persisted only on an explicit
    /// Save (`submitEvents`), so a blanket restore on *any* incoming event or remote
    /// sync would silently revert a value the user has edited but not yet saved (P0-5).
    /// Reconcile field-by-field: a field whose on-screen value still matches the
    /// snapshot we last synced to (`lastApplied`) is clean and adopts this snapshot's
    /// value; a field that has diverged from the baseline — or has no baseline yet —
    /// is a live local edit and is preserved.
    public func reconciledSaveOnlyFields(
        currentScore: Int,
        currentPutts: Int,
        currentPenaltyCount: Int,
        lastApplied: LiveHoleStateSnapshot?
    ) -> (score: Int, putts: Int, penaltyCount: Int) {
        func resolve(_ current: Int, _ incoming: Int, _ baseline: Int?) -> Int {
            guard let baseline, current == baseline else { return current }
            return incoming
        }
        return (
            score: resolve(currentScore, score, lastApplied?.score),
            putts: resolve(currentPutts, putts, lastApplied?.putts),
            penaltyCount: resolve(currentPenaltyCount, penaltyCount, lastApplied?.penaltyCount)
        )
    }
}

private enum NullableNumberPayload {
    case missing
    case null
    case number(Double)
}

public final class OfflineStore {
    private let directoryURL: URL
    private let logURL: URL
    private let packagesDirectoryURL: URL
    private let currentPackageURL: URL
    private let homePackageURL: URL
    private let pendingMediaDirectoryURL: URL
    private let pendingMediaIndexURL: URL
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    public init(directoryURL: URL) {
        self.directoryURL = directoryURL
        self.logURL = directoryURL.appendingPathComponent("events.jsonl")
        self.packagesDirectoryURL = directoryURL.appendingPathComponent("packages", isDirectory: true)
        self.currentPackageURL = directoryURL.appendingPathComponent("current_package.json")
        self.homePackageURL = directoryURL.appendingPathComponent("home_package.json")
        self.pendingMediaDirectoryURL = directoryURL.appendingPathComponent("pending_media", isDirectory: true)
        self.pendingMediaIndexURL = directoryURL.appendingPathComponent("pending_media.jsonl")
        self.encoder = JSONEncoder()
        self.decoder = JSONDecoder()
    }

    public convenience init() {
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("AICaddie", isDirectory: true)
        self.init(directoryURL: directory)
    }

    public func saveRoundPackage(_ package: LiveRoundPackage) throws {
        try FileManager.default.createDirectory(at: packagesDirectoryURL, withIntermediateDirectories: true)
        let encoded = try encoder.encode(package)
        try encoded.write(to: packageURL(roundId: package.roundId), options: [.atomic])
        try encoded.write(to: currentPackageURL, options: [.atomic])
        AICaddieLog.storage.debug("Saved round package \(package.roundId, privacy: .public) (\(package.holes.count, privacy: .public) holes)")
    }

    public func loadRoundPackage(roundId: String) throws -> LiveRoundPackage? {
        let url = packageURL(roundId: roundId)
        guard FileManager.default.fileExists(atPath: url.path) else {
            return nil
        }
        return try decoder.decode(LiveRoundPackage.self, from: Data(contentsOf: url))
    }

    public func loadCurrentRoundPackage() throws -> LiveRoundPackage? {
        guard FileManager.default.fileExists(atPath: currentPackageURL.path) else {
            return nil
        }
        return try decoder.decode(LiveRoundPackage.self, from: Data(contentsOf: currentPackageURL))
    }

    /// The roundId of the most recent REAL hole event (score/putt/club/location, hole > 0), or nil.
    /// The event log is the source of truth for "a round is in progress" — so resume is driven by it,
    /// not by the `current_package.json` pointer (which non-remote/cached start paths can fail to write).
    public func inProgressRoundId() throws -> String? {
        var roundId: String?
        for event in try loadEvents() where event.kind != .syncMarker && event.hole > 0 {
            roundId = event.roundId
        }
        return roundId
    }

    /// The package to resume on launch: the in-progress round derived from the EVENT LOG (its saved
    /// package always exists — a round can't start without one), falling back to the current-package
    /// pointer. This makes resume robust even when the pointer is missing/stale (e.g. an offline start
    /// that never wrote it, or a schema-skewed pointer after an app update) — recorded holes survive.
    public func loadResumablePackage() throws -> LiveRoundPackage? {
        if let roundId = try inProgressRoundId() {
            // A corrupt per-round package file must NOT abort resume: fall through to the
            // current-package pointer rather than throwing out of bootstrap (which would land the
            // player on the Hub with the in-progress round hidden).
            if let package = try? loadRoundPackage(roundId: roundId) {
                return package
            }
            AICaddieLog.storage.error("Resumable package unreadable for \(roundId, privacy: .public); using current pointer")
        }
        return try loadCurrentRoundPackage()
    }

    /// True iff the round has at least one real recorded hole event (score/putt/club/location/…),
    /// i.e. play actually started. Used to decide whether to RESUME an in-progress round on
    /// relaunch (and show the 进行中 card) vs treat the cached package as just home data.
    public func hasRecordedEvents(roundId: String) throws -> Bool {
        try loadEvents().contains { event in
            event.roundId == roundId && event.kind != .syncMarker && event.hole > 0
        }
    }

    /// Home/landing package (most-played course data for the Hub's choices). Persisted to a
    /// SEPARATE file so it never becomes the "current round" pointer — only a started round
    /// (saveRoundPackage) is the active round that resumes on relaunch.
    public func saveHomePackage(_ package: LiveRoundPackage) throws {
        let encoded = try encoder.encode(package)
        try encoded.write(to: homePackageURL, options: [.atomic])
    }

    public func loadHomePackage() throws -> LiveRoundPackage? {
        guard FileManager.default.fileExists(atPath: homePackageURL.path) else {
            return nil
        }
        return try decoder.decode(LiveRoundPackage.self, from: Data(contentsOf: homePackageURL))
    }

    /// Forget a round entirely (discard/cancel): clear the active-package pointer + its
    /// cached package, and drop its events from the log so a discarded round never
    /// resurfaces on relaunch or syncs to the backend.
    public func discardRound(roundId: String) throws {
        try? FileManager.default.removeItem(at: currentPackageURL)
        try? FileManager.default.removeItem(at: packageURL(roundId: roundId))
        let remaining = (try? loadEvents())?.filter { $0.roundId != roundId } ?? []
        if remaining.isEmpty {
            try? FileManager.default.removeItem(at: logURL)
        } else {
            var data = Data()
            for event in remaining {
                data.append(try encoder.encode(event))
                data.append(Data([0x0A]))
            }
            try data.write(to: logURL, options: [.atomic])
        }
        AICaddieLog.storage.debug("Discarded round \(roundId, privacy: .public)")
    }

    public func appendEvent(_ event: LiveRoundEvent) throws {
        try FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        let encoded = try encoder.encode(event)
        if FileManager.default.fileExists(atPath: logURL.path) {
            let handle = try FileHandle(forWritingTo: logURL)
            try handle.seekToEnd()
            try handle.write(contentsOf: encoded)
            try handle.write(contentsOf: Data([0x0A]))
            try handle.close()
        } else {
            var data = encoded
            data.append(Data([0x0A]))
            try data.write(to: logURL, options: [.atomic])
        }
        AICaddieLog.storage.debug("Saved live event \(String(describing: event.kind), privacy: .public) hole \(event.hole, privacy: .public)")
    }

    public func containsEvent(eventId: String) throws -> Bool {
        try loadEvents().contains { event in
            event.eventId == eventId
        }
    }

    public func loadEvents() throws -> [LiveRoundEvent] {
        guard FileManager.default.fileExists(atPath: logURL.path) else {
            return []
        }
        let data = try Data(contentsOf: logURL)
        guard let text = String(data: data, encoding: .utf8) else {
            return []
        }
        // Skip (don't throw on) malformed lines. appendEvent writes the JSON and the trailing
        // newline as two non-atomic FileHandle writes; if iOS kills the app mid-write, the last
        // line is a truncated JSON fragment. A throwing decode there used to abort the whole load,
        // which silently dropped resume → the in-progress round looked lost on relaunch. Losing at
        // most that one half-written event keeps every prior recorded score intact.
        var events: [LiveRoundEvent] = []
        for line in text.split(separator: "\n") {
            do {
                events.append(try decoder.decode(LiveRoundEvent.self, from: Data(line.utf8)))
            } catch {
                AICaddieLog.storage.error("Skipping malformed event line (truncation/schema): \(String(describing: error), privacy: .public)")
            }
        }
        return events
    }

    public func loadPendingEvents(roundId: String? = nil) throws -> [LiveRoundEvent] {
        let events = try loadEvents()
            .filter { event in
                roundId == nil || event.roundId == roundId
            }
        let lastSyncMarkerIndex = events.lastIndex(where: { event in
            event.kind == .syncMarker
        })
        let candidates: [LiveRoundEvent]
        if let lastSyncMarkerIndex {
            candidates = Array(events[events.index(after: lastSyncMarkerIndex)...])
        } else {
            candidates = events
        }
        return candidates.filter { event in
            event.kind != .syncMarker
        }
    }

    public func appendSyncMarker(roundId: String, timestamp: String) throws {
        let result = SyncResult(accepted: 0, duplicate: false)
        try appendSyncMarker(roundId: roundId, timestamp: timestamp, result: result)
    }

    public func appendSyncMarker(roundId: String, timestamp: String, result: SyncResult) throws {
        let event = LiveRoundEvent(
            eventId: UUID().uuidString,
            roundId: roundId,
            timestamp: timestamp,
            hole: 0,
            kind: .syncMarker,
            payload: [
                "status": .string("synced"),
                "source": .string("ios_sync"),
                "acceptedEventIds": .array(result.acceptedEventIds.map { .string($0) }),
                "duplicateEventIds": .array(result.duplicateEventIds.map { .string($0) }),
                "serverSequence": .number(Double(result.serverSequence)),
            ]
        )
        try appendEvent(event)
    }

    public func restoreLiveRoundState(roundId: String, package: LiveRoundPackage) throws -> LiveRoundStateSnapshot {
        let defaultClubName = package.clubProfiles.first?.clubName ?? ""
        var activeHole = package.holes.first?.number ?? 1
        let packageHoleNumbers = Set(package.holes.map(\.number))
        var scoredHoles = Set<Int>()
        var holeStates = Dictionary(
            uniqueKeysWithValues: package.holes.map { hole in
                (
                    hole.number,
                    defaultLiveHoleState(
                        roundId: roundId,
                        hole: hole.number,
                        par: hole.par,
                        selectedClub: defaultClubName,
                        selectedShotType: defaultShotType(package: package, hole: hole.number)
                    )
                )
            }
        )

        let events = try loadEvents()
        for event in events where event.roundId == roundId && event.kind != .syncMarker && event.hole > 0 {
            var state = holeStates[event.hole] ?? defaultLiveHoleState(
                roundId: roundId,
                hole: event.hole,
                par: 0,
                selectedClub: defaultClubName,
                selectedShotType: defaultShotType(package: package, hole: event.hole)
            )
            // Only advance activeHole to a hole that's actually in this package — after「移除加打的 9 洞」
            // the package is 1–9 but events may span 1–12, and the Hub's 继续这场 card requires
            // activeHole ∈ package.holes.
            if packageHoleNumbers.contains(event.hole) {
                activeHole = event.hole
            }

            switch event.kind {
            case .score:
                if let strokes = numberPayload("strokes", in: event.payload) {
                    state.score = Int(strokes)
                    if packageHoleNumbers.contains(event.hole) {
                        scoredHoles.insert(event.hole)
                    }
                }
            case .putt:
                if let putts = numberPayload("putts", in: event.payload) {
                    state.putts = Int(putts)
                }
            case .penalty:
                if let penalties = numberPayload("penalties", in: event.payload) {
                    state.penaltyCount = Int(penalties)
                }
            case .club:
                if let clubName = stringPayload("clubName", in: event.payload), !clubName.isEmpty {
                    state.selectedClub = clubName
                }
                if let shotType = stringPayload("shotType", in: event.payload) {
                    state.selectedShotType = shotType
                }
                if let strategyMode = stringPayload("strategyMode", in: event.payload) {
                    state.selectedStrategyMode = strategyMode
                }
                if let lie = stringPayload("lie", in: event.payload) {
                    state.lie = lie
                }
                switch optionalNumberPayload("distanceToPinM", in: event.payload) {
                case .number(let distanceToPinM):
                    state.distanceToPinM = distanceToPinM
                case .null:
                    state.distanceToPinM = nil
                case .missing:
                    break
                }
            case .location:
                if let latitude = numberPayload("latitude", in: event.payload) {
                    state.latitude = latitude
                }
                if let longitude = numberPayload("longitude", in: event.payload) {
                    state.longitude = longitude
                }
                if let targetLatitude = numberPayload("targetLatitude", in: event.payload) {
                    state.targetLatitude = targetLatitude
                }
                if let targetLongitude = numberPayload("targetLongitude", in: event.payload) {
                    state.targetLongitude = targetLongitude
                }
                if let targetKind = stringPayload("targetKind", in: event.payload) {
                    state.targetKind = targetKind
                }
                switch optionalNumberPayload("horizontalAccuracyM", in: event.payload) {
                case .number(let horizontalAccuracyM):
                    state.horizontalAccuracyM = horizontalAccuracyM
                case .null:
                    state.horizontalAccuracyM = nil
                case .missing:
                    break
                }
            case .note, .photo, .video, .syncMarker:
                break
            }
            state.updatedAt = event.timestamp
            holeStates[event.hole] = state
        }

        return LiveRoundStateSnapshot(
            roundId: roundId,
            activeHole: activeHole,
            holes: holeStates.values.sorted { lhs, rhs in
                lhs.hole < rhs.hole
            },
            scoredHoles: scoredHoles.sorted()
        )
    }

    public func savePendingMedia(
        data: Data,
        eventId: String,
        roundId: String,
        hole: Int,
        targetId: String,
        assetLocalId: String,
        mediaKind: String,
        fileName: String,
        capturedAt: String
    ) throws -> PendingMediaAttachment {
        let safeRoundId = safePathComponent(roundId)
        let safeFileName = safePathComponent(fileName)
        let mediaDirectory = pendingMediaDirectoryURL.appendingPathComponent(safeRoundId, isDirectory: true)
        try FileManager.default.createDirectory(at: mediaDirectory, withIntermediateDirectories: true)
        let fileURL = mediaDirectory.appendingPathComponent("\(UUID().uuidString)-\(safeFileName)")
        try data.write(to: fileURL, options: [.atomic])
        let attachment = PendingMediaAttachment(
            id: UUID().uuidString,
            eventId: eventId,
            roundId: roundId,
            hole: hole,
            targetId: targetId,
            assetLocalId: assetLocalId,
            mediaKind: mediaKind,
            fileName: fileURL.lastPathComponent,
            fileURL: fileURL,
            capturedAt: capturedAt
        )
        try appendPendingMedia(attachment)
        return attachment
    }

    public func attachUploadedMediaId(eventId: String, mediaId: String) throws {
        let events = try loadEvents()
        var changed = false
        let updatedEvents = events.map { event -> LiveRoundEvent in
            guard event.eventId == eventId, event.kind == .photo || event.kind == .video else {
                return event
            }
            var payload = event.payload
            payload["mediaId"] = .string(mediaId)
            changed = true
            return LiveRoundEvent(
                schema: event.schema,
                eventId: event.eventId,
                roundId: event.roundId,
                clientId: event.clientId,
                timestamp: event.timestamp,
                hole: event.hole,
                kind: event.kind,
                payload: payload
            )
        }
        if changed {
            try rewriteEvents(updatedEvents)
        }
    }

    public func loadPendingMedia(roundId: String? = nil) throws -> [PendingMediaAttachment] {
        guard FileManager.default.fileExists(atPath: pendingMediaIndexURL.path) else {
            return []
        }
        let data = try Data(contentsOf: pendingMediaIndexURL)
        guard let text = String(data: data, encoding: .utf8) else {
            return []
        }
        // Skip (don't throw on) a torn final line — the index is appended non-atomically, so an app
        // kill mid-write leaves a truncated JSON fragment; a throwing decode there used to drop ALL
        // pending media (P2, same truncation guard as loadEvents).
        var media: [PendingMediaAttachment] = []
        for line in text.split(separator: "\n") {
            do {
                let attachment = try decoder.decode(PendingMediaAttachment.self, from: Data(line.utf8))
                if roundId == nil || attachment.roundId == roundId {
                    media.append(attachment)
                }
            } catch {
                AICaddieLog.storage.error("Skipping malformed pending-media line (truncation/schema): \(String(describing: error), privacy: .public)")
            }
        }
        return media
    }

    public func removePendingMedia(ids: Set<String>) throws {
        guard !ids.isEmpty else {
            return
        }
        let allMedia = try loadPendingMedia()
        let remaining = allMedia.filter { !ids.contains($0.id) }
        let removed = allMedia.filter { ids.contains($0.id) }
        if remaining.isEmpty {
            do {
                try FileManager.default.removeItem(at: pendingMediaIndexURL)
            } catch {
                AICaddieLog.storage.error("Failed to remove pending-media index: \(String(describing: error), privacy: .public)")
            }
        } else {
            let lines = try remaining.map { media in
                String(data: try encoder.encode(media), encoding: .utf8) ?? "{}"
            }
            .joined(separator: "\n")
            var data = Data(lines.utf8)
            data.append(Data([0x0A]))
            try data.write(to: pendingMediaIndexURL, options: [.atomic])
        }
        for media in removed {
            do {
                try FileManager.default.removeItem(at: media.fileURL)
            } catch {
                AICaddieLog.storage.error("Failed to remove pending media file \(media.id, privacy: .public): \(String(describing: error), privacy: .public)")
            }
        }
    }

    private func packageURL(roundId: String) -> URL {
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        let fileName = roundId.addingPercentEncoding(withAllowedCharacters: allowed) ?? roundId.replacingOccurrences(of: "/", with: "_")
        return packagesDirectoryURL.appendingPathComponent("\(fileName).json")
    }

    private func appendPendingMedia(_ attachment: PendingMediaAttachment) throws {
        try FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        let encoded = try encoder.encode(attachment)
        if FileManager.default.fileExists(atPath: pendingMediaIndexURL.path) {
            let handle = try FileHandle(forWritingTo: pendingMediaIndexURL)
            try handle.seekToEnd()
            try handle.write(contentsOf: encoded)
            try handle.write(contentsOf: Data([0x0A]))
            try handle.close()
        } else {
            var data = encoded
            data.append(Data([0x0A]))
            try data.write(to: pendingMediaIndexURL, options: [.atomic])
        }
    }

    private func rewriteEvents(_ events: [LiveRoundEvent]) throws {
        try FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        let lines = try events.map { event in
            String(data: try encoder.encode(event), encoding: .utf8) ?? "{}"
        }
        .joined(separator: "\n")
        var data = Data(lines.utf8)
        if !events.isEmpty {
            data.append(Data([0x0A]))
        }
        try data.write(to: logURL, options: [.atomic])
    }

    private func defaultLiveHoleState(
        roundId: String,
        hole: Int,
        par: Int,
        selectedClub: String,
        selectedShotType: String
    ) -> LiveHoleStateSnapshot {
        LiveHoleStateSnapshot(
            roundId: roundId,
            hole: hole,
            par: par,
            score: par,
            putts: 2,
            penaltyCount: 0,
            selectedClub: selectedClub,
            selectedShotType: selectedShotType,
            selectedStrategyMode: "stock",
            distanceToPinM: nil,
            lie: "fairway",
            latitude: nil,
            longitude: nil,
            horizontalAccuracyM: nil,
            targetLatitude: nil,
            targetLongitude: nil,
            targetKind: nil,
            updatedAt: nil
        )
    }

    private func defaultShotType(package: LiveRoundPackage, hole: Int) -> String {
        package.caddieContextSeeds.first { seed in
            seed.hole == hole
        }?.shotTypes.first ?? "approach"
    }

    private func numberPayload(_ key: String, in payload: [String: JSONValue]) -> Double? {
        guard case .number(let value) = payload[key] else {
            return nil
        }
        return value
    }

    private func stringPayload(_ key: String, in payload: [String: JSONValue]) -> String? {
        guard case .string(let value) = payload[key] else {
            return nil
        }
        return value
    }

    private func optionalNumberPayload(_ key: String, in payload: [String: JSONValue]) -> NullableNumberPayload {
        guard let value = payload[key] else {
            return .missing
        }
        switch value {
        case .number(let raw):
            return .number(raw)
        case .null:
            return .null
        default:
            return .missing
        }
    }

    private func safePathComponent(_ value: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_."))
        let characters = value.unicodeScalars.map { scalar -> Character in
            allowed.contains(scalar) ? Character(scalar) : "_"
        }
        let safe = String(characters).trimmingCharacters(in: CharacterSet(charactersIn: "._-"))
        return safe.isEmpty ? "media" : safe
    }
}
