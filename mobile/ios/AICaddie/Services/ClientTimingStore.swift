import Foundation

/// The privacy-safe record persisted for one client request. It contains only transport facts;
/// server timing is useful locally but is intentionally omitted from the upload schema.
struct ClientTimingRecord: Codable, Equatable, Sendable {
    let requestId: String
    let path: String
    let clientTotalMs: Double
    let status: Int?
    let error: String?
    let startedAt: String
    let networkType: String?
    let serverTotalMs: Double?

    enum CodingKeys: String, CodingKey {
        case requestId = "request_id"
        case path
        case clientTotalMs = "client_total_ms"
        case status
        case error
        case startedAt = "started_at"
        case networkType = "network_type"
        case serverTotalMs = "server_total_ms"
    }

    var uploadValue: ClientTimingUploadRecord {
        ClientTimingUploadRecord(
            requestId: requestId,
            path: path,
            clientTotalMs: clientTotalMs,
            status: status,
            error: error,
            startedAt: startedAt,
            networkType: networkType
        )
    }
}

struct ClientTimingUploadRecord: Codable, Sendable {
    let requestId: String
    let path: String
    let clientTotalMs: Double
    let status: Int?
    let error: String?
    let startedAt: String
    let networkType: String?

    enum CodingKeys: String, CodingKey {
        case requestId = "request_id"
        case path
        case clientTotalMs = "client_total_ms"
        case status
        case error
        case startedAt = "started_at"
        case networkType = "network_type"
    }
}

enum ClientTimingUploadOutcome: Equatable {
    case sent
    case dropped
    case unavailable
}

typealias ClientTimingUploadHandler = ([ClientTimingUploadRecord]) async -> ClientTimingUploadOutcome

/// Process-wide timing ring and upload scheduler. The shared instance loads its existing ring on a
/// utility queue; request construction never waits for App Support I/O. A lock protects both the
/// ring and the pending upload queue, while a separate file lock serializes atomic replacements.
final class ClientTimingStore: @unchecked Sendable {
    static let maxRecords = 200
    static let maxUploadBatch = 50
    static let uploadThreshold = 10
    static let uploadInterval: TimeInterval = 60

    #if DEBUG
    private static let sharedUploadsEnabled = false
    #else
    private static let sharedUploadsEnabled = true
    #endif

    private static let fileLock = NSLock()
    private static let foregroundLock = NSLock()
    private static var foregroundStartCount = 0

    static let shared: ClientTimingStore = {
        ClientTimingStore(
            fileURL: ClientTimingStore.defaultFileURL(),
            persists: true,
            loadAsync: true,
            now: { ProcessInfo.processInfo.systemUptime },
            uploadsEnabled: sharedUploadsEnabled
        )
    }()

    private let lock = NSLock()
    private let fileURL: URL?
    private let persists: Bool
    /// The process-wide store writes snapshots off the request path. Explicit injected stores keep
    /// synchronous writes for deterministic focused tests and callers that need an immediate file.
    private let persistenceQueue: DispatchQueue?
    private let now: () -> TimeInterval
    private let uploadsEnabled: Bool
    private let encoder = JSONEncoder()
    private var records: [ClientTimingRecord]
    private var loaded: Bool
    private var pending: [ClientTimingRecord] = []
    private var pendingAges: [TimeInterval] = []
    private var uploadInFlight = false
    private var uploadHandler: ClientTimingUploadHandler?

    /// Explicit stores are synchronous and are intended for timing tests or an injected owner.
    /// The production app uses ``shared``, whose file read is asynchronous.
    init(
        fileURL: URL? = nil,
        now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
        uploadsEnabled: Bool = true
    ) {
        self.fileURL = fileURL
        self.persists = fileURL != nil
        self.persistenceQueue = nil
        self.now = now
        self.uploadsEnabled = uploadsEnabled
        self.records = fileURL.map(Self.readRecords) ?? []
        self.loaded = true
    }

