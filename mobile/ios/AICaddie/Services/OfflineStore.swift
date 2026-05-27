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

public final class OfflineStore {
    private let directoryURL: URL
    private let logURL: URL
    private let packagesDirectoryURL: URL
    private let currentPackageURL: URL
    private let pendingMediaDirectoryURL: URL
    private let pendingMediaIndexURL: URL
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    public init(directoryURL: URL) {
        self.directoryURL = directoryURL
        self.logURL = directoryURL.appendingPathComponent("events.jsonl")
        self.packagesDirectoryURL = directoryURL.appendingPathComponent("packages", isDirectory: true)
        self.currentPackageURL = directoryURL.appendingPathComponent("current_package.json")
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
        return try text
            .split(separator: "\n")
            .map { line in
                try decoder.decode(PendingMediaAttachment.self, from: Data(line.utf8))
            }
            .filter { media in
                roundId == nil || media.roundId == roundId
            }
    }

    public func removePendingMedia(ids: Set<String>) throws {
        guard !ids.isEmpty else {
            return
        }
        let allMedia = try loadPendingMedia()
        let remaining = allMedia.filter { !ids.contains($0.id) }
        let removed = allMedia.filter { ids.contains($0.id) }
        if remaining.isEmpty {
            try? FileManager.default.removeItem(at: pendingMediaIndexURL)
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
            try? FileManager.default.removeItem(at: media.fileURL)
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

    private func safePathComponent(_ value: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_."))
        let characters = value.unicodeScalars.map { scalar -> Character in
            allowed.contains(scalar) ? Character(scalar) : "_"
        }
        let safe = String(characters).trimmingCharacters(in: CharacterSet(charactersIn: "._-"))
        return safe.isEmpty ? "media" : safe
    }
}
