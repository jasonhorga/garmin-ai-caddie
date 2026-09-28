import Foundation

public enum LiveFairwayResult: String, CaseIterable, Codable, Equatable {
    case hit
    case left
    case right
}

/// Where a hole's score came from (B0c `ai_caddie/rounds/score_source.py`). Stats skip a hole whose
/// source is `default` and was never changed, so an untouched par cannot inflate putting or GIR.
public enum LiveScoreSource: String, Codable, Equatable {
    case watchDetected = "watch_detected"
    case phoneShots = "phone_shots"
    case `default` = "default"
    case manualEdit = "manual_edit"
}

/// One-screen hole score (README §2, `score.html`). Everything is preselected, nothing explains
/// where it came from, and a correct guess is saved with one tap.
///
/// Preselection priority: the Watch's detected swings → the phone's 记一杆 count + 2 putts → the
/// default par (Par − 2 to the green + 2 putts). The tee result comes from the B0 fairway check.
/// A hole keeps its preselection source until the player changes any value; then it is
/// `manual_edit`.
///
/// Invariant (README §3): the total is never below putts + penalty + 1 — at least one full shot.
/// Raising putts or the penalty raises the total with them; choosing a lower total gives way to it
/// by lowering putts first, then the penalty. Lowering putts or the penalty never lowers the total.
public struct LiveScoreDraft: Codable, Equatable, Identifiable {
    public var id: Int { hole }

    public let hole: Int
    public let par: Int
    public private(set) var score: Int
    public private(set) var putts: Int
    public private(set) var penalty: Int
    public private(set) var fairway: LiveFairwayResult?
    /// The source of the preselected values.
    public let preselectedSource: LiveScoreSource
    /// True once the player changed any value in this sheet.
    public private(set) var edited: Bool
    public let advanceAfterSave: Bool

    /// The source written with the score: the preselection until the player edits it.
    public var source: LiveScoreSource { edited ? .manualEdit : preselectedSource }

    /// Choices on the score strip, always starting at 1 (the strip never auto-centres).
    public var scoreChoices: ClosedRange<Int> { 1...max(10, par + 5, score + 2) }
    /// The putt segments `0 / 1 / 2 / 3 / 4+` (`score.html`). `4+` keeps the real count (4…9),
    /// adjusted with its own −/+; stats read the actual number.
    public static let puttSegments = [0, 1, 2, 3, 4]
    public static let fourPlusSegment = 4
    public static let maximumPutts = 9
    public static let maximumPenalty = 9

    /// The putt segment shown selected: the count itself, or `4+` for four or more.
    public var puttSegment: Int { min(putts, Self.fourPlusSegment) }

    /// The smallest total these putts and penalty allow.
    public var minimumScore: Int { putts + penalty + 1 }

    /// A new hole: preselect from the best evidence available.
    public init(
        hole: Int,
        par: Int,
        watchSwingCount: Int? = nil,
        watchPuttCount: Int? = nil,
        phoneShotCount: Int,
        teeResult: LiveFairwayResult? = nil,
        advanceAfterSave: Bool = true
    ) {
        self.hole = hole
        self.par = par
        let defaultPutts = 2
        if let swings = watchSwingCount, swings > 0 {
            let putts = max(0, watchPuttCount ?? defaultPutts)
            self.score = swings + putts
            self.putts = putts
            self.preselectedSource = .watchDetected
        } else if phoneShotCount > 0 {
            self.score = phoneShotCount + defaultPutts
            self.putts = defaultPutts
            self.preselectedSource = .phoneShots
        } else {
            self.score = max(1, par)
            self.putts = min(defaultPutts, max(1, par) - 1)
            self.preselectedSource = .default
        }
        self.putts = min(self.putts, Self.maximumPutts)
        self.score = max(self.score, self.putts + 1)
        self.penalty = 0
        self.fairway = par == 3 ? nil : teeResult
        self.edited = false
        self.advanceAfterSave = advanceAfterSave
    }

    /// Reopen a saved hole from the scorecard. Saving it unchanged keeps its recorded source.
    public init(
        hole: Int,
        par: Int,
        savedScore: Int,
        savedPutts: Int,
        savedPenalty: Int,
        savedFairway: LiveFairwayResult?,
        savedSource: LiveScoreSource?
    ) {
        self.hole = hole
        self.par = par
        self.putts = min(max(0, savedPutts), Self.maximumPutts)
        self.penalty = min(max(0, savedPenalty), Self.maximumPenalty)
        // A legacy row that broke the invariant opens corrected; saving it records the correction.
        self.score = max(1, savedScore, self.putts + self.penalty + 1)
        self.fairway = par == 3 ? nil : savedFairway
        self.preselectedSource = savedSource ?? .manualEdit
        self.edited = false
        self.advanceAfterSave = false
    }

