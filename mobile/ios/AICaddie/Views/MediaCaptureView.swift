import Foundation
import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

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
    @State private var pendingFindings: [VisionFinding] = []
    @State private var confirmedFindings: [VisionFinding] = []

    private let formatter = ISO8601DateFormatter()
    private let maxPhotoBytes = 12 * 1024 * 1024
    private let maxVideoBytes = 80 * 1024 * 1024

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
            if !pendingFindings.isEmpty {
                ForEach(Array(pendingFindings.enumerated()), id: \.offset) { item in
                    let finding = item.element
                    VStack(alignment: .leading, spacing: 4) {
                        Text(finding.findingType)
                            .font(.caption.weight(.semibold))
                        Text(finding.evidenceText)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        HStack {
                            Button("Confirm") {
                                Task {
                                    await confirmVisionFinding(finding: finding, state: "manual_confirmed")
                                }
                            }
                            Button("Reject") {
                                Task {
                                    await confirmVisionFinding(finding: finding, state: "rejected")
                                }
                            }
                        }
                    }
                }
            }
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
            let maxBytes = mediaKind == "video" ? maxVideoBytes : maxPhotoBytes
            guard data.count <= maxBytes else {
                statusText = "\(mediaKind.capitalized) exceeds upload limit"
                return
            }
            let capturedAt = formatter.string(from: Date())
            let contentType = preferredContentType(for: item, mediaKind: mediaKind)
            let fileExtension = contentType?.preferredFilenameExtension ?? (mediaKind == "video" ? "mp4" : "jpg")
            let mimeType = contentType?.preferredMIMEType ?? (mediaKind == "video" ? "video/mp4" : "image/jpeg")
            let fileName = "\(targetId.replacingOccurrences(of: ":", with: "-"))-\(mediaKind).\(fileExtension)"
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
                capturedAt: capturedAt,
                mimeType: mimeType
            )
            var uploadedMediaId: String?
            var analyzedCount = 0
            var uploadDeferred = false
            if let uploadClient {
                do {
                    let uploadResponse = try await uploadClient.uploadMediaWithRetry(request)
                    uploadedMediaId = uploadResponse.media.id
                    if let savedMedia {
                        try? offlineStore?.removePendingMedia(ids: Set([savedMedia.id]))
                    }
                    let analysis = try await uploadClient.analyzeMedia(mediaId: uploadResponse.media.id)
                    pendingFindings = analysis.findings
                    analyzedCount = analysis.findings.count
                } catch {
                    uploadDeferred = savedMedia != nil
                }
            } else {
                uploadDeferred = savedMedia != nil
            }
            emitMediaEvent(
                mediaKind: mediaKind,
                fileName: savedMedia?.assetLocalId ?? fileName,
                fileURL: savedMedia?.fileURL,
                capturedAt: capturedAt,
                mediaId: uploadedMediaId,
                eventId: mediaEventId
            )
            if uploadDeferred {
                statusText = "\(mediaKind.capitalized) saved offline; upload retry pending"
            } else {
                statusText = analyzedCount == 0 ? "\(mediaKind.capitalized) attached" : "\(mediaKind.capitalized) analyzed; confirm findings before caddie use"
            }
        } catch {
            statusText = "\(mediaKind.capitalized) attach failed"
        }
    }

    private func preferredContentType(for item: PhotosPickerItem, mediaKind: String) -> UTType? {
        let candidates = item.supportedContentTypes
        if mediaKind == "video" {
            return candidates.first { $0.conforms(to: .movie) || $0.conforms(to: .video) }
        }
        return candidates.first { $0.conforms(to: .image) }
    }

    @MainActor
    private func confirmVisionFinding(finding: VisionFinding, state: String) async {
        guard let findingId = finding.id, let uploadClient else {
            return
        }
        do {
            let response = try await uploadClient.confirmVisionFinding(
                findingId: findingId,
                requestBody: VisionFindingConfirmationRequest(confirmationState: state)
            )
            pendingFindings.removeAll { $0.id == findingId }
            if state == "manual_confirmed" {
                confirmedFindings.removeAll { $0.id == findingId }
                confirmedFindings.append(response.finding)
                onVisionFindings(confirmedFindings.map { $0.contextPayload })
                statusText = "Finding confirmed for caddie"
            } else {
                statusText = "Finding rejected"
            }
        } catch {
            statusText = "Finding confirmation failed"
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
