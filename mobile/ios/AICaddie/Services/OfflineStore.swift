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
    public var fairwayResult: String?
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
            && fairwayResult == other.fairwayResult
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

private struct LiveRoundProgress: Codable, Equatable {
    let roundId: String
    var activeHole: Int
    var scoreDraft: LiveScoreDraft?
}

private struct ReplayEventIdentity: Hashable {
    let roundId: String
    let clientId: String
    let eventId: String
}

private struct EventLogFileIdentity: Equatable {
    let device: UInt64
    let inode: UInt64
}

private enum EventLogEntryState: Equatable {
    case missing
    case regular(EventLogFileIdentity)
}

private final class EventLogDirectoryAuthority {
    let descriptors: [Int32]
    let identities: [EventLogFileIdentity]
    let componentNames: [String]
    let urls: [URL]

    var directoryDescriptor: Int32 {
        descriptors[descriptors.count - 1]
    }

    init(
        descriptors: [Int32],
        identities: [EventLogFileIdentity],
        componentNames: [String],
        urls: [URL]
    ) {
        self.descriptors = descriptors
        self.identities = identities
        self.componentNames = componentNames
        self.urls = urls
    }

    deinit {
        for descriptor in descriptors.reversed() {
            _ = close(descriptor)
        }
    }
}

private struct EventLogSnapshot {
    let data: Data
    let state: EventLogEntryState
}

private struct LoadedEventLog {
    let events: [LiveRoundEvent]
    let state: EventLogEntryState
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
    private let liveProgressURL: URL
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
            syncEventLogFile: { _ in },
            syncEventLogDirectory: { _ in }
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
        self.liveProgressURL = resolvedDirectory.appendingPathComponent("live_progress.json")
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
            syncEventLogFile: { _ in },
            syncEventLogDirectory: { _ in }
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

