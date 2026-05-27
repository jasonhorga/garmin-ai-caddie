import Foundation
import PhotosUI
import SwiftUI

public struct MediaCaptureView: View {
    public let roundId: String
    public let hole: Int
    public let targetId: String
    public let offlineStore: OfflineStore?
    public let uploadClient: MediaUploadClient?
    public let onEvent: (LiveRoundEvent) -> Void
    public let onVisionFindings: ([[String: JSONValue]]) -> Void

    @State private var selectedPhotoItem: PhotosPickerItem?
    @State private var selectedVideoItem: PhotosPickerItem?
    @State private var statusText: String = "No media attached"

    private let formatter = ISO8601DateFormatter()

    public init(
        roundId: String,
        hole: Int,
        targetId: String,
        offlineStore: OfflineStore? = nil,
        uploadClient: MediaUploadClient? = nil,
        onEvent: @escaping (LiveRoundEvent) -> Void = { _ in },
        onVisionFindings: @escaping ([[String: JSONValue]]) -> Void = { _ in }
    ) {
        self.roundId = roundId
        self.hole = hole
        self.targetId = targetId
        self.offlineStore = offlineStore
        self.uploadClient = uploadClient
        self.onEvent = onEvent
        self.onVisionFindings = onVisionFindings
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                PhotosPicker(selection: $selectedPhotoItem, matching: .images) {
                    Label("Photo", systemImage: "camera")
                }
                PhotosPicker(selection: $selectedVideoItem, matching: .videos) {
                    Label("Video", systemImage: "video")
                }
            }
            Text(statusText)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .onChange(of: selectedPhotoItem) { _, item in
            Task {
                await importMedia(item: item, mediaKind: "photo")
            }
        }
        .onChange(of: selectedVideoItem) { _, item in
            Task {
                await importMedia(item: item, mediaKind: "video")
            }
        }
    }

    private func importMedia(item: PhotosPickerItem?, mediaKind: String) async {
        guard let item else {
            return
        }
        do {
            guard let data = try await item.loadTransferable(type: Data.self) else {
                statusText = "Media unavailable"
                return
            }
            let capturedAt = formatter.string(from: Date())
            let fileName = "\(targetId.replacingOccurrences(of: ":", with: "-"))-\(mediaKind).bin"
            let mediaEventId = UUID().uuidString
            let savedMedia: PendingMediaAttachment?
            if let offlineStore {
                savedMedia = try offlineStore.savePendingMedia(
                    data: data,
                    eventId: mediaEventId,
                    roundId: roundId,
                    hole: hole,
                    targetId: targetId,
                    assetLocalId: fileName,
                    mediaKind: mediaKind,
                    fileName: fileName,
                    capturedAt: capturedAt
                )
            } else {
                savedMedia = nil
            }
            let request = MediaCreateRequest(
                targetType: "hole",
                targetId: targetId,
                mediaKind: mediaKind,
                fileName: savedMedia?.fileName ?? fileName,
                contentBase64: data.base64EncodedString(),
                capturedAt: capturedAt
            )
            var uploadedMediaId: String?
            var analyzedFindings: [[String: JSONValue]] = []
            if let uploadClient {
                do {
                    let uploadResponse = try await uploadClient.uploadMedia(request)
                    uploadedMediaId = uploadResponse.media.id
                    let analysis = try await uploadClient.analyzeMedia(mediaId: uploadResponse.media.id)
                    analyzedFindings = analysis.findings.map { $0.contextPayload }
                    if !analyzedFindings.isEmpty {
                        onVisionFindings(analyzedFindings)
                    }
                } catch {
                    // The media bytes are already in OfflineStore; event sync can retry upload/analysis later.
                }
            }
            emitMediaEvent(
                mediaKind: mediaKind,
                fileName: savedMedia?.assetLocalId ?? fileName,
                fileURL: savedMedia?.fileURL,
                capturedAt: capturedAt,
                mediaId: uploadedMediaId,
                eventId: mediaEventId
            )
            statusText = analyzedFindings.isEmpty ? "\(mediaKind.capitalized) attached" : "\(mediaKind.capitalized) analyzed"
        } catch {
            statusText = "\(mediaKind.capitalized) attach failed"
        }
    }

    private func emitMediaEvent(mediaKind: String, fileName: String, fileURL: URL?, capturedAt: String, mediaId: String?, eventId: String) {
        let builder = LiveRoundEventBuilder(
            roundId: roundId,
            idFactory: { eventId },
            now: { ISO8601DateFormatter().date(from: capturedAt) ?? Date() }
        )
        if mediaKind == "photo" {
            onEvent(builder.makePhotoEvent(hole: hole, assetLocalId: fileName, fileURL: fileURL, note: nil, mediaId: mediaId))
        } else {
            onEvent(builder.makeVideoEvent(hole: hole, assetLocalId: fileName, fileURL: fileURL, durationS: nil, note: nil, mediaId: mediaId))
        }
    }
}
