import Foundation
#if canImport(Darwin)
import Darwin
#elseif canImport(Glibc)
import Glibc
#endif

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

enum OfflineStoreError: Error, Equatable {
    case eventLogCorrupt
    case replayIdentityEnvelopeMismatch
    case replayDurabilityVerificationFailed
}

private struct ReplayEventIdentity: Hashable {
    let roundId: String
    let clientId: String
    let eventId: String
}

private enum JSONPrefixClassification: Equatable {
    case incomplete
    case complete
    case invalid
}

private struct JSONPrefixScanner {
    private static let maximumNestingDepth = 128

    private enum DocumentState: Equatable {
        case expectingRoot
        case afterRoot
    }

    private enum ArrayState {
        case firstValueOrEnd
        case valueAfterComma
        case commaOrEnd
    }

    private enum ObjectState {
        case firstKeyOrEnd
        case keyAfterComma
        case colon
        case value
        case commaOrEnd
    }

    private enum Frame {
        case array(ArrayState)
        case object(ObjectState)
    }

    private enum TokenResult {
        case complete(Data.Index)
        case incomplete
        case invalid
    }

    private let bytes: Data
    private var index: Data.Index
    private var documentState = DocumentState.expectingRoot
    private var frames: [Frame] = []

    static func classify(_ data: Data) -> JSONPrefixClassification {
        var scanner = JSONPrefixScanner(bytes: data)
        return scanner.classify()
    }

    private init(bytes: Data) {
        self.bytes = bytes
        self.index = bytes.startIndex
    }

    private mutating func classify() -> JSONPrefixClassification {
        while true {
            consumeWhitespace()
            if index == bytes.endIndex {
                if frames.isEmpty, documentState == .afterRoot {
                    return .complete
                }
                return .incomplete
            }

            guard !frames.isEmpty else {
                guard documentState == .expectingRoot else {
                    return .invalid
                }
                if let terminal = consumeValue() {
                    return terminal
                }
                continue
            }

            let frameIndex = frames.count - 1
            switch frames[frameIndex] {
            case .array(.firstValueOrEnd):
                if bytes[index] == 0x5D {
                    index += 1
                    frames.removeLast()
                    guard finishValue() else { return .invalid }
                } else if let terminal = consumeValue() {
                    return terminal
                }
            case .array(.valueAfterComma):
                if let terminal = consumeValue() {
                    return terminal
                }
            case .array(.commaOrEnd):
                switch bytes[index] {
                case 0x2C:
                    index += 1
                    frames[frameIndex] = .array(.valueAfterComma)
                case 0x5D:
                    index += 1
                    frames.removeLast()
                    guard finishValue() else { return .invalid }
                default:
                    return .invalid
                }
            case .object(.firstKeyOrEnd):
                if bytes[index] == 0x7D {
                    index += 1
                    frames.removeLast()
                    guard finishValue() else { return .invalid }
                } else if let terminal = consumeObjectKey(at: frameIndex) {
                    return terminal
                }
            case .object(.keyAfterComma):
                if let terminal = consumeObjectKey(at: frameIndex) {
                    return terminal
                }
            case .object(.colon):
                guard bytes[index] == 0x3A else { return .invalid }
                index += 1
                frames[frameIndex] = .object(.value)
            case .object(.value):
                if let terminal = consumeValue() {
                    return terminal
                }
            case .object(.commaOrEnd):
                switch bytes[index] {
                case 0x2C:
                    index += 1
                    frames[frameIndex] = .object(.keyAfterComma)
                case 0x7D:
                    index += 1
                    frames.removeLast()
                    guard finishValue() else { return .invalid }
                default:
                    return .invalid
                }
            }
        }
    }

    private mutating func consumeWhitespace() {
        while index < bytes.endIndex {
            switch bytes[index] {
            case 0x09, 0x0A, 0x0D, 0x20:
                index += 1
            default:
                return
            }
        }
    }