    /// An explicit live cursor/draft is the strongest in-progress signal. Older rounds without that
    /// file fall back to the most recent real hole event.
    public func inProgressRoundId() throws -> String? {
        if let progress = try? loadLiveRoundProgress() {
            return progress.roundId
        }
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

    /// True when play has explicit live progress (including an unfinished score draft) or at least
    /// one real hole event. Used by bootstrap to resume instead of treating the package as home data.
    public func hasRecordedEvents(roundId: String) throws -> Bool {
        if let progress = try? loadLiveRoundProgress(), progress.roundId == roundId {
            return true
        }
        return try loadEvents().contains { event in
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

    public func saveActiveHole(roundId: String, hole: Int) throws {
        let current = try loadLiveRoundProgress()
        let progress = LiveRoundProgress(
            roundId: roundId,
            activeHole: hole,
            scoreDraft: current?.roundId == roundId ? current?.scoreDraft : nil
        )
        try saveLiveRoundProgress(progress)
    }

    public func saveLiveScoreDraft(roundId: String, draft: LiveScoreDraft) throws {
        let current = try loadLiveRoundProgress()
        let activeHole = (current?.roundId == roundId) ? current?.activeHole ?? draft.hole : draft.hole
        let progress = LiveRoundProgress(
            roundId: roundId,
            activeHole: activeHole,
            scoreDraft: draft
        )
        try saveLiveRoundProgress(progress)
    }

    public func loadLiveScoreDraft(roundId: String) throws -> LiveScoreDraft? {
        guard let progress = try loadLiveRoundProgress(), progress.roundId == roundId else {
            return nil
        }
        return progress.scoreDraft
    }

    public func clearLiveScoreDraft(roundId: String) throws {
        guard var progress = try loadLiveRoundProgress(), progress.roundId == roundId else {
            return
        }
        progress.scoreDraft = nil
        try saveLiveRoundProgress(progress)
    }

    private func loadLiveRoundProgress() throws -> LiveRoundProgress? {
        guard FileManager.default.fileExists(atPath: liveProgressURL.path) else {
            return nil
        }
        return try decoder.decode(LiveRoundProgress.self, from: Data(contentsOf: liveProgressURL))
    }

    private func saveLiveRoundProgress(_ progress: LiveRoundProgress) throws {
        try FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        try encoder.encode(progress).write(to: liveProgressURL, options: [.atomic])
    }

    /// Forget a round entirely (discard/cancel): clear the active-package pointer + its
    /// cached package, and drop its events from the log so a discarded round never
    /// resurfaces on relaunch or syncs to the backend.
    public func discardRound(roundId: String) throws {
        try withEventLogLock {
            let authority = try openEventLogDirectoryAuthority(createIfMissing: false)
            if let authority {
                try repairTornEventLogEOFIfNeededUnlocked(authority: authority)
            }
            let loaded = try loadEventsUnlocked(strict: true, authority: authority)
            let remaining = loaded.events.filter { $0.roundId != roundId }
            if remaining.isEmpty {
                try removeEventLogUnlocked(
                    authority: authority,
                    expectedState: loaded.state
                )
            } else {
                guard let authority else {
                    throw OfflineStoreError.eventLogCorrupt
                }
                _ = try rewriteEventsUnlocked(
                    remaining,
                    authority: authority,
                    expectedState: loaded.state
                )
            }
        }
        try? FileManager.default.removeItem(at: currentPackageURL)
        try? FileManager.default.removeItem(at: packageURL(roundId: roundId))
        if let progress = try? loadLiveRoundProgress(), progress.roundId == roundId {
            try? FileManager.default.removeItem(at: liveProgressURL)
        }
        AICaddieLog.storage.debug("Discarded round \(roundId, privacy: .public)")
    }

    public func appendEvent(_ event: LiveRoundEvent) throws {
        try withEventLogLock {
            var authority = try openEventLogDirectoryAuthority(createIfMissing: false)
            if let authority {
                try repairTornEventLogEOFIfNeededUnlocked(authority: authority)
            }
            let loaded = try loadEventsUnlocked(strict: true, authority: authority)
            let writeAuthority = try requireEventLogDirectoryAuthority(&authority)
            _ = try appendEventUnlocked(
                event,
                authority: writeAuthority,
                expectedState: loaded.state
            )
        }
    }

    private func appendEventUnlocked(
        _ event: LiveRoundEvent,
        authority: EventLogDirectoryAuthority,
        expectedState: EventLogEntryState
    ) throws -> EventLogEntryState {
        try ensureEventLogDirectoryDurable(authority: authority)
        let transport = transportEvent(event)
        var encoded = try encoder.encode(transport)
        encoded.append(Data([0x0A]))
        let resultingState = try appendEventLogDataUnlocked(
            encoded,
            authority: authority,
            expectedState: expectedState
        )
        AICaddieLog.storage.debug("Saved live event \(String(describing: transport.kind), privacy: .public) hole \(transport.hole, privacy: .public)")
        return resultingState
    }

    public func containsEvent(eventId: String) throws -> Bool {
        try loadEvents().contains { event in
            event.eventId == eventId
        }
    }

    public func applyReplayEvents(_ replayEvents: [LiveRoundEvent]) throws -> Bool {
        try withEventLogLock {
            var authority = try openEventLogDirectoryAuthority(createIfMissing: false)
            if let authority {
                try repairTornEventLogEOFIfNeededUnlocked(authority: authority)
            }
            let transportReplayEvents = replayEvents.map { transportEvent($0) }
            let loaded = try loadEventsStrictlyForReplayUnlocked(authority: authority)
            var currentState = loaded.state
            var eventsByIdentity = try replayEventsByIdentity(loaded.events)
            if !transportReplayEvents.isEmpty,
               case .regular = currentState {
                guard let authority else {
                    throw OfflineStoreError.eventLogCorrupt
                }
                try establishFreshEventLogBarrierUnlocked(
                    authority: authority,
                    expectedState: currentState
                )
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
                let writeAuthority = try requireEventLogDirectoryAuthority(&authority)
                currentState = try appendEventUnlocked(
                    event,
                    authority: writeAuthority,
                    expectedState: currentState
                )
                eventsByIdentity[identity] = event
                appendedAny = true
            }

            let durableEvents = try loadEventsStrictlyForReplayUnlocked(
                authority: authority
            ).events
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
            let authority = try openEventLogDirectoryAuthority(createIfMissing: false)
            return try loadEventsUnlocked(
                strict: false,
                authority: authority
            ).events
        }
    }

    private func loadEventsStrictlyForReplayUnlocked(
        authority: EventLogDirectoryAuthority?
    ) throws -> LoadedEventLog {
        try loadEventsUnlocked(strict: true, authority: authority)
    }

    private func loadEventsUnlocked(
        strict: Bool,
        authority: EventLogDirectoryAuthority?
    ) throws -> LoadedEventLog {
        let snapshot: EventLogSnapshot
        if let authority {
            snapshot = try readEventLogSnapshotUnlocked(authority: authority)
        } else {
            snapshot = EventLogSnapshot(data: Data(), state: .missing)
        }
        let data = snapshot.data
        guard !data.isEmpty else {
            return LoadedEventLog(events: [], state: snapshot.state)
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
        return LoadedEventLog(events: events, state: snapshot.state)
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
                if let fairway = stringPayload("fairway", in: event.payload) {
                    state.fairwayResult = fairway
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

        if let progress = try? loadLiveRoundProgress(),
           progress.roundId == roundId,
           package.holes.contains(where: { $0.number == progress.activeHole }) {
            activeHole = progress.activeHole
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

    private static func posixError(_ code: Int32) -> NSError {
        NSError(domain: NSPOSIXErrorDomain, code: Int(code))
    }

    private func validatedIdentity(
        of descriptor: Int32,
        requiredType: mode_t
    ) throws -> EventLogFileIdentity {
        var metadata = stat()
        guard fstat(descriptor, &metadata) == 0,
              (metadata.st_mode & mode_t(S_IFMT)) == requiredType
        else {
            throw OfflineStoreError.eventLogCorrupt
        }
        return EventLogFileIdentity(
            device: UInt64(metadata.st_dev),
            inode: UInt64(metadata.st_ino)
        )
    }

    private func eventLogDirectoryComponents() throws -> [String] {
        guard trustedDirectoryAnchor.isFileURL, directoryURL.isFileURL else {
            throw OfflineStoreError.eventLogCorrupt
        }
        let anchorComponents = trustedDirectoryAnchor.standardizedFileURL.pathComponents
        let directoryComponents = directoryURL.standardizedFileURL.pathComponents
        guard directoryComponents.count >= anchorComponents.count,
              Array(directoryComponents.prefix(anchorComponents.count)) == anchorComponents
        else {
            throw OfflineStoreError.eventLogCorrupt
        }
        let relativeComponents = Array(
            directoryComponents.dropFirst(anchorComponents.count)
        )
        guard relativeComponents.allSatisfy({ component in
            !component.isEmpty
                && component != "/"
                && component != "."
                && component != ".."
                && !component.contains("/")
        }) else {
            throw OfflineStoreError.eventLogCorrupt
        }
        return relativeComponents
    }

    private func openEventLogDirectoryAuthority(
        createIfMissing: Bool
    ) throws -> EventLogDirectoryAuthority? {
        let componentNames = try eventLogDirectoryComponents()
        let directoryFlags = O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
        let anchorDescriptor = trustedDirectoryAnchor.withUnsafeFileSystemRepresentation {
            path -> Int32 in
            guard let path else { return -1 }
            return open(path, directoryFlags)
        }
        guard anchorDescriptor >= 0 else {
            throw OfflineStoreError.eventLogCorrupt
        }

        var descriptors = [anchorDescriptor]
        var transferredDescriptors = false
        defer {
            if !transferredDescriptors {
                for descriptor in descriptors.reversed() {
                    _ = close(descriptor)
                }
            }
        }
        var identities = [
            try validatedIdentity(
                of: anchorDescriptor,
                requiredType: mode_t(S_IFDIR)
            ),
        ]
        var urls = [trustedDirectoryAnchor]
        var currentURL = trustedDirectoryAnchor

        for component in componentNames {
            let parentDescriptor = descriptors[descriptors.count - 1]
            var descriptor = component.withCString { path in
                openat(parentDescriptor, path, directoryFlags)
            }
            let initialOpenError = errno
            if descriptor < 0, initialOpenError == ENOENT {
                guard createIfMissing else {
                    return nil
                }
                let result = component.withCString { path in
                    mkdirat(parentDescriptor, path, mode_t(0o700))
                }
                let creationError = errno
                guard result == 0 || creationError == EEXIST else {
                    throw OfflineStoreError.eventLogCorrupt
                }
                descriptor = component.withCString { path in
                    openat(parentDescriptor, path, directoryFlags)
                }
            }
            guard descriptor >= 0 else {
                throw OfflineStoreError.eventLogCorrupt
            }
            do {
                identities.append(
                    try validatedIdentity(
                        of: descriptor,
                        requiredType: mode_t(S_IFDIR)
                    )
                )
            } catch {
                _ = close(descriptor)
                throw error
            }
            descriptors.append(descriptor)
            currentURL.appendPathComponent(component, isDirectory: true)
            urls.append(currentURL)
        }

        let authority = EventLogDirectoryAuthority(
            descriptors: descriptors,
            identities: identities,
            componentNames: componentNames,
            urls: urls
        )
        transferredDescriptors = true
        return authority
    }

    private func requireEventLogDirectoryAuthority(
        _ authority: inout EventLogDirectoryAuthority?
    ) throws -> EventLogDirectoryAuthority {
        if let authority {
            return authority
        }
        guard let created = try openEventLogDirectoryAuthority(createIfMissing: true) else {
            throw OfflineStoreError.eventLogCorrupt
        }
        authority = created
        return created
    }

    private func revalidateEventLogDirectoryAuthority(
        _ authority: EventLogDirectoryAuthority
    ) throws {
        guard authority.descriptors.count == authority.identities.count,
              authority.descriptors.count == authority.componentNames.count + 1,
              authority.urls.count == authority.descriptors.count
        else {
            throw OfflineStoreError.eventLogCorrupt
        }

        for index in authority.descriptors.indices {
            guard try validatedIdentity(
                of: authority.descriptors[index],
                requiredType: mode_t(S_IFDIR)
            ) == authority.identities[index] else {
                throw OfflineStoreError.eventLogCorrupt
            }
        }

        let directoryFlags = O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
        let reopenedAnchor = trustedDirectoryAnchor.withUnsafeFileSystemRepresentation {
            path -> Int32 in
            guard let path else { return -1 }
            return open(path, directoryFlags)
        }
        guard reopenedAnchor >= 0 else {
            throw OfflineStoreError.eventLogCorrupt
        }
        let anchorIdentity: EventLogFileIdentity
        do {
            anchorIdentity = try validatedIdentity(
                of: reopenedAnchor,
                requiredType: mode_t(S_IFDIR)
            )
        } catch {
            _ = close(reopenedAnchor)
            throw error
        }
        _ = close(reopenedAnchor)
        guard anchorIdentity == authority.identities[0] else {
            throw OfflineStoreError.eventLogCorrupt
        }

        for index in authority.componentNames.indices {
            let descriptor = authority.componentNames[index].withCString { path in
                openat(authority.descriptors[index], path, directoryFlags)
            }
            guard descriptor >= 0 else {
                throw OfflineStoreError.eventLogCorrupt
            }
            let identity: EventLogFileIdentity
            do {
                identity = try validatedIdentity(
                    of: descriptor,
                    requiredType: mode_t(S_IFDIR)
                )
            } catch {
                _ = close(descriptor)
                throw error
            }
            _ = close(descriptor)
            guard identity == authority.identities[index + 1] else {
                throw OfflineStoreError.eventLogCorrupt
            }
        }
    }

    private func openEventLogDescriptor(
        authority: EventLogDirectoryAuthority,
        accessFlags: Int32,
        allowMissing: Bool
    ) throws -> (descriptor: Int32, identity: EventLogFileIdentity)? {
        let flags = accessFlags | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK
        let descriptor = "events.jsonl".withCString { path in
            openat(authority.directoryDescriptor, path, flags)
        }
        if descriptor < 0 {
            let openError = errno
            if allowMissing, openError == ENOENT {
                return nil
            }
            throw OfflineStoreError.eventLogCorrupt
        }
        do {
            let identity = try validatedIdentity(
                of: descriptor,
                requiredType: mode_t(S_IFREG)
            )
            return (descriptor, identity)
        } catch {
            _ = close(descriptor)
            throw error
        }
    }

    private func eventLogEntryState(
        authority: EventLogDirectoryAuthority
    ) throws -> EventLogEntryState {
        guard let opened = try openEventLogDescriptor(
            authority: authority,
            accessFlags: O_RDONLY,
            allowMissing: true
        ) else {
            return .missing
        }
        _ = close(opened.descriptor)
        return .regular(opened.identity)
    }

    private func requireEventLogState(
        _ expectedState: EventLogEntryState,
        authority: EventLogDirectoryAuthority
    ) throws {
        guard try eventLogEntryState(authority: authority) == expectedState else {
            throw OfflineStoreError.eventLogCorrupt
        }
        try revalidateEventLogDirectoryAuthority(authority)
    }

    private func readAll(from descriptor: Int32) throws -> Data {
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 64 * 1024)
        while true {
            let count = buffer.withUnsafeMutableBytes { rawBuffer -> Int in
                guard let baseAddress = rawBuffer.baseAddress else { return 0 }
                return read(descriptor, baseAddress, rawBuffer.count)
            }
            if count > 0 {
                data.append(contentsOf: buffer.prefix(count))
                continue
            }
            if count == 0 {
                return data
            }
            let readError = errno
            if readError == EINTR {
                continue
            }
            throw Self.posixError(readError)
        }
    }

    private func writeAll(_ data: Data, to descriptor: Int32) throws {
        try data.withUnsafeBytes { (rawBuffer: UnsafeRawBufferPointer) throws -> Void in
            guard let baseAddress = rawBuffer.baseAddress else { return }
            var offset = 0
            while offset < rawBuffer.count {
                let count = write(
                    descriptor,
                    baseAddress.advanced(by: offset),
                    rawBuffer.count - offset
                )
                if count > 0 {
                    offset += count
                    continue
                }
                let writeError = errno
                if count < 0, writeError == EINTR {
                    continue
                }
                throw Self.posixError(writeError)
            }
        }
    }

    private func synchronizeDescriptor(_ descriptor: Int32) throws {
        while fsync(descriptor) != 0 {
            let syncError = errno
            if syncError == EINTR {
                continue
            }
            throw Self.posixError(syncError)
        }
    }

    private func ensureEventLogDirectoryDurable(
        authority: EventLogDirectoryAuthority
    ) throws {
        try revalidateEventLogDirectoryAuthority(authority)
        for index in authority.componentNames.indices {
            try synchronizeDescriptor(authority.descriptors[index])
            try syncEventLogDirectory(authority.urls[index])
            try revalidateEventLogDirectoryAuthority(authority)
        }
    }

    private func readEventLogSnapshotUnlocked(
        authority: EventLogDirectoryAuthority
    ) throws -> EventLogSnapshot {
        try revalidateEventLogDirectoryAuthority(authority)
        guard let opened = try openEventLogDescriptor(
            authority: authority,
            accessFlags: O_RDONLY,
            allowMissing: true
        ) else {
            try requireEventLogState(.missing, authority: authority)
            return EventLogSnapshot(data: Data(), state: .missing)
        }
        defer { _ = close(opened.descriptor) }
        let data = try readAll(from: opened.descriptor)
        guard try validatedIdentity(
            of: opened.descriptor,
            requiredType: mode_t(S_IFREG)
        ) == opened.identity,
              try eventLogEntryState(authority: authority) == .regular(opened.identity)
        else {
            throw OfflineStoreError.eventLogCorrupt
        }
        try revalidateEventLogDirectoryAuthority(authority)
        return EventLogSnapshot(data: data, state: .regular(opened.identity))
    }

    private func establishEventLogFileAndDirectoryBarrier(
        descriptor: Int32,
        identity: EventLogFileIdentity,
        authority: EventLogDirectoryAuthority
    ) throws {
        guard try validatedIdentity(
            of: descriptor,
            requiredType: mode_t(S_IFREG)
        ) == identity else {
            throw OfflineStoreError.eventLogCorrupt
        }
        try synchronizeDescriptor(descriptor)
        try syncEventLogFile(logURL)
        try requireEventLogState(.regular(identity), authority: authority)
        try synchronizeDescriptor(authority.directoryDescriptor)
        try syncEventLogDirectory(directoryURL)
        try requireEventLogState(.regular(identity), authority: authority)
    }

    private func establishFreshEventLogBarrierUnlocked(
        authority: EventLogDirectoryAuthority,
        expectedState: EventLogEntryState
    ) throws {
        try requireEventLogState(expectedState, authority: authority)
        try ensureEventLogDirectoryDurable(authority: authority)
        guard let opened = try openEventLogDescriptor(
            authority: authority,
            accessFlags: O_WRONLY,
            allowMissing: true
        ) else {
            throw OfflineStoreError.replayDurabilityVerificationFailed
        }
        defer { _ = close(opened.descriptor) }
        guard expectedState == .regular(opened.identity) else {
            throw OfflineStoreError.eventLogCorrupt
        }
        try establishEventLogFileAndDirectoryBarrier(
            descriptor: opened.descriptor,
            identity: opened.identity,
            authority: authority
        )
    }

    private func appendEventLogDataUnlocked(
        _ data: Data,
        authority: EventLogDirectoryAuthority,
        expectedState: EventLogEntryState
    ) throws -> EventLogEntryState {
        switch expectedState {
        case .missing:
            return try replaceEventLogDataAtomicallyUnlocked(
                data,
                authority: authority,
                expectedState: expectedState
            )
        case .regular(let expectedIdentity):
            try requireEventLogState(expectedState, authority: authority)
            guard let opened = try openEventLogDescriptor(
                authority: authority,
                accessFlags: O_WRONLY | O_APPEND,
                allowMissing: true
            ), opened.identity == expectedIdentity else {
                throw OfflineStoreError.eventLogCorrupt
            }
            defer { _ = close(opened.descriptor) }
            try writeAll(data, to: opened.descriptor)
            try establishEventLogFileAndDirectoryBarrier(
                descriptor: opened.descriptor,
                identity: opened.identity,
                authority: authority
            )
            return .regular(opened.identity)
        }
    }

    private func createEventLogTemporaryFile(
        authority: EventLogDirectoryAuthority
    ) throws -> (name: String, descriptor: Int32, identity: EventLogFileIdentity) {
        let flags = O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC
        for _ in 0..<8 {
            let name = ".events.jsonl.\(UUID().uuidString).tmp"
            let descriptor = name.withCString { path in
                openat(authority.directoryDescriptor, path, flags, mode_t(0o600))
            }
            if descriptor >= 0 {
                do {
                    let identity = try validatedIdentity(
                        of: descriptor,
                        requiredType: mode_t(S_IFREG)
                    )
                    return (name, descriptor, identity)
                } catch {
                    _ = close(descriptor)
                    _ = name.withCString { path in
                        unlinkat(authority.directoryDescriptor, path, 0)
                    }
                    throw error
                }
            }
            let creationError = errno
            if creationError == EEXIST {
                continue
            }
            throw Self.posixError(creationError)
        }
        throw OfflineStoreError.eventLogCorrupt
    }

    private func replaceEventLogDataAtomicallyUnlocked(
        _ data: Data,
        authority: EventLogDirectoryAuthority,
        expectedState: EventLogEntryState
    ) throws -> EventLogEntryState {
        try requireEventLogState(expectedState, authority: authority)
        let temporary = try createEventLogTemporaryFile(authority: authority)
        var renamed = false
        defer {
            _ = close(temporary.descriptor)
            if !renamed {
                _ = temporary.name.withCString { path in
                    unlinkat(authority.directoryDescriptor, path, 0)
                }
            }
        }

        try writeAll(data, to: temporary.descriptor)
        try synchronizeDescriptor(temporary.descriptor)
        guard try validatedIdentity(
            of: temporary.descriptor,
            requiredType: mode_t(S_IFREG)
        ) == temporary.identity else {
            throw OfflineStoreError.eventLogCorrupt
        }
        try requireEventLogState(expectedState, authority: authority)

        let renameResult = temporary.name.withCString { temporaryPath in
            "events.jsonl".withCString { eventLogPath in
                renameat(
                    authority.directoryDescriptor,
                    temporaryPath,
                    authority.directoryDescriptor,
                    eventLogPath
                )
            }
        }
        guard renameResult == 0 else {
            throw Self.posixError(errno)
        }
        renamed = true

        guard let opened = try openEventLogDescriptor(
            authority: authority,
            accessFlags: O_WRONLY,
            allowMissing: false
        ), opened.identity == temporary.identity else {
            throw OfflineStoreError.eventLogCorrupt
        }
        defer { _ = close(opened.descriptor) }
        try establishEventLogFileAndDirectoryBarrier(
            descriptor: opened.descriptor,
            identity: opened.identity,
            authority: authority
        )
        return .regular(opened.identity)
    }

    private func removeEventLogUnlocked(
        authority: EventLogDirectoryAuthority?,
        expectedState: EventLogEntryState
    ) throws {
        guard let authority else {
            guard expectedState == .missing else {
                throw OfflineStoreError.eventLogCorrupt
            }
            return
        }
        try requireEventLogState(expectedState, authority: authority)
        guard case .regular = expectedState else {
            return
        }
        let result = "events.jsonl".withCString { path in
            unlinkat(authority.directoryDescriptor, path, 0)
        }
        guard result == 0 else {
            throw Self.posixError(errno)
        }
        try requireEventLogState(.missing, authority: authority)
    }

    private func repairTornEventLogEOFIfNeededUnlocked(
        authority: EventLogDirectoryAuthority
    ) throws {
        let snapshot = try readEventLogSnapshotUnlocked(authority: authority)
        let data = snapshot.data
        guard !data.isEmpty, data.last != 0x0A else {
            return
        }
        let lastNewline = data.lastIndex(of: 0x0A)
        let tailStart = lastNewline.map { data.index(after: $0) } ?? data.startIndex
        let tail = Data(data[tailStart..<data.endIndex])
        let replacement: Data
        switch JSONPrefixScanner.classify(tail) {
        case .complete:
            guard (try? decoder.decode(LiveRoundEvent.self, from: tail)) != nil else {
                throw OfflineStoreError.eventLogCorrupt
            }
            var terminated = data
            terminated.append(Data([0x0A]))
            replacement = terminated
        case .incomplete:
            replacement = lastNewline.map { Data(data[...$0]) } ?? Data()
        case .invalid:
            throw OfflineStoreError.eventLogCorrupt
        }
        try ensureEventLogDirectoryDurable(authority: authority)
        _ = try replaceEventLogDataAtomicallyUnlocked(
            replacement,
            authority: authority,
            expectedState: snapshot.state
        )
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

    private func rewriteEventsUnlocked(
        _ events: [LiveRoundEvent],
        authority: EventLogDirectoryAuthority,
        expectedState: EventLogEntryState
    ) throws -> EventLogEntryState {
        try ensureEventLogDirectoryDurable(authority: authority)
        let lines = try events.map { event in
            String(data: try encoder.encode(transportEvent(event)), encoding: .utf8) ?? "{}"
        }
        .joined(separator: "\n")
        var data = Data(lines.utf8)
        if !events.isEmpty {
            data.append(Data([0x0A]))
        }
        return try replaceEventLogDataAtomicallyUnlocked(
            data,
            authority: authority,
            expectedState: expectedState
        )
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
            fairwayResult: nil,
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
