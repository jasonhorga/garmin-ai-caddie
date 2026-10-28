import Foundation

struct ClientTimingRecord: Equatable {
    let requestId: String
    let path: String
    let clientTotalMs: Double
    let status: Int?
    let error: String?
    let startedAt: String
    let networkType: String?
    let serverTotalMs: Double?
}

struct ClientTimingUploadRecord {}

/// Red-test seam: the production timing store is supplied by the implementation commit.
final class ClientTimingStore {
    init(fileURL: URL? = nil) {}
    static func prepareAtLaunch() {}
    func record(_ value: ClientTimingRecord) {}
    func snapshot() -> [ClientTimingRecord] { [] }
    func takeBatchIfDue(now: TimeInterval, foregroundStartRunning: Bool, threshold: Int = 10, interval: TimeInterval = 60) -> [ClientTimingRecord]? { nil }
    func finishUpload() {}
}