    private mutating func consumeValue() -> JSONPrefixClassification? {
        guard index < bytes.endIndex else { return .incomplete }
        switch bytes[index] {
        case 0x7B:
            guard frames.count < Self.maximumNestingDepth else { return .invalid }
            index += 1
            frames.append(.object(.firstKeyOrEnd))
            return nil
        case 0x5B:
            guard frames.count < Self.maximumNestingDepth else { return .invalid }
            index += 1
            frames.append(.array(.firstValueOrEnd))
            return nil
        case 0x22:
            let result = scanString(at: index)
            return finishToken(result)
        case 0x74:
            let result = scanLiteral([0x74, 0x72, 0x75, 0x65])
            return finishToken(result)
        case 0x66:
            let result = scanLiteral([0x66, 0x61, 0x6C, 0x73, 0x65])
            return finishToken(result)
        case 0x6E:
            let result = scanLiteral([0x6E, 0x75, 0x6C, 0x6C])
            return finishToken(result)
        case 0x2D, 0x30...0x39:
            let result = scanNumber()
            return finishToken(result)
        default:
            return .invalid
        }
    }

    private mutating func consumeObjectKey(
        at frameIndex: Int
    ) -> JSONPrefixClassification? {
        guard bytes[index] == 0x22 else { return .invalid }
        switch scanString(at: index) {
        case .complete(let nextIndex):
            index = nextIndex
            frames[frameIndex] = .object(.colon)
            return nil
        case .incomplete:
            return .incomplete
        case .invalid:
            return .invalid
        }
    }

    private mutating func finishToken(
        _ result: TokenResult
    ) -> JSONPrefixClassification? {
        switch result {
        case .complete(let nextIndex):
            index = nextIndex
            return finishValue() ? nil : .invalid
        case .incomplete:
            return .incomplete
        case .invalid:
            return .invalid
        }
    }

    private mutating func finishValue() -> Bool {
        guard !frames.isEmpty else {
            guard documentState == .expectingRoot else { return false }
            documentState = .afterRoot
            return true
        }

        let parentIndex = frames.count - 1
        switch frames[parentIndex] {
        case .array(.firstValueOrEnd), .array(.valueAfterComma):
            frames[parentIndex] = .array(.commaOrEnd)
            return true
        case .object(.value):
            frames[parentIndex] = .object(.commaOrEnd)
            return true
        default:
            return false
        }
    }

    private func scanString(at start: Int) -> TokenResult {
        var cursor = start + 1
        while cursor < bytes.endIndex {
            let byte = bytes[cursor]
            switch byte {
            case 0x22:
                return .complete(cursor + 1)
            case 0x5C:
                cursor += 1
                guard cursor < bytes.endIndex else { return .incomplete }
                switch bytes[cursor] {
                case 0x22, 0x2F, 0x5C, 0x62, 0x66, 0x6E, 0x72, 0x74:
                    cursor += 1
                case 0x75:
                    cursor += 1
                    for _ in 0..<4 {
                        guard cursor < bytes.endIndex else { return .incomplete }
                        guard Self.isHexDigit(bytes[cursor]) else { return .invalid }
                        cursor += 1
                    }
                default:
                    return .invalid
                }
            case 0x00...0x1F:
                return .invalid
            case 0x80...0xFF:
                switch scanUTF8Scalar(at: cursor) {
                case .complete(let nextIndex):
                    cursor = nextIndex
                case .incomplete:
                    return .incomplete
                case .invalid:
                    return .invalid
                }
            default:
                cursor += 1
            }
        }
        return .incomplete
    }

    private func scanUTF8Scalar(at start: Int) -> TokenResult {
        let first = bytes[start]
        let length: Int
        let secondRange: ClosedRange<UInt8>
        switch first {
        case 0xC2...0xDF:
            length = 2
            secondRange = 0x80...0xBF
        case 0xE0:
            length = 3
            secondRange = 0xA0...0xBF
        case 0xE1...0xEC, 0xEE...0xEF:
            length = 3
            secondRange = 0x80...0xBF
        case 0xED:
            length = 3
            secondRange = 0x80...0x9F
        case 0xF0:
            length = 4
            secondRange = 0x90...0xBF
        case 0xF1...0xF3:
            length = 4
            secondRange = 0x80...0xBF
        case 0xF4:
            length = 4
            secondRange = 0x80...0x8F
        default:
            return .invalid
        }

        guard start + 1 < bytes.endIndex else { return .incomplete }
        guard secondRange.contains(bytes[start + 1]) else { return .invalid }
        if length > 2 {
            for offset in 2..<length {
                guard start + offset < bytes.endIndex else { return .incomplete }
                guard (0x80...0xBF).contains(bytes[start + offset]) else {
                    return .invalid
                }
            }
        }
        return .complete(start + length)
    }

