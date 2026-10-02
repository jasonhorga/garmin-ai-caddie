import Foundation

/// The one writer of the backend manual bag (`PUT /api/v2/players/{id}/clubs/bag`). Every 球包
/// change (add, remove, a typed distance, 用 Garmin 球包重置 as `{"clubs": []}`) lands in a durable
/// outbox first; a single serialized worker owned by this long-lived object — never by a screen —
/// sends the latest outbox after a short pause, and keeps retrying transport / server failures with
/// backoff until the server has it. So leaving 球包 right after a change, a newer change while a
/// PUT is in flight, or a failed write all end with the server holding the last edit.
///
/// Everything is per player: the outbox lives under the signed-in player's keys and records that
/// player, the PUT targets exactly that player's id, and an account switch stops the worker so one
/// account's pending edit is never sent with another account's credentials. A permanent rejection
/// (401 / 403 / 4xx validation) is not retried: the intent is kept, marked rejected, and shown.
@MainActor
public final class ClubBagSyncCoordinator: ObservableObject {
    public typealias Sender = (_ playerId: String, _ clubs: [ManualClubInput]) async throws -> Void
    public typealias Fetcher = (_ playerId: String) async throws -> EffectiveClubBagResponse

    public enum Status: Equatable {
        case idle
        case pending
        case syncing
        /// The last attempt failed with a transport/server error; the worker is waiting to retry.
        case failed
        /// The server refused the write (HTTP status); it is kept but not retried until a new edit.
        case rejected(Int)
    }

    struct Outbox: Codable, Equatable {
        var playerId: String
        var generation: Int
        var clubs: [ManualClubInput]
        /// The HTTP status of a permanent rejection; such an outbox is never retried by itself.
        var rejectedStatus: Int?
    }

    public static let shared = ClubBagSyncCoordinator()
    static let debounceNanoseconds: UInt64 = 800_000_000
    /// The PUT target when no player is bound (the owner admin build): the owner's own bag.
    static let ownerTarget = "me"

    /// Where the bound player's cloud restore stands. Editing waits for it (see `canEdit`).
    public enum RestoreState: Equatable {
        case unknown
        case restoring
        case restored
        case failed
    }

    @Published public private(set) var status: Status = .idle
    @Published public private(set) var restoreState: RestoreState = .unknown
    /// Every PUT attempt that failed, for tests and diagnostics.
    public private(set) var failedAttempts = 0

    private let defaults: () -> UserDefaults
    private let sleep: (UInt64) async -> Void
    private var sender: Sender?
    private var fetcher: Fetcher?
    private var worker: Task<Void, Never>?
    private var workerID = 0
    /// The previous worker, which may still be inside `sender` after it was cancelled (an account
    /// switch). A new worker awaits it first, so there is never more than one PUT writer.
    private var fence: Task<Void, Never>?
    /// Wakes the worker from its retry backoff (设置 → 重新同步球包) without replacing it.
    private var backoffWake: CheckedContinuation<Void, Never>?
    private var backoffID = 0
    private var restoreTask: Task<Bool, Never>?

    init(
        defaults: @escaping () -> UserDefaults = { ClubBagStore.defaults },
        sleep: @escaping (UInt64) async -> Void = { try? await Task.sleep(nanoseconds: $0) }
    ) {
        self.defaults = defaults
        self.sleep = sleep
        status = restingStatus()
    }

    /// Bind storage and sync to the signed-in player. A worker still running for the previous
    /// player stops: its outbox stays under that player and resumes only when they sign in again.
    public func activate(playerId: String?, migrateLegacy: Bool) {
        let previous = ClubBagStore.playerId
        ClubBagStore.bind(playerId: playerId, migrateLegacy: migrateLegacy)
        guard ClubBagStore.playerId != previous else { return }
        wakeBackoff()
        worker?.cancel()
        fence = worker ?? fence
        worker = nil
        restoreTask = nil
        restoreState = .unknown
        status = restingStatus()
        resumeIfPending()
    }

