import Foundation

/// Sends the Watch every hole map of the live round that is on the phone.
///
/// The Watch shows a hole's map only once the phone has sent its bitmap, and a phone-started round
/// gives the Watch no template to fetch one itself. The live hole view sends only the hole it is
/// showing, so with the phone in a pocket the Watch sat on "地图准备中" (field report 2026-10-10).
/// `sync()` queues every cached hole not yet sent for the live round; it runs when a round is
/// activated, when its course download ends and when the Watch session activates. A transfer that
/// fails is retried on a bounded backoff while the same round is live.
@MainActor
final class WatchTopoSender {
    /// One hole map as the Watch looks it up: Garmin course, round hole and prep revision.
    struct Item: Hashable {
        let globalId: Int
        let roundHole: Int
        let localHole: Int
        let revision: String?

        var key: String { "\(roundHole)|\(globalId)|\(revision ?? "")" }
    }

    /// The round's holes keyed exactly as the hole view and the Watch state key them: round hole,
    /// source course, and the prep revision (falling back to the package hole's).
    static func plan(for package: LiveRoundPackage) -> [Item] {
        package.holes.map { hole in
            Item(
                globalId: hole.sourceGlobalId,
                roundHole: hole.number,
                localHole: hole.sourceLocalHole,
                revision: package.coursePrep?.holes.first(where: { $0.hole == hole.number })?.geometryRevision
                    ?? hole.geometryRevision
            )
        }
    }

    /// The bitmap on the phone, or nil. Called off the main actor's critical path.
    var load: (Item) async -> Data?
    /// Queues one transfer; false when the session cannot take it now.
    var enqueue: (Item, Data) -> Bool
    /// The live round's package, or nil when no round is being played.
    var livePackage: () -> LiveRoundPackage?
    /// Waits before each retry of a failed transfer; its count bounds the retries per hole.
    var retryDelaysNanoseconds: [UInt64] = [10_000_000_000, 60_000_000_000, 300_000_000_000]

    private var roundId: String?
    private var sent = Set<String>()
    private var failures: [String: Int] = [:]
    private var running: Task<Void, Never>?
    private var retry: Task<Void, Never>?

    init(
        load: @escaping (Item) async -> Data?,
        enqueue: @escaping (Item, Data) -> Bool,
        livePackage: @escaping () -> LiveRoundPackage?
    ) {
        self.load = load
        self.enqueue = enqueue
        self.livePackage = livePackage
    }

    /// Queues every cached, not yet sent hole of the live round. A newer call supersedes a running
    /// one; a different round (or none) forgets the previous round's state and pending retry.
    func sync() {
        guard let package = livePackage() else {
            reset(roundId: nil)
            return
        }
        if package.roundId != roundId {
            reset(roundId: package.roundId)
        }
        running?.cancel()
        let items = Self.plan(for: package)
        let round = package.roundId
        running = Task { [weak self] in
            for item in items {
                guard let self, !Task.isCancelled, self.roundId == round else { return }
                guard !self.sent.contains(item.key) else { continue }
                guard let data = await self.load(item), !Task.isCancelled, self.roundId == round else { continue }
                if self.enqueue(item, data) {
                    self.sent.insert(item.key)
                }
            }
        }
    }

    /// The session (re)activated, possibly with another Watch: send the round again, with fresh
    /// retries.
    func forgetSent() {
        sent.removeAll()
        failures.removeAll()
    }

    /// A queued topo transfer for (course, round hole) failed: it is no longer sent, and a retry is
    /// scheduled while this round is live, up to `retryDelaysNanoseconds.count` times per hole.
    func transferFailed(globalId: Int, roundHole: Int) {
        let failed = sent.filter { $0.hasPrefix("\(roundHole)|\(globalId)|") }
        guard !failed.isEmpty else { return }
        sent.subtract(failed)
        let attempt = failed.map { failures[$0, default: 0] }.max() ?? 0
        for key in failed { failures[key, default: 0] += 1 }
        guard attempt < retryDelaysNanoseconds.count, retry == nil, let round = roundId else { return }
        let delay = retryDelaysNanoseconds[attempt]
        retry = Task { [weak self] in
            try? await Task.sleep(nanoseconds: delay)
            guard let self, !Task.isCancelled else { return }
            self.retry = nil
            guard self.livePackage()?.roundId == round else { return }
            self.sync()
        }
    }

    /// Test synchronisation: the running pass and any scheduled retry (and the pass it starts), to
    /// completion.
    func waitUntilIdle() async {
        var awaited: [Task<Void, Never>] = []
        while let task = [running, retry].compactMap({ $0 }).first(where: { !awaited.contains($0) }) {
            awaited.append(task)
            await task.value
        }
    }

    private func reset(roundId: String?) {
        running?.cancel()
        retry?.cancel()
        running = nil
        retry = nil
        self.roundId = roundId
        sent.removeAll()
        failures.removeAll()
    }
}