    private func scanLiteral(_ literal: [UInt8]) -> TokenResult {
        for (offset, expected) in literal.enumerated() {
            guard index + offset < bytes.endIndex else { return .incomplete }
            guard bytes[index + offset] == expected else { return .invalid }
        }
        return .complete(index + literal.count)
    }

    private func scanNumber() -> TokenResult {
        var cursor = index
        if bytes[cursor] == 0x2D {
            cursor += 1
            guard cursor < bytes.endIndex else { return .incomplete }
        }

        if bytes[cursor] == 0x30 {
            cursor += 1
        } else if (0x31...0x39).contains(bytes[cursor]) {
            cursor += 1
            while cursor < bytes.endIndex, Self.isDigit(bytes[cursor]) {
                cursor += 1
            }
        } else {
            return .invalid
        }

        if cursor < bytes.endIndex, bytes[cursor] == 0x2E {
            cursor += 1
            guard cursor < bytes.endIndex else { return .incomplete }
            guard Self.isDigit(bytes[cursor]) else { return .invalid }
            while cursor < bytes.endIndex, Self.isDigit(bytes[cursor]) {
                cursor += 1
            }
        }

        if cursor < bytes.endIndex,
           (bytes[cursor] == 0x65 || bytes[cursor] == 0x45) {
            cursor += 1
            guard cursor < bytes.endIndex else { return .incomplete }
            if bytes[cursor] == 0x2B || bytes[cursor] == 0x2D {
                cursor += 1
                guard cursor < bytes.endIndex else { return .incomplete }
            }
            guard Self.isDigit(bytes[cursor]) else { return .invalid }
            while cursor < bytes.endIndex, Self.isDigit(bytes[cursor]) {
                cursor += 1
            }
        }
        return .complete(cursor)
    }

    private static func isDigit(_ byte: UInt8) -> Bool {
        (0x30...0x39).contains(byte)
    }

    private static func isHexDigit(_ byte: UInt8) -> Bool {
        (0x30...0x39).contains(byte)
            || (0x41...0x46).contains(byte)
            || (0x61...0x66).contains(byte)
    }
}

private let REDACTED_LOCAL_MEDIA_URL = "[REDACTED_LOCAL_MEDIA_URL]"
private let REDACTED_MOBILE_PATH = "[REDACTED_PATH]"

public final class OfflineStore {
    private let trustedDirectoryAnchor: URL
    private let directoryURL: URL
    private let logURL: URL
    private let packagesDirectoryURL: URL
    private let currentPackageURL: URL
    private let homePackageURL: URL
    private let pendingMediaDirectoryURL: URL
    private let pendingMediaIndexURL: URL
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
    private let syncEventLogFile: (URL) throws -> Void
    private let syncEventLogDirectory: (URL) throws -> Void
    private let eventLogLock = NSLock()

    private static func nearestExistingDirectoryAncestor(of url: URL) -> URL {
        var candidate = url.standardizedFileURL.resolvingSymlinksInPath()
        while true {
            var isDirectory = ObjCBool(false)
            if FileManager.default.fileExists(
                atPath: candidate.path,
                isDirectory: &isDirectory
            ), isDirectory.boolValue {
                return candidate
            }
            let parent = candidate.deletingLastPathComponent()
            if parent.path == candidate.path {
                return candidate
            }
            candidate = parent.standardizedFileURL.resolvingSymlinksInPath()
        }
    }

    convenience init(directoryURL: URL) {
        let resolvedDirectory = directoryURL.standardizedFileURL.resolvingSymlinksInPath()
        let trustedDirectoryAnchor = Self.nearestExistingDirectoryAncestor(
            of: resolvedDirectory.deletingLastPathComponent()
        )
        self.init(
            directoryURL: resolvedDirectory,
            trustedDirectoryAnchor: trustedDirectoryAnchor,
            syncEventLogFile: { try Self.synchronizeFile(at: $0) },
            syncEventLogDirectory: { try Self.synchronizeDirectory(at: $0) }
        )
    }

