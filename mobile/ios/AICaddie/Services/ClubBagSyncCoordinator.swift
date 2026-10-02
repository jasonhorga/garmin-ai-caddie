import Foundation

/// The one writer of the backend manual bag (`PUT /api/v2/players/me/clubs/bag`). Every 球包 change
/// (add, remove, a typed distance, 用 Garmin 球包重置 as `{"clubs": []}`) lands in a durable outbox
/// first; a single serialized worker owned by this long-lived object — never by a screen — sends the
/// latest outbox after a short pause, and keeps retrying with backoff until the server has it. So
/// leaving 球包 right after a change, a newer change while a PUT is in flight, or a failed write all
/// end with the server holding the last edit. The outbox survives relaunch and is resumed on
/// `configure`.
@MainActor
public final class ClubBagSyncCoordinator: ObservableObject {
    public typealias Sender = ([ManualClubInput]) async throws -> Void

    public enum Status: Equatable {
        case idle
        case pending
        case syncing
        /// The last attempt failed; the worker is waiting to retry.
        case failed
    }

    struct Outbox: Codable, Equatable {
        var generation: Int
        var clubs: [ManualClubInput]
    }

    public static let shared = ClubBagSyncCoordinator()
    static let outboxKey = "ai-caddie.club-bag-outbox-v1"
    static let debounceNanoseconds: UInt64 = 800_000_000

    @Published public private(set) var status: Status = .idle
    /// Every PUT attempt that failed, for tests and diagnostics.
    public private(set) var failedAttempts = 0

    private let defaults: () -> UserDefaults
    private let sleep: (UInt64) async -> Void
    private var sender: Sender?
    private var worker: Task<Void, Never>?

    init(
        defaults: @escaping () -> UserDefaults = { ClubBagStore.defaults },
        sleep: @escaping (UInt64) async -> Void = { try? await Task.sleep(nanoseconds: $0) }
    ) {
        self.defaults = defaults
        self.sleep = sleep
        if pendingOutbox() != nil { status = .pending }
    }

    /// Point the worker at the signed-in backend (no-op without one) and resume a saved outbox.
    public func configure(apiBaseURL: URL?, adminToken: String?) {
        guard let apiBaseURL else { return }
        configure(sender: { clubs in
            _ = try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken).putManualClubBag(clubs: clubs)
        })
    }

    func configure(sender: @escaping Sender) {
        self.sender = sender
        if pendingOutbox() != nil { startWorker(debounce: false) }
    }

    /// Queue the whole manual bag (latest wins). An empty list clears the server's manual bag.
    public func enqueue(_ clubs: [ManualClubInput]) {
        let generation = (pendingOutbox()?.generation ?? defaults().integer(forKey: Self.outboxKey + ".generation")) + 1
        defaults().set(generation, forKey: Self.outboxKey + ".generation")
        save(Outbox(generation: generation, clubs: clubs))
        if status != .failed { status = .pending }
        startWorker(debounce: true)
    }

    /// Wait until the worker is idle (the outbox is sent, or there is no backend to send it to).
    public func flush() async {
        while let worker {
            await worker.value
        }
    }

    var pendingClubs: [ManualClubInput]? { pendingOutbox()?.clubs }

    private func startWorker(debounce: Bool) {
        guard worker == nil else { return }
        worker = Task { [weak self] in
            await self?.drain(debounce: debounce)
        }
    }

    private func drain(debounce: Bool) async {
        defer { worker = nil }
        if debounce { await sleep(Self.debounceNanoseconds) }
        var failures = 0
        while let pending = pendingOutbox() {
            guard let sender else {
                status = .pending
                return
            }
            status = failures == 0 ? .syncing : .failed
            do {
                try await sender(pending.clubs)
                failures = 0
                // A newer edit queued while this PUT was in flight stays for the next turn.
                if pendingOutbox()?.generation == pending.generation {
                    defaults().removeObject(forKey: Self.outboxKey)
                }
            } catch {
                failures += 1
                failedAttempts += 1
                status = .failed
                await sleep(Self.retryDelay(afterFailures: failures))
            }
        }
        status = .idle
    }

    /// 2 s, 4 s, 8 s … capped at one minute.
    static func retryDelay(afterFailures failures: Int) -> UInt64 {
        let seconds = min(60, 1 << min(max(failures, 1), 6))
        return UInt64(seconds) * 1_000_000_000
    }

    private func pendingOutbox() -> Outbox? {
        guard let data = defaults().data(forKey: Self.outboxKey) else { return nil }
        return try? JSONDecoder().decode(Outbox.self, from: data)
    }

    private func save(_ outbox: Outbox) {
        guard let data = try? JSONEncoder().encode(outbox) else { return }
        defaults().set(data, forKey: Self.outboxKey)
    }
}