    private init(
        fileURL: URL?,
        persists: Bool,
        loadAsync: Bool,
        now: @escaping () -> TimeInterval,
        uploadsEnabled: Bool
    ) {
        self.fileURL = fileURL
        self.persists = persists
        self.persistenceQueue = persists
            ? DispatchQueue(label: "ai.caddie.client-timing-persistence", qos: .utility)
            : nil
        self.now = now
        self.uploadsEnabled = uploadsEnabled
        self.records = []
        self.loaded = !loadAsync
        if loadAsync, let fileURL {
            DispatchQueue.global(qos: .utility).async { [weak self] in
                let loaded = Self.readRecords(fileURL)
                guard let self else { return }
                self.lock.lock()
                self.records = Array(Self.deduplicate(loaded + self.records).suffix(Self.maxRecords))
                self.loaded = true
                let snapshot = self.persists ? self.records : nil
                // Enqueue while holding the state lock so a concurrent record cannot enqueue a
                // newer snapshot before this load snapshot and then have it overwritten by load.
                if let snapshot, self.persistenceQueue != nil {
                    self.enqueuePersistence(snapshot)
                }
                self.lock.unlock()
                if let snapshot, self.persistenceQueue == nil {
                    self.enqueuePersistence(snapshot)
                }
            }
        } else if let fileURL {
            self.records = Self.readRecords(fileURL)
        }
    }

    /// The internal SyncClient test initializer uses this store so ordinary tests cannot write
    /// App Support or emit a diagnostic POST. Timing tests explicitly inject an upload-enabled one.
    static func testingStore() -> ClientTimingStore {
        ClientTimingStore(fileURL: nil, now: { 0 }, uploadsEnabled: false)
    }

    static func foregroundStartDidBegin() {
        foregroundLock.lock()
        foregroundStartCount += 1
        foregroundLock.unlock()
    }

    func foregroundStartDidEnd() {
        Self.foregroundLock.lock()
        if Self.foregroundStartCount > 0 {
            Self.foregroundStartCount -= 1
        }
        let running = Self.foregroundStartCount > 0
        Self.foregroundLock.unlock()
        if !running {
            startUploadIfDue(now: now())
        }
    }

    func configureUploader(_ handler: ClientTimingUploadHandler?) {
        lock.lock()
        uploadHandler = handler
        lock.unlock()
        startUploadIfDue(now: now())
    }

    func record(_ value: ClientTimingRecord, now timestamp: TimeInterval? = nil) {
        let timestamp = timestamp ?? now()
        lock.lock()
        records.append(value)
        if records.count > Self.maxRecords {
            records.removeFirst(records.count - Self.maxRecords)
        }
        pending.append(value)
        pendingAges.append(timestamp)
        if pending.count > Self.maxRecords {
            let excess = pending.count - Self.maxRecords
            pending.removeFirst(excess)
            pendingAges.removeFirst(excess)
        }
        let snapshot = persists && loaded ? records : nil
        if let snapshot, persistenceQueue != nil {
            // Queue submission is inside the lock to preserve snapshot order relative to the
            // asynchronous load above; the file write itself remains off this request path.
            enqueuePersistence(snapshot)
        }
        lock.unlock()
        if let snapshot, persistenceQueue == nil {
            enqueuePersistence(snapshot)
        }
        startUploadIfDue(now: timestamp)
    }

    func snapshot() -> [ClientTimingRecord] {
        lock.lock()
        defer { lock.unlock() }
        return records
    }

    /// Compatibility seam for the focused store tests. Production scheduling uses the uploader
    /// configured above, so a failed network call is discarded and never requeued.
    func takeBatchIfDue(
        now timestamp: TimeInterval,
        foregroundStartRunning: Bool,
        threshold: Int = ClientTimingStore.uploadThreshold,
        interval: TimeInterval = ClientTimingStore.uploadInterval
    ) -> [ClientTimingRecord]? {
        lock.lock()
        defer { lock.unlock() }
        guard !foregroundStartRunning, !uploadInFlight, !pending.isEmpty else { return nil }
        guard isDueLocked(now: timestamp, threshold: threshold, interval: interval) else { return nil }
        uploadInFlight = true
        return reserveBatchLocked().records
    }

