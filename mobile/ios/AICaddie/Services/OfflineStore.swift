import Foundation

public final class OfflineStore {
    private let directoryURL: URL
    private let logURL: URL
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    public init(directoryURL: URL) {
        self.directoryURL = directoryURL
        self.logURL = directoryURL.appendingPathComponent("events.jsonl")
        self.encoder = JSONEncoder()
        self.decoder = JSONDecoder()
    }

    public convenience init() {
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("AICaddie", isDirectory: true)
        self.init(directoryURL: directory)
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
    }

    public func loadEvents() throws -> [LiveRoundEvent] {
        guard FileManager.default.fileExists(atPath: logURL.path) else {
            return []
        }
        let data = try Data(contentsOf: logURL)
        guard let text = String(data: data, encoding: .utf8) else {
            return []
        }
        return try text
            .split(separator: "\n")
            .map { line in
                try decoder.decode(LiveRoundEvent.self, from: Data(line.utf8))
            }
    }

    public func appendSyncMarker(roundId: String, timestamp: String) throws {
        let event = LiveRoundEvent(
            eventId: UUID().uuidString,
            roundId: roundId,
            timestamp: timestamp,
            hole: 0,
            kind: .syncMarker,
            payload: ["status": .string("synced")]
        )
        try appendEvent(event)
    }
}
