import SwiftUI

public struct WatchInputView: View {
    public let state: WatchRoundState
    public let clubs: [String]
    public let onEvent: (WatchInputEvent) -> Void

    @State private var score: Int
    @State private var putts: Int
    @State private var penaltyCount: Int
    @State private var selectedClub: String
    @State private var distanceYd: Int
    @State private var scoreDirty = false
    @State private var puttsDirty = false
    @State private var clubDirty = false
    @State private var distanceDirty = false
    @State private var fairway = ""          // "" | left | center | right | miss (上球道问法)
    @State private var fairwayDirty = false

    public init(state: WatchRoundState, clubs: [String], onEvent: @escaping (WatchInputEvent) -> Void = { _ in }) {
        self.state = state
        self.clubs = clubs.isEmpty ? state.availableClubNames : clubs
        self.onEvent = onEvent
        self._score = State(initialValue: state.score)
        self._putts = State(initialValue: state.putts)
        self._penaltyCount = State(initialValue: state.penaltyCount)
        let availableClubs = clubs.isEmpty ? state.availableClubNames : clubs
        self._selectedClub = State(initialValue: state.selectedClub ?? state.suggestedClub ?? availableClubs.first ?? "")
        self._distanceYd = State(initialValue: WatchUnits.yards(state.distanceM ?? 0))
    }

    public var body: some View {
        Form {
            Stepper("距 \(distanceYd) 码", value: $distanceYd, in: 0...350, step: 5)
            Stepper("杆 \(score)", value: $score, in: 1...12)
            Stepper("推 \(putts)", value: $putts, in: 0...6)
            Button {
                penaltyCount += 1
                emit(kind: .penalty, value: "\(penaltyCount)")
            } label: {
                Label("罚 \(penaltyCount)", systemImage: "plus.circle")
            }
            Picker("球杆", selection: $selectedClub) {
                ForEach(inputClubs, id: \.self) { club in
                    Text(club).tag(club)
                }
            }
            .disabled(inputClubs.isEmpty)
            Picker("上球道", selection: $fairway) {
                Text("—").tag("")
                Text("左").tag("left")
                Text("中").tag("center")
                Text("右").tag("right")
                Text("没上").tag("miss")
            }
            Button("保存") {
                if distanceDirty && hasClubContext {
                    // 显示/输入是码,但事件/状态(distanceM)与 Garmin 一致仍是米 → 边界换算回米。
                    emit(kind: .distance, value: "\(Int(WatchUnits.metres(fromYards: distanceYd).rounded()))")
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
                if fairwayDirty && !fairway.isEmpty {
                    emit(kind: .fairway, value: fairway)
                }
                distanceDirty = false
                scoreDirty = false
                puttsDirty = false
                clubDirty = false
                fairwayDirty = false
            }
        }
        .navigationTitle("输入")
        .onChange(of: fairway) { _, _ in
            fairwayDirty = true
        }
        .onChange(of: distanceYd) { _, _ in
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
                distanceToPinM: WatchUnits.metres(fromYards: distanceYd),
                offlineOptionId: state.offlineOptionId,
                decisionId: state.decisionId
            )
        )
    }
}
