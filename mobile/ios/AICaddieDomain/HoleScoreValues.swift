import Foundation

/// A hole's total, putts and penalty under the one score rule shared by the phone and the Watch
/// (README §3), so the two never behave differently:
/// - the total is never below putts + penalty + 1 (at least one full shot);
/// - raising putts or the penalty raises the total only when it must;
/// - lowering putts or the penalty never lowers the total (the total is what the player chose);
/// - choosing a lower total gives way by lowering putts first, then the penalty.
public struct HoleScoreValues: Codable, Equatable, Sendable {
    public static let maximumPutts = 9
    public static let maximumPenalty = 9

    public private(set) var score: Int
    public private(set) var putts: Int
    public private(set) var penalty: Int

    /// Clamps putts and penalty into range and lifts the total to the invariant.
    public init(score: Int, putts: Int, penalty: Int) {
        self.putts = min(max(0, putts), Self.maximumPutts)
        self.penalty = min(max(0, penalty), Self.maximumPenalty)
        self.score = max(1, score, self.putts + self.penalty + 1)
    }

    /// The smallest total these putts and penalty allow.
    public var minimumScore: Int { putts + penalty + 1 }

    /// The chosen total wins: putts, then the penalty, give way. False when nothing changed.
    @discardableResult
    public mutating func selectScore(_ value: Int) -> Bool {
        let next = max(1, value)
        guard next != score else { return false }
        score = next
        putts = min(putts, max(0, score - penalty - 1))
        penalty = min(penalty, max(0, score - putts - 1))
        return true
    }

    /// More putts than the total allows raise the total with them. False when nothing changed.
    @discardableResult
    public mutating func selectPutts(_ value: Int) -> Bool {
        let next = min(max(0, value), Self.maximumPutts)
        guard next != putts else { return false }
        putts = next
        score = max(score, minimumScore)
        return true
    }

    /// A larger penalty than the total allows raises the total with it. False when nothing changed.
    @discardableResult
    public mutating func selectPenalty(_ value: Int) -> Bool {
        let next = min(max(0, value), Self.maximumPenalty)
        guard next != penalty else { return false }
        penalty = next
        score = max(score, minimumScore)
        return true
    }
}