    convenience init(
        directoryURL: URL,
        syncEventLogFile: @escaping (URL) throws -> Void,
        syncEventLogDirectory: @escaping (URL) throws -> Void
    ) {
        let resolvedDirectory = directoryURL.standardizedFileURL.resolvingSymlinksInPath()
        let trustedDirectoryAnchor = Self.nearestExistingDirectoryAncestor(
            of: resolvedDirectory.deletingLastPathComponent()
        )
        self.init(
            directoryURL: resolvedDirectory,
            trustedDirectoryAnchor: trustedDirectoryAnchor,
            syncEventLogFile: syncEventLogFile,
            syncEventLogDirectory: syncEventLogDirectory
        )
    }

    init(
        directoryURL: URL,
        trustedDirectoryAnchor: URL,
        syncEventLogFile: @escaping (URL) throws -> Void,
        syncEventLogDirectory: @escaping (URL) throws -> Void
    ) {
        let resolvedAnchor = trustedDirectoryAnchor.standardizedFileURL
            .resolvingSymlinksInPath()
        let resolvedDirectory = directoryURL.standardizedFileURL.resolvingSymlinksInPath()
        self.trustedDirectoryAnchor = resolvedAnchor
        self.directoryURL = resolvedDirectory
        self.logURL = resolvedDirectory.appendingPathComponent("events.jsonl")
        self.packagesDirectoryURL = resolvedDirectory.appendingPathComponent(
            "packages",
            isDirectory: true
        )
        self.currentPackageURL = resolvedDirectory.appendingPathComponent("current_package.json")
        self.homePackageURL = resolvedDirectory.appendingPathComponent("home_package.json")
        self.pendingMediaDirectoryURL = resolvedDirectory.appendingPathComponent(
            "pending_media",
            isDirectory: true
        )
        self.pendingMediaIndexURL = resolvedDirectory.appendingPathComponent("pending_media.jsonl")
        self.encoder = JSONEncoder()
        self.decoder = JSONDecoder()
        self.syncEventLogFile = syncEventLogFile
        self.syncEventLogDirectory = syncEventLogDirectory
    }

    public convenience init() {
        let trustedDirectoryAnchor = URL(
            fileURLWithPath: NSHomeDirectory(),
            isDirectory: true
        ).standardizedFileURL.resolvingSymlinksInPath()
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("AICaddie", isDirectory: true)
        self.init(
            directoryURL: directory,
            trustedDirectoryAnchor: trustedDirectoryAnchor,
            syncEventLogFile: { try Self.synchronizeFile(at: $0) },
            syncEventLogDirectory: { try Self.synchronizeDirectory(at: $0) }
        )
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
        try withEventLogLock {
            try repairTornEventLogEOFIfNeededUnlocked()
            let remaining = try loadEventsUnlocked(strict: true).filter { $0.roundId != roundId }
            if remaining.isEmpty {
                try? FileManager.default.removeItem(at: logURL)
            } else {
                try rewriteEventsUnlocked(remaining)
            }
        }
        try? FileManager.default.removeItem(at: currentPackageURL)
        try? FileManager.default.removeItem(at: packageURL(roundId: roundId))
        AICaddieLog.storage.debug("Discarded round \(roundId, privacy: .public)")
    }

    public func appendEvent(_ event: LiveRoundEvent) throws {
        try withEventLogLock {
            try validateEventLogDirectoryContainment()
            try repairTornEventLogEOFIfNeededUnlocked()
            _ = try loadEventsUnlocked(strict: true)
            try appendEventUnlocked(event)
        }
    }

    private func appendEventUnlocked(_ event: LiveRoundEvent) throws {
        try ensureEventLogDirectoryDurable()
        let transport = transportEvent(event)
        var encoded = try encoder.encode(transport)
        encoded.append(Data([0x0A]))
        if FileManager.default.fileExists(atPath: logURL.path) {
            let handle = try FileHandle(forWritingTo: logURL)
            do {
                try handle.seekToEnd()
                try handle.write(contentsOf: encoded)
                try handle.close()
            } catch {
                try? handle.close()
                throw error
            }
            try syncEventLogFile(logURL)
            try syncEventLogDirectory(directoryURL)
        } else {
            try writeEventLogAtomicallyAndDurably(encoded)
        }
        AICaddieLog.storage.debug("Saved live event \(String(describing: transport.kind), privacy: .public) hole \(transport.hole, privacy: .public)")
    }

    public func containsEvent(eventId: String) throws -> Bool {
        try loadEvents().contains { event in
            event.eventId == eventId
        }
    }