    /// The chosen total wins: putts, then the penalty, give way so that at least one full shot
    /// remains inside it.
    public mutating func selectScore(_ value: Int) {
        let next = max(1, value)
        guard next != score else { return }
        score = next
        putts = min(putts, max(0, score - penalty - 1))
        penalty = min(penalty, max(0, score - putts - 1))
        edited = true
    }

    /// More putts than the total allows raise the total with them.
    public mutating func selectPutts(_ value: Int) {
        let next = min(max(0, value), Self.maximumPutts)
        guard next != putts else { return }
        putts = next
        score = max(score, minimumScore)
        edited = true
    }

    /// The `4+` segment: selecting it sets 4 (or keeps a larger count already chosen).
    public mutating func selectPuttSegment(_ segment: Int) {
        if segment >= Self.fourPlusSegment {
            guard putts < Self.fourPlusSegment else { return }
            selectPutts(Self.fourPlusSegment)
        } else {
            selectPutts(segment)
        }
    }

    /// −/+ on the `4+` segment, within 4…9.
    public mutating func adjustFourPlusPutts(by delta: Int) {
        guard putts >= Self.fourPlusSegment else { return }
        selectPutts(min(max(Self.fourPlusSegment, putts + delta), Self.maximumPutts))
    }

    public mutating func selectFairway(_ result: LiveFairwayResult) {
        guard par != 3, fairway != result else { return }
        fairway = result
        edited = true
    }

    public mutating func adjustPenalty(by delta: Int) {
        let next = min(max(0, penalty + delta), Self.maximumPenalty)
        guard next != penalty else { return }
        penalty = next
        score = max(score, minimumScore)
        edited = true
    }
}

/// Score confirmation emits score facts only. Shot location and actual club have their own recording
/// task; including either here would turn a hole-end GPS fix into a fabricated golf shot.
public enum LiveScoreSubmission {
    public static func events(
        roundId: String,
        draft: LiveScoreDraft,
        note: String,
        timestamp: String,
        makeEventId: () -> String = { UUID().uuidString }
    ) -> [LiveRoundEvent] {
        let source = JSONValue.string(draft.source.rawValue)
        var scorePayload: [String: JSONValue] = [
            "strokes": .number(Double(draft.score)),
            "source": source,
        ]
        if draft.par != 3, let fairway = draft.fairway {
            scorePayload["fairway"] = .string(fairway.rawValue)
        }

        var result = [
            LiveRoundEvent(
                eventId: makeEventId(), roundId: roundId, timestamp: timestamp,
                hole: draft.hole, kind: .score, payload: scorePayload
            ),
            LiveRoundEvent(
                eventId: makeEventId(), roundId: roundId, timestamp: timestamp,
                hole: draft.hole, kind: .putt,
                payload: [
                    "putts": .number(Double(draft.putts)),
                    "source": source,
                ]
            ),
            LiveRoundEvent(
                eventId: makeEventId(), roundId: roundId, timestamp: timestamp,
                hole: draft.hole, kind: .penalty,
                payload: [
                    "penalties": .number(Double(draft.penalty)),
                    "source": source,
                ]
            ),
        ]

        let trimmedNote = note.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmedNote.isEmpty {
            result.append(
                LiveRoundEvent(
                    eventId: makeEventId(), roundId: roundId, timestamp: timestamp,
                    hole: draft.hole, kind: .note,
                    payload: ["note": .string(trimmedNote), "source": .string("ios_score_confirmation")]
                )
            )
        }
        return result
    }
}

/// The shots the player marked on one hole ("记一杆"), in the order they were marked. A mark made on
/// the watch is relayed into the phone's event log as the same `.location` event (clientId
/// `apple-watch`) and counts exactly like a phone mark: both are the player saying "I hit a shot
/// here". They preselect the score as `phone_shots` (marked shots + 2 putts) and the second mark
/// drives the tee-result preselection. `watch_detected` is reserved for the watch's automatic swing
/// detection (B7), which is passed separately as `watchSwingCount` and is never inferred from marks.
enum LiveMarkedShots {
    static func locations(in events: [LiveRoundEvent], roundId: String, hole: Int) -> [LiveRoundEvent] {
        events.filter { $0.roundId == roundId && $0.hole == hole && $0.kind == .location }
    }
}
