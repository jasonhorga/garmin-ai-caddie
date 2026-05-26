import SwiftUI

public struct CurrentHoleView: View {
    public let package: LiveRoundPackage
    public let hole: Hole
    public let onEvent: (LiveRoundEvent) -> Void
    private let requestBuilder = CaddieDecisionRequestBuilder()

    @State private var score: Int
    @State private var puttCount: Int = 2
    @State private var penaltyCount: Int = 0
    @State private var selectedClub: String
    @State private var note: String = ""

    public init(package: LiveRoundPackage, hole: Hole, onEvent: @escaping (LiveRoundEvent) -> Void = { _ in }) {
        self.package = package
        self.hole = hole
        self.onEvent = onEvent
        self._score = State(initialValue: hole.par)
        self._selectedClub = State(initialValue: package.clubProfiles.first?.clubName ?? "")
    }

    public var body: some View {
        Form {
            Section {
                HStack {
                    Text("Hole \(hole.number)")
                        .font(.title3.weight(.semibold))
                    Spacer()
                    Text("Par \(hole.par)")
                        .foregroundStyle(.secondary)
                }
                CaddiePlanView(
                    options: CaddiePlanOption.defaultOptions,
                    selectedOptionId: "stock"
                )
            }

            Section("Input") {
                Stepper("Score \(score)", value: $score, in: 1...12)
                Stepper("Putts \(puttCount)", value: $puttCount, in: 0...6)
                Stepper("Penalty \(penaltyCount)", value: $penaltyCount, in: 0...4)
                Picker("Club", selection: $selectedClub) {
                    ForEach(package.clubProfiles) { club in
                        Text(club.clubName).tag(club.clubName)
                    }
                }
                TextField("Note", text: $note)
                Button {
                    submitEvents()
                } label: {
                    Label("Save", systemImage: "checkmark.circle")
                }
            }
        }
        .navigationTitle("Hole \(hole.number)")
    }

    private var caddieContextSeed: CaddieContextSeed? {
        package.caddieContextSeeds.first { $0.hole == hole.number }
    }

    private func makeCaddieDecisionRequest() -> CaddieDecisionRequest? {
        guard let caddieContextSeed else {
            return nil
        }
        return requestBuilder.makeDecisionRequest(
            seed: caddieContextSeed,
            input: LiveCaddieInput(
                shotType: "approach",
                lie: "fairway"
            )
        )
    }

    private func submitEvents() {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        emit(kind: .score, timestamp: timestamp, payload: ["strokes": .number(Double(score))])
        emit(kind: .putt, timestamp: timestamp, payload: ["count": .number(Double(puttCount))])
        emit(kind: .penalty, timestamp: timestamp, payload: ["count": .number(Double(penaltyCount))])
        emit(kind: .club, timestamp: timestamp, payload: ["clubName": .string(selectedClub)])
        if !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            emit(kind: .note, timestamp: timestamp, payload: ["text": .string(note)])
        }
    }

    private func emit(kind: LiveRoundEventKind, timestamp: String, payload: [String: JSONValue]) {
        onEvent(
            LiveRoundEvent(
                eventId: UUID().uuidString,
                roundId: package.roundId,
                timestamp: timestamp,
                hole: hole.number,
                kind: kind,
                payload: payload
            )
        )
    }
}