    public func applyReplayEvents(_ replayEvents: [LiveRoundEvent]) throws -> Bool {
        try withEventLogLock {
            try validateEventLogDirectoryContainment()
            try repairTornEventLogEOFIfNeededUnlocked()
            let transportReplayEvents = replayEvents.map { transportEvent($0) }
            var eventsByIdentity = try replayEventsByIdentity(
                try loadEventsStrictlyForReplayUnlocked()
            )
            if !transportReplayEvents.isEmpty,
               FileManager.default.fileExists(atPath: logURL.path) {
                try establishFreshEventLogBarrierUnlocked()
            }

            var appendedAny = false
            for event in transportReplayEvents {
                let identity = replayIdentity(event)
                if let existing = eventsByIdentity[identity] {
                    guard existing == event else {
                        throw OfflineStoreError.replayIdentityEnvelopeMismatch
                    }
                    continue
                }
                try appendEventUnlocked(event)
                eventsByIdentity[identity] = event
                appendedAny = true
            }

            let durableEvents = try loadEventsStrictlyForReplayUnlocked()
            let durableEventsByIdentity = try replayEventsByIdentity(durableEvents)
            for event in transportReplayEvents {
                guard let durable = durableEventsByIdentity[replayIdentity(event)] else {
                    throw OfflineStoreError.replayDurabilityVerificationFailed
                }
                guard durable == event else {
                    throw OfflineStoreError.replayIdentityEnvelopeMismatch
                }
            }
            return appendedAny
        }
    }

    public func loadEvents() throws -> [LiveRoundEvent] {
        try withEventLogLock {
            try validateEventLogDirectoryContainment()
            try loadEventsUnlocked(strict: false)
        }
    }

    private func loadEventsStrictlyForReplayUnlocked() throws -> [LiveRoundEvent] {
        try loadEventsUnlocked(strict: true)
    }

    private func loadEventsUnlocked(strict: Bool) throws -> [LiveRoundEvent] {
        guard FileManager.default.fileExists(atPath: logURL.path) else {
            return []
        }
        let data = try Data(contentsOf: logURL)
        guard !data.isEmpty else {
            return []
        }
        if strict, !data.isEmpty, data.last != 0x0A {
            throw OfflineStoreError.eventLogCorrupt
        }
        let hasTrailingNewline = data.last == 0x0A
        var lines = data.split(separator: 0x0A, omittingEmptySubsequences: false)
        if hasTrailingNewline, lines.last?.isEmpty == true {
            lines.removeLast()
        }
        var events: [LiveRoundEvent] = []
        for (index, line) in lines.enumerated() {
            if line.isEmpty {
                throw OfflineStoreError.eventLogCorrupt
            }
            do {
                let decoded = try decoder.decode(LiveRoundEvent.self, from: Data(line))
                events.append(transportEvent(decoded))
            } catch {
                let lineData = Data(line)
                let isUnterminatedFinalLine = !hasTrailingNewline && index == lines.count - 1
                if !strict,
                   isUnterminatedFinalLine,
                   JSONPrefixScanner.classify(lineData) == .incomplete {
                    AICaddieLog.storage.error("Skipping torn event-log EOF fragment: \(String(describing: error), privacy: .public)")
                    continue
                }
                throw OfflineStoreError.eventLogCorrupt
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
            if package.holes.contains(where: { $0.number == event.hole }) {
                activeHole = event.hole
            }

            switch event.kind {
            case .score:
                if let strokes = numberPayload("strokes", in: event.payload) {
                    state.score = Int(strokes)
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
            }
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

    private func withEventLogLock<T>(_ operation: () throws -> T) rethrows -> T {
        eventLogLock.lock()
        defer { eventLogLock.unlock() }
        return try operation()
    }

    private static func synchronizeFile(at url: URL) throws {
        let handle = try FileHandle(forWritingTo: url)
        do {
            try handle.synchronize()
            try handle.close()
        } catch {
            try? handle.close()
            throw error
        }
    }

    private static func synchronizeDirectory(at url: URL) throws {
        let descriptor = url.withUnsafeFileSystemRepresentation { path -> Int32 in
            guard let path else { return -1 }
            return open(path, O_RDONLY)
        }
        guard descriptor >= 0 else {
            throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno))
        }
        defer { _ = close(descriptor) }
        guard fsync(descriptor) == 0 else {
            throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno))
        }
    }

