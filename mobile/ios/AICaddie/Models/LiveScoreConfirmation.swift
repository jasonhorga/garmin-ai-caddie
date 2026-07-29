import Foundation

public enum LiveScoreFlowStep: String, Codable, Equatable {
    case recommendation
    case score
    case putts
    case fairway
    case penalty
}

public enum LiveFairwayResult: String, CaseIterable, Codable, Equatable {
    case hit
    case left
    case right
}

/// A small, durable phone scoring draft. It mirrors the already-proven Watch order without coupling
/// the phone's current-hole cursor to score events or pretending that scoring created a GPS shot.
public struct LiveScoreDraft: Codable, Equatable, Identifiable {
    public var id: Int { hole }

    public let hole: Int
    public let par: Int
    public var score: Int
    public var putts: Int
    public var penalty: Int
    public var fairway: LiveFairwayResult?
    public private(set) var step: LiveScoreFlowStep
    public let advanceAfterSave: Bool

    public init(
        hole: Int,
        par: Int,
        recordedShotCount: Int,
        currentScore: Int,
        currentPutts: Int,
        currentPenalty: Int,
        currentFairway: LiveFairwayResult? = nil,
        offerRecommendation: Bool = true,
        advanceAfterSave: Bool = true
    ) {
        self.hole = hole
        self.par = par
        self.score = max(1, recordedShotCount > 0 ? recordedShotCount + 2 : currentScore)
        self.putts = max(0, currentPutts)
        self.penalty = max(0, currentPenalty)
        self.fairway = par == 3 ? nil : currentFairway
        self.step = offerRecommendation ? .recommendation : .score
        self.advanceAfterSave = advanceAfterSave
    }

    public mutating func startManualEntry() {
        step = .score
    }

    public mutating func advanceManualEntry() {
        switch step {
        case .recommendation:
            step = .score
        case .score:
            putts = min(putts, score)
            step = .putts
        case .putts:
            step = par == 3 ? .penalty : .fairway
        case .fairway:
            if fairway != nil { step = .penalty }
        case .penalty:
            break
        }
    }

    public mutating func selectFairway(_ result: LiveFairwayResult) {
        guard par != 3 else { return }
        fairway = result
        step = .penalty
    }

    public mutating func retreatManualEntry() {
        switch step {
        case .recommendation:
            break
        case .score:
            step = .recommendation
        case .putts:
            step = .score
        case .fairway:
            step = .putts
        case .penalty:
            step = par == 3 ? .putts : .fairway
        }
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
        var scorePayload: [String: JSONValue] = [
            "strokes": .number(Double(draft.score)),
            "source": .string("ios_score_confirmation"),
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
                    "source": .string("ios_score_confirmation"),
                ]
            ),
            LiveRoundEvent(
                eventId: makeEventId(), roundId: roundId, timestamp: timestamp,
                hole: draft.hole, kind: .penalty,
                payload: [
                    "penalties": .number(Double(draft.penalty)),
                    "source": .string("ios_score_confirmation"),
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
