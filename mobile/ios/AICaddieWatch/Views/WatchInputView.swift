import SwiftUI

public struct WatchInputView: View {
    public let state: WatchRoundState
    public let clubs: [String]
    public let onEvent: (WatchInputEvent) -> Void

    @State private var score: Int
    @State private var putts: Int
    @State private var penaltyCount: Int
    @State private var selectedClub: String
    @State private var distanceM: Int
    @State private var scoreDirty = false
    @State private var puttsDirty = false
    @State private var clubDirty = false
    @State private var distanceDirty = false

    public init(state: WatchRoundState, clubs: [String], onEvent: @escaping (WatchInputEvent) -> Void = { _ in }) {
        self.state = state
        self.clubs = clubs.isEmpty ? state.availableClubNames : clubs
        self.onEvent = onEvent
        self._score = State(initialValue: state.score)
        self._putts = State(initialValue: state.putts)
        self._penaltyCount = State(initialValue: state.penaltyCount)
        let availableClubs = clubs.isEmpty ? state.availableClubNames : clubs
        self._selectedClub = State(initialValue: state.selectedClub ?? state.suggestedClub ?? availableClubs.first ?? "")
        self._distanceM = State(initialValue: Int(state.distanceM ?? 0))
    }

    public var body: some View {
        Form {
            Stepper("D \(distanceM)m", value: $distanceM, in: 0...320, step: 5)
            Stepper("S \(score)", value: $score, in: 1...12)
            Stepper("P \(putts)", value: $putts, in: 0...6)
            Button {
                penaltyCount += 1
                emit(kind: .penalty, value: "\(penaltyCount)")
            } label: {
                Label("Pen \(penaltyCount)", systemImage: "plus.circle")
            }
            Picker("Club", selection: $selectedClub) {
                ForEach(inputClubs, id: \.self) { club in
                    Text(club).tag(club)
                }
            }
            .disabled(inputClubs.isEmpty)
            Button("Save") {
                if distanceDirty && hasClubContext {
                    emit(kind: .distance, value: "\(distanceM)")
                }
                if scoreDirty {
                    emit(kind: .score, value: "\(score)")
                }
                if puttsDirty {
                    emit(kind: .putt, value: "\(putts)")
                }
                if clubDirty && hasClubContext {
                    emit(kind: .club, value: selectedClub)
                }
                distanceDirty = false
                scoreDirty = false
                puttsDirty = false
                clubDirty = false
            }
        }
        .navigationTitle("Input")
        .onChange(of: distanceM) { _, _ in
            distanceDirty = true
        }
        .onChange(of: score) { _, _ in
            scoreDirty = true
        }
        .onChange(of: putts) { _, _ in
            puttsDirty = true
        }
        .onChange(of: selectedClub) { _, _ in
            clubDirty = true
        }
    }

    private var inputClubs: [String] {
        clubs.isEmpty ? state.availableClubNames : clubs
    }

    private var hasClubContext: Bool {
        !selectedClub.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func emit(kind: WatchInputKind, value: String) {
        onEvent(
            WatchInputEvent(
                eventId: UUID().uuidString,
                roundId: state.roundId,
                hole: state.hole,
                kind: kind,
                value: value,
                createdAt: ISO8601DateFormatter().string(from: Date()),
                contextClub: hasClubContext ? selectedClub : nil,
                shotType: state.shotType,
                strategyMode: state.strategyMode,
                lie: state.lie,
                distanceToPinM: Double(distanceM),
                offlineOptionId: state.offlineOptionId,
                decisionId: state.decisionId
            )
        )
    }
}