    private func validateEventLogDirectoryContainment() throws {
        _ = try eventLogDirectoryCreationParents()
    }

    private func eventLogDirectoryCreationParents() throws -> [URL] {
        let resolvedDirectory = directoryURL.standardizedFileURL.resolvingSymlinksInPath()
        let anchorComponents = trustedDirectoryAnchor.pathComponents
        let directoryComponents = resolvedDirectory.pathComponents
        var anchorIsDirectory = ObjCBool(false)
        guard FileManager.default.fileExists(
                  atPath: trustedDirectoryAnchor.path,
                  isDirectory: &anchorIsDirectory
              ),
              anchorIsDirectory.boolValue,
              trustedDirectoryAnchor.isFileURL,
              resolvedDirectory.isFileURL,
              directoryComponents.count >= anchorComponents.count,
              Array(directoryComponents.prefix(anchorComponents.count)) == anchorComponents
        else {
            throw OfflineStoreError.eventLogCorrupt
        }

        var parents: [URL] = []
        var current = trustedDirectoryAnchor
        for component in directoryComponents.dropFirst(anchorComponents.count) {
            parents.append(current)
            current.appendPathComponent(component, isDirectory: true)
        }
        return parents
    }

    private func ensureEventLogDirectoryDurable() throws {
        try validateEventLogDirectoryContainment()
        try FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        for parent in try eventLogDirectoryCreationParents() {
            try syncEventLogDirectory(parent)
        }
    }

    private func establishFreshEventLogBarrierUnlocked() throws {
        try ensureEventLogDirectoryDurable()
        guard FileManager.default.fileExists(atPath: logURL.path) else {
            throw OfflineStoreError.replayDurabilityVerificationFailed
        }
        try syncEventLogFile(logURL)
        try syncEventLogDirectory(directoryURL)
    }

    private func writeEventLogAtomicallyAndDurably(_ data: Data) throws {
        try data.write(to: logURL, options: [.atomic])
        try syncEventLogFile(logURL)
        try syncEventLogDirectory(directoryURL)
    }

    private func repairTornEventLogEOFIfNeededUnlocked() throws {
        try validateEventLogDirectoryContainment()
        guard FileManager.default.fileExists(atPath: logURL.path) else {
            return
        }
        let data = try Data(contentsOf: logURL)
        guard !data.isEmpty, data.last != 0x0A else {
            return
        }
        let lastNewline = data.lastIndex(of: 0x0A)
        let tailStart = lastNewline.map { data.index(after: $0) } ?? data.startIndex
        let tail = Data(data[tailStart..<data.endIndex])
        switch JSONPrefixScanner.classify(tail) {
        case .complete:
            guard (try? decoder.decode(LiveRoundEvent.self, from: tail)) != nil else {
                throw OfflineStoreError.eventLogCorrupt
            }
            var terminated = data
            terminated.append(Data([0x0A]))
            try ensureEventLogDirectoryDurable()
            try writeEventLogAtomicallyAndDurably(terminated)
        case .incomplete:
            let durablePrefix = lastNewline.map { Data(data[...$0]) } ?? Data()
            try ensureEventLogDirectoryDurable()
            try writeEventLogAtomicallyAndDurably(durablePrefix)
        case .invalid:
            throw OfflineStoreError.eventLogCorrupt
        }
    }

    private func replayIdentity(_ event: LiveRoundEvent) -> ReplayEventIdentity {
        ReplayEventIdentity(
            roundId: event.roundId,
            clientId: event.clientId ?? "",
            eventId: event.eventId
        )
    }

    private func replayEventsByIdentity(
        _ events: [LiveRoundEvent]
    ) throws -> [ReplayEventIdentity: LiveRoundEvent] {
        var eventsByIdentity: [ReplayEventIdentity: LiveRoundEvent] = [:]
        for event in events {
            let identity = replayIdentity(event)
            if let existing = eventsByIdentity[identity] {
                guard existing == event else {
                    throw OfflineStoreError.replayIdentityEnvelopeMismatch
                }
                continue
            }
            eventsByIdentity[identity] = event
        }
        return eventsByIdentity
    }

