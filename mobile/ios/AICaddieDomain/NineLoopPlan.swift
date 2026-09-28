import Foundation

/// One of a course's own nine-hole loops (README §8): A / B / C on a 27-hole venue, or the two
/// halves of an 18-hole course (e.g. 前九 / 后九). `id` is stable (the loop's Garmin course id, or
/// the course id plus its half); `name` is the course's own loop name, never a Garmin "9 洞组".
public struct NineLoop: Codable, Equatable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let par: Int?
    public let yards: Int?

    public init(id: String, name: String, par: Int? = nil, yards: Int? = nil) {
        self.id = id
        self.name = name
        self.par = par
        self.yards = yards
    }

    /// Only the course's single-letter loop names get " 场" ("A" → "A 场"); 东 / 前九 / 湖景场 stay as
    /// they are.
    public var displayName: String { Self.displayName(name) }

    public static func displayName(_ name: String) -> String {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let capitals: ClosedRange<Unicode.Scalar> = "A"..."Z"
        guard trimmed.unicodeScalars.count == 1,
              let scalar = trimmed.unicodeScalars.first,
              capitals.contains(scalar) else { return trimmed }
        return trimmed + " 场"
    }
}

/// The loops a venue offers, in the course's own order, and the player's usual pairings
/// (first loop id → second loop id, from history or the course's fixed front/back pair).
public struct NineLoopCourse: Codable, Equatable, Sendable {
    public let id: String
    public let loops: [NineLoop]
    public let usualPairs: [String: String]

    public init(id: String, loops: [NineLoop], usualPairs: [String: String] = [:]) {
        self.id = id
        self.loops = loops
        self.usualPairs = usualPairs
    }

    public func hasLoop(_ id: String) -> Bool { loops.contains { $0.id == id } }

    public func loop(_ id: String) -> NineLoop? { loops.first { $0.id == id } }

    /// The usual pairing when it is still one of this course's loops.
    public func usualSecond(after first: String) -> String? {
        guard let pair = usualPairs[first], hasLoop(pair) else { return nil }
        return pair
    }

    /// The usual pairing if known, else the next loop in the course's order (wrapping, so a
    /// one-loop course pairs with itself).
    public func defaultSecond(after first: String) -> String? {
        if let pair = usualSecond(after: first) { return pair }
        guard !loops.isEmpty else { return nil }
        let index = loops.firstIndex { $0.id == first } ?? -1
        return loops[(index + 1) % loops.count].id
    }
}

/// The one nine-loop state machine (README §8, IMPLEMENTATION_PLAN B4), shared by phone and watch.
///
/// Start: choose only the **first** loop. The second loop is prefilled with the default (the usual
/// pairing, else the next loop) and can be changed — to any loop, the same loop again, or "stop
/// after nine" — at the turn or any time before the first hole of the second loop is played; from
/// then on it is locked. Changing the course or the first loop re-resolves the second loop; a
/// second loop that is no longer offered is replaced, while "stop after nine" is kept.
public struct NineLoopPlan: Codable, Equatable, Sendable {
    public enum Second: Codable, Equatable, Hashable, Sendable {
        case loop(String)
        case stopAfterNine
    }

    public enum Phase: String, Codable, Equatable, Sendable {
        /// Choosing where to start; nothing played yet.
        case choosing
        /// Playing the first loop.
        case firstLoop
        /// The first loop is finished; the second choice is on screen.
        case atTurn
        /// The second loop's first hole was played; the choice is locked.
        case secondLoop
        /// The round ended after nine.
        case finishedAfterNine
    }

    public private(set) var course: NineLoopCourse
    public private(set) var first: String
    public private(set) var second: Second
    public private(set) var phase: Phase

    /// Start on a course's first loop (or the given one) with the default second loop.
    public init?(course: NineLoopCourse, first: String? = nil) {
        guard let start = first.flatMap({ course.hasLoop($0) ? $0 : nil }) ?? course.loops.first?.id else {
            return nil
        }
        self.course = course
        self.first = start
        self.second = course.defaultSecond(after: start).map(Second.loop) ?? .stopAfterNine
        self.phase = .choosing
    }

    public var firstLoop: NineLoop? { course.loop(first) }

    public var secondLoop: NineLoop? {
        guard case .loop(let id) = second else { return nil }
        return course.loop(id)
    }

    /// True when the chosen second loop is the course's usual pairing ("上次搭配").
    public var secondIsUsualPairing: Bool {
        guard case .loop(let id) = second else { return false }
        return course.usualSecond(after: first) == id
    }

    /// The second choice can change until the second loop's first hole is played.
    public var canChangeSecond: Bool {
        switch phase {
        case .choosing, .firstLoop, .atTurn: return true
        case .secondLoop, .finishedAfterNine: return false
        }
    }

    /// The first loop and the course can change only before anything is played.
    public var canChangeFirst: Bool { phase == .choosing }

    // MARK: start

    public mutating func selectCourse(_ course: NineLoopCourse) {
        guard canChangeFirst, let start = course.loops.first?.id else { return }
        self.course = course
        first = start
        second = defaultSecond(after: start)
    }

    public mutating func selectFirst(_ id: String) {
        guard canChangeFirst, course.hasLoop(id), id != first else { return }
        first = id
        second = defaultSecond(after: id)
    }

    /// The course's loops changed (e.g. a refreshed catalogue): keep valid choices, replace stale ones.
    public mutating func normalize(with course: NineLoopCourse) {
        self.course = course
        if !course.hasLoop(first), canChangeFirst, let start = course.loops.first?.id {
            first = start
        }
        if case .loop(let id) = second, !course.hasLoop(id), canChangeSecond {
            second = defaultSecond(after: first)
        }
    }

    public mutating func beginFirstLoop() {
        guard phase == .choosing else { return }
        phase = .firstLoop
    }

    // MARK: the turn

    /// The last hole of the first loop was saved: ask which nine comes next.
    public mutating func reachTurn() {
        guard phase == .choosing || phase == .firstLoop else { return }
        phase = .atTurn
    }

    /// Choose the second loop (any loop, the same one included) or stop after nine. Ignored once
    /// the second loop has started.
    public mutating func chooseSecond(_ choice: Second) {
        guard canChangeSecond else { return }
        if case .loop(let id) = choice, !course.hasLoop(id) { return }
        second = choice
    }

    /// The first hole of the second loop was played: lock the choice. Stopping after nine ends it.
    public mutating func beginSecondLoop() {
        guard canChangeSecond else { return }
        phase = second == .stopAfterNine ? .finishedAfterNine : .secondLoop
    }

    public mutating func finishAfterNine() {
        guard canChangeSecond else { return }
        second = .stopAfterNine
        phase = .finishedAfterNine
    }

    // MARK: copy

    /// "从 B 场 开始 · 蓝 T" (`pre-round.html`).
    public func startTitle(teeName: String?) -> String {
        let loop = firstLoop.map { "从 \($0.displayName) 开始" } ?? "开始"
        guard let teeName, !teeName.isEmpty else { return loop }
        return "\(loop) · \(teeName)"
    }

    /// "接着打 C 场" / "结束 · 只打 9 洞".
    public var turnActionTitle: String {
        guard let loop = secondLoop else { return "结束 · 只打 9 洞" }
        return "接着打 \(loop.displayName)"
    }

    /// "B 场打完了".
    public var turnTitle: String {
        "\(firstLoop?.displayName ?? "前 9 洞")打完了"
    }

    private func defaultSecond(after id: String) -> Second {
        course.defaultSecond(after: id).map(Second.loop) ?? .stopAfterNine
    }
}
