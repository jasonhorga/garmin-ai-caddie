import Foundation

/// The privacy-safe record persisted for one client request. It contains only transport facts;
/// server timing is useful locally but is intentionally omitted from the upload schema.
struct ClientTimingRecord: Codable, Equatable {
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

struct ClientTimingUploadRecord: Codable {
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

/// A locked, bounded JSONL ring plus an in-memory pending queue for the next client-timing batch.
/// Failed uploads are deliberately discarded by ``takeBatchIfDue`` as required by C90.
final class ClientTimingStore: @unchecked Sendable {
    static let maxRecords = 200
    static let maxUploadBatch = 50
    static let uploadThreshold = 10
    static let uploadInterval: TimeInterval = 60
    private static let fileLock = NSLock()

    private let lock = NSLock()
    private let fileURL: URL?
    private let encoder = JSONEncoder()
    private var records: [ClientTimingRecord]
    private var pending: [ClientTimingRecord] = []
    private var lastUploadAt: TimeInterval?
    private var uploadInFlight = false

    init(fileURL: URL? = nil) {
        self.fileURL = fileURL ?? Self.defaultFileURL()
        self.records = []
        if let fileURL = self.fileURL {
            self.records = Self.readRecords(fileURL: fileURL)
        }
    }

    static func prepareAtLaunch() {
        guard let fileURL = defaultFileURL() else { return }
        try? FileManager.default.createDirectory(
            at: fileURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
    }

    func record(_ value: ClientTimingRecord) {
        lock.lock()
        defer { lock.unlock() }
        records.append(value)
        if records.count > Self.maxRecords {
            records.removeFirst(records.count - Self.maxRecords)
        }
        pending.append(value)
        if pending.count > Self.maxRecords {
            pending.removeFirst(pending.count - Self.maxRecords)
        }
        persistLocked()
    }

    func snapshot() -> [ClientTimingRecord] {
        lock.lock()
        defer { lock.unlock() }
        return records
    }

    func takeBatchIfDue(
        now: TimeInterval,
        foregroundStartRunning: Bool,
        threshold: Int = ClientTimingStore.uploadThreshold,
        interval: TimeInterval = ClientTimingStore.uploadInterval
    ) -> [ClientTimingRecord]? {
        lock.lock()
        defer { lock.unlock() }
        guard !foregroundStartRunning, !uploadInFlight, !pending.isEmpty else { return nil }
        // With no previous upload, allow a small pending batch to age for the same interval
        // before the next request triggers a best-effort flush.
        let intervalDue = lastUploadAt.map { now - $0 >= interval } ?? now >= interval
        guard pending.count >= threshold || intervalDue else { return nil }
        uploadInFlight = true
        lastUploadAt = now
        let count = min(Self.maxUploadBatch, pending.count)
        let batch = Array(pending.prefix(count))
        pending.removeFirst(count)
        return batch
    }

    func finishUpload() {
        lock.lock()
        uploadInFlight = false
        lock.unlock()
    }

    private func persistLocked() {
        guard let fileURL else { return }
        Self.fileLock.lock()
        defer { Self.fileLock.unlock() }
        do {
            try FileManager.default.createDirectory(
                at: fileURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            let lines = try records.map { try encoder.encode($0) }
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

    private static func readRecords(fileURL: URL) -> [ClientTimingRecord] {
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
}