    private func transportEvent(_ event: LiveRoundEvent) -> LiveRoundEvent {
        var payload = event.payload.mapValues { transportValue($0) }
        if event.kind == .photo || event.kind == .video {
            switch payload["fileURL"] {
            case .some(.string(let value)) where !value.isEmpty:
                payload["fileURL"] = .string(REDACTED_LOCAL_MEDIA_URL)
            case .some(.bool(_)), .some(.number(_)), .some(.object(_)), .some(.array(_)):
                payload["fileURL"] = .string(REDACTED_LOCAL_MEDIA_URL)
            case .none, .some(.null), .some(.string(_)):
                break
            }
        }
        return LiveRoundEvent(
            schema: redactedTransportText(event.schema),
            eventId: event.eventId,
            roundId: event.roundId,
            clientId: event.clientId,
            timestamp: redactedTransportText(event.timestamp),
            hole: event.hole,
            kind: event.kind,
            payload: payload
        )
    }

    private func transportValue(_ value: JSONValue) -> JSONValue {
        switch value {
        case .string(let text):
            return .string(redactedTransportText(text))
        case .object(let object):
            return .object(object.mapValues { transportValue($0) })
        case .array(let array):
            return .array(array.map { transportValue($0) })
        case .number(_), .bool(_), .null:
            return value
        }
    }

    private func redactedTransportText(_ text: String) -> String {
        let replacements: [(pattern: String, template: String)] = [
            (#"(?i)authorization\s+bearer\s+[^\s,;)]+"#, "authorization [REDACTED]"),
            (#"(?i)bearer\s+[^\s,;)]+"#, "Bearer [REDACTED]"),
            (
                #"(?i)(authorization|cookie|connect-csrf-token|csrf|token|access[_-]?token|refresh[_-]?token|client[_-]?secret|api[_-]?key)\s*[:=]\s*[^,\s]+"#,
                "$1=[REDACTED]"
            ),
            (
                #"(?i)\b(authorization|cookie|connect-csrf-token|csrf|token|access[_-]?token|refresh[_-]?token|client[_-]?secret|api[_-]?key)\s+[^\s,;)]+"#,
                "$1 [REDACTED]"
            ),
            (#"(?i)file://[^\s,)]+"#, REDACTED_MOBILE_PATH),
            (#"\\\\[^\s,;)]+"#, REDACTED_MOBILE_PATH),
            (#"(?i)(?<![a-z0-9])[a-z]:\\[^\s,;)]+"#, REDACTED_MOBILE_PATH),
            (
                #"(?i)(^|[\s=(\[{'"])[a-z]:[\\/][^\s,;)]+"#,
                "$1\(REDACTED_MOBILE_PATH)"
            ),
            (
                #"(^|[\s=(\[{'"])//[^\s,;)]+"#,
                "$1\(REDACTED_MOBILE_PATH)"
            ),
            (
                #"(?i)(^|[\s=(\[{'"])([a-z_][a-z0-9_-]*):/(?!/)[^\s,;)]+"#,
                "$1$2:\(REDACTED_MOBILE_PATH)"
            ),
            (#"(^|[\s=(\[{'"])/(?!/)[^\s,;)]+"#, "$1\(REDACTED_MOBILE_PATH)"),
            (
                #"(?i)\b(password|secret|token|api[_-]?key|authorization|cookie|csrf)\s*[:=]\s*[^,\s;)]+"#,
                "$1=[REDACTED]"
            ),
            (
                #"(?i)\b(password|secret|token|api[_-]?key|authorization|cookie|csrf)\s+[^\s,;)]+"#,
                "$1 [REDACTED]"
            ),
        ]
        return replacements.reduce(text) { value, replacement in
            guard let expression = try? NSRegularExpression(pattern: replacement.pattern) else {
                return value
            }
            return expression.stringByReplacingMatches(
                in: value,
                range: NSRange(value.startIndex..<value.endIndex, in: value),
                withTemplate: replacement.template
            )
        }
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

    private func rewriteEventsUnlocked(_ events: [LiveRoundEvent]) throws {
        try repairTornEventLogEOFIfNeededUnlocked()
        _ = try loadEventsUnlocked(strict: true)
        try ensureEventLogDirectoryDurable()
        let lines = try events.map { event in
            String(data: try encoder.encode(transportEvent(event)), encoding: .utf8) ?? "{}"
        }
        .joined(separator: "\n")
        var data = Data(lines.utf8)
        if !events.isEmpty {
            data.append(Data([0x0A]))
        }
        try writeEventLogAtomicallyAndDurably(data)
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