    func finishUpload() {
        lock.lock()
        uploadInFlight = false
        lock.unlock()
    }

    private func startUploadIfDue(now timestamp: TimeInterval) {
        guard uploadsEnabled, !Self.foregroundStartIsRunning() else { return }
        lock.lock()
        guard !uploadInFlight,
              let handler = uploadHandler,
              isDueLocked(now: timestamp, threshold: Self.uploadThreshold, interval: Self.uploadInterval) else {
            lock.unlock()
            return
        }
        let reserved = reserveBatchLocked()
        uploadInFlight = true
        lock.unlock()

        let store = self
        let upload = reserved.records.map(\.uploadValue)
        Task {
            let outcome = await handler(upload)
            store.finishUpload(outcome: outcome, records: reserved.records, ages: reserved.ages)
        }
    }

    private func finishUpload(
        outcome: ClientTimingUploadOutcome,
        records: [ClientTimingRecord],
        ages: [TimeInterval]
    ) {
        lock.lock()
        if outcome == .unavailable {
            pending = records + pending
            pendingAges = ages + pendingAges
        }
        uploadInFlight = false
        lock.unlock()
    }

    private func isDueLocked(now timestamp: TimeInterval, threshold: Int, interval: TimeInterval) -> Bool {
        guard let first = pendingAges.first else { return false }
        return pending.count >= threshold || timestamp - first >= interval
    }

    private func reserveBatchLocked() -> (records: [ClientTimingRecord], ages: [TimeInterval]) {
        let count = min(Self.maxUploadBatch, pending.count)
        let records = Array(pending.prefix(count))
        let ages = Array(pendingAges.prefix(count))
        pending.removeFirst(count)
        pendingAges.removeFirst(count)
        return (records, ages)
    }

    private static func foregroundStartIsRunning() -> Bool {
        foregroundLock.lock()
        defer { foregroundLock.unlock() }
        return foregroundStartCount > 0
    }

    private func enqueuePersistence(_ snapshot: [ClientTimingRecord]) {
        guard let persistenceQueue else {
            persist(snapshot)
            return
        }
        persistenceQueue.async { [weak self] in
            self?.persist(snapshot)
        }
    }

    private func persist(_ snapshot: [ClientTimingRecord]) {
        guard let fileURL else { return }
        Self.fileLock.lock()
        defer { Self.fileLock.unlock() }
        do {
            try FileManager.default.createDirectory(
                at: fileURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            let lines = try snapshot.map { try encoder.encode($0) }
                .map { String(decoding: $0, as: UTF8.self) }
                .joined(separator: "\n")
            try (lines + (lines.isEmpty ? "" : "\n")).write(to: fileURL, atomically: true, encoding: .utf8)
        } catch {
            AICaddieLog.storage.error("Client timing log write skipped: \(String(describing: error), privacy: .public)")
        }
    }

    private static func defaultFileURL() -> URL? {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first?
            .appendingPathComponent("client-network-timing.jsonl", isDirectory: false)
    }

    private static func readRecords(_ fileURL: URL) -> [ClientTimingRecord] {
        fileLock.lock()
        defer { fileLock.unlock() }
        guard let data = try? Data(contentsOf: fileURL),
              let text = String(data: data, encoding: .utf8) else { return [] }
        let decoder = JSONDecoder()
        let decoded = text.split(whereSeparator: { $0.isNewline }).compactMap { line in
            try? decoder.decode(ClientTimingRecord.self, from: Data(line.utf8))
        }
        return Array(decoded.suffix(maxRecords))
    }

    private static func deduplicate(_ values: [ClientTimingRecord]) -> [ClientTimingRecord] {
        var seen = Set<String>()
        var result: [ClientTimingRecord] = []
        for value in values.reversed() where seen.insert(value.requestId).inserted {
            result.append(value)
        }
        return Array(result.reversed())
    }
}
