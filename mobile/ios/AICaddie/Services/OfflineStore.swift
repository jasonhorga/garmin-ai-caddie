import Foundation

public final class OfflineStore {
    private let directoryURL: URL
    private let logURL: URL
    private let packagesDirectoryURL: URL
    private let currentPackageURL: URL
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    public init(directoryURL: URL) {
        self.directoryURL = directoryURL
        self.logURL = directoryURL.appendingPathComponent("events.jsonl")
        self.packagesDirectoryURL = directoryURL.appendingPathComponent("packages", isDirectory: true)
        self.currentPackageURL = directoryURL.appendingPathComponent("current_package.json")
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

    private func packageURL(roundId: String) -> URL {
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        let fileName = roundId.addingPercentEncoding(withAllowedCharacters: allowed) ?? roundId.replacingOccurrences(of: "/", with: "_")
        return packagesDirectoryURL.appendingPathComponent("\(fileName).json")
    }
}