    /// An edit is built on the whole bag and PUT whole, so it must start from the cloud bag on a
    /// reinstall / second phone: allowed once this phone has matched the cloud (now or before), or
    /// when there is no backend to restore from. While a restore is in flight — or has failed on a
    /// phone that never matched the cloud — the 球包 controls stay disabled.
    /// Whether there is a backend to restore from and save to.
    public var hasBackend: Bool { fetcher != nil }

    public var canEdit: Bool {
        switch restoreState {
        case .restored: return true
        case .restoring: return false
        case .failed, .unknown: return fetcher == nil || ClubBagStore.hasSyncedWithCloud
        }
    }

    /// Point the worker at the signed-in backend (no-op without one) and resume a saved outbox.
    public func configure(apiBaseURL: URL?, adminToken: String?) {
        guard let apiBaseURL else { return }
        configure(
            sender: { playerId, clubs in
                _ = try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken)
                    .putManualClubBag(playerId: playerId, clubs: clubs)
            },
            fetcher: { playerId in
                try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken)
                    .fetchEffectiveClubBag(playerId: playerId)
            }
        )
    }

    func configure(sender: @escaping Sender, fetcher: Fetcher? = nil) {
        self.sender = sender
        if let fetcher { self.fetcher = fetcher }
        resumeIfPending()
    }

    /// Queue the whole manual bag of the bound player (latest wins). An empty list clears the
    /// server's manual bag. A new intent replaces a rejected one.
    public func enqueue(_ clubs: [ManualClubInput]) {
        let player = ClubBagStore.playerId
        let generationKey = ClubBagStore.key(ClubBagStore.generationBase, playerId: player)
        let generation = defaults().integer(forKey: generationKey) + 1
        defaults().set(generation, forKey: generationKey)
        save(Outbox(playerId: player ?? Self.ownerTarget, generation: generation, clubs: clubs, rejectedStatus: nil), for: player)
        if status != .failed { status = .pending }
        startWorker(for: player, debounce: true)
    }

    /// Restore the bound player's manual bag from the server (reinstall / second phone) before it
    /// is edited here. Concurrent callers (launch, foreground, the 球包 screen) share one request.
    /// Skipped while a local edit is still queued: that edit was made on a restored or synced bag
    /// and is newer.
    @discardableResult
    public func restoreFromServer() async -> Bool {
        // Decided at the call, before any suspension: an edit queued now is newer than the cloud.
        if fetcher != nil, outbox(for: ClubBagStore.playerId) != nil {
            restoreState = .restored
            return false
        }
        if let restoreTask { return await restoreTask.value }
        let task = Task { await self.performRestore() }
        restoreTask = task
        let restored = await task.value
        if restoreTask == task { restoreTask = nil }
        return restored
    }

    private func performRestore() async -> Bool {
        let player = ClubBagStore.playerId
        guard let fetcher else { return false }
        guard outbox(for: player) == nil else {
            restoreState = .restored
            return false
        }
        restoreState = .restoring
        let response = try? await fetcher(player ?? Self.ownerTarget)
        guard ClubBagStore.playerId == player else { return false }
        guard let response else {
            AICaddieLog.network.error("Club bag cloud restore failed")
            restoreState = .failed
            return false
        }
        if outbox(for: player) == nil {
            ClubBagStore.hydrate(from: response)
            ClubBagStore.hasSyncedWithCloud = true
        }
        restoreState = .restored
        return true
    }

    /// 设置 → 重新同步球包: re-read a failed cloud restore and resend a rejected (e.g. after
    /// re-login) or backing-off outbox now.
    public func retryNow() {
        let player = ClubBagStore.playerId
        if var pending = outbox(for: player), pending.rejectedStatus != nil {
            pending.rejectedStatus = nil
            save(pending, for: player)
            status = .pending
        }
        // Never a second writer: a running worker is only woken from its backoff (a PUT it has
        // already handed to `sender` finishes first); a new one starts only when none runs.
        if worker != nil {
            wakeBackoff()
        } else if outbox(for: player) != nil {
            startWorker(for: player, debounce: false)
        }
        if restoreState == .failed {
            Task { await restoreFromServer() }
        }
    }

    /// Wait until the worker is idle (the outbox is sent, rejected, or there is no backend).
    public func flush() async {
        while let worker {
            await worker.value
        }
    }

    var pendingClubs: [ManualClubInput]? { outbox(for: ClubBagStore.playerId)?.clubs }
    var pendingOutbox: Outbox? { outbox(for: ClubBagStore.playerId) }

    private func resumeIfPending() {
        guard let pending = outbox(for: ClubBagStore.playerId), pending.rejectedStatus == nil else { return }
        startWorker(for: ClubBagStore.playerId, debounce: false)
    }

    private func startWorker(for player: String?, debounce: Bool) {
        guard worker == nil else { return }
        workerID &+= 1
        let id = workerID
        let prior = fence
        worker = Task { [weak self] in
            await prior?.value
            await self?.drain(player: player, debounce: debounce)
            if self?.workerID == id { self?.worker = nil }
        }
    }

    /// The retry backoff, cut short by `wakeBackoff()`.
    private func pauseForRetry(_ nanoseconds: UInt64) async {
        backoffID &+= 1
        let id = backoffID
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            backoffWake = continuation
            Task { [weak self] in
                await self?.sleep(nanoseconds)
                if self?.backoffID == id { self?.wakeBackoff() }
            }
        }
    }

    private func wakeBackoff() {
        backoffWake?.resume()
        backoffWake = nil
    }

    private func drain(player: String?, debounce: Bool) async {
        if debounce { await sleep(Self.debounceNanoseconds) }
        var failures = 0
        while !Task.isCancelled, ClubBagStore.playerId == player,
              let pending = outbox(for: player), pending.rejectedStatus == nil {
            guard let sender else {
                status = .pending
                return
            }
            status = failures == 0 ? .syncing : .failed
            do {
                try await sender(pending.playerId, pending.clubs)
                failures = 0
                if ClubBagStore.playerId == player { ClubBagStore.hasSyncedWithCloud = true }
                // A newer edit queued while this PUT was in flight stays for the next turn.
                if outbox(for: player)?.generation == pending.generation {
                    defaults().removeObject(forKey: ClubBagStore.key(ClubBagStore.outboxBase, playerId: player))
                }
            } catch {
                failedAttempts += 1
                AICaddieLog.network.error("Club bag PUT failed: \(String(describing: error), privacy: .public)")
                if let code = Self.permanentStatus(error) {
                    if var current = outbox(for: player), current.generation == pending.generation {
                        current.rejectedStatus = code
                        save(current, for: player)
                        if ClubBagStore.playerId == player { status = .rejected(code) }
                        return
                    }
                    continue  // a newer edit replaced the rejected one: send it
                }
                failures += 1
                if ClubBagStore.playerId == player { status = .failed }
                await pauseForRetry(Self.retryDelay(afterFailures: failures))
            }
        }
        if ClubBagStore.playerId == player { status = restingStatus() }
    }

    /// 401 / 403 / 404 / 409 / 4xx validation will not succeed by retrying the same payload.
    /// Timeouts (408) and rate limits (429) are transient.
    static func permanentStatus(_ error: Error) -> Int? {
        guard case SyncClientError.http(let status, _) = error,
              (400..<500).contains(status), status != 408, status != 429 else { return nil }
        return status
    }

    /// 2 s, 4 s, 8 s … capped at one minute.
    static func retryDelay(afterFailures failures: Int) -> UInt64 {
        let seconds = min(60, 1 << min(max(failures, 1), 6))
        return UInt64(seconds) * 1_000_000_000
    }

    private func restingStatus() -> Status {
        guard let pending = outbox(for: ClubBagStore.playerId) else { return .idle }
        return pending.rejectedStatus.map(Status.rejected) ?? .pending
    }

    private func outbox(for player: String?) -> Outbox? {
        guard let data = defaults().data(forKey: ClubBagStore.key(ClubBagStore.outboxBase, playerId: player)) else { return nil }
        return try? JSONDecoder().decode(Outbox.self, from: data)
    }

    private func save(_ outbox: Outbox, for player: String?) {
        guard let data = try? JSONEncoder().encode(outbox) else { return }
        defaults().set(data, forKey: ClubBagStore.key(ClubBagStore.outboxBase, playerId: player))
    }
}
