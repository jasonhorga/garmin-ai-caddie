import Foundation
import SwiftUI

public struct CurrentHoleView: View {
    public let package: LiveRoundPackage
    public let hole: Hole
    public let onEvent: (LiveRoundEvent) -> Void
    private let requestBuilder = CaddieDecisionRequestBuilder()
    private let caddieClient: CaddieDecisionClient?

    @State private var score: Int
    @State private var puttCount: Int = 2
    @State private var penaltyCount: Int = 0
    @State private var selectedClub: String
    @State private var note: String = ""
    @State private var caddieDecision: CaddieDecisionResponse?
    @State private var isLoadingCaddieDecision = false
    @State private var caddieErrorMessage: String?

    public init(
        package: LiveRoundPackage,
        hole: Hole,
        caddieBaseURL: URL? = nil,
        caddieClient: CaddieDecisionClient? = nil,
        onEvent: @escaping (LiveRoundEvent) -> Void = { _ in }
    ) {
        self.package = package
        self.hole = hole
        self.onEvent = onEvent
        self.caddieClient = caddieClient ?? caddieBaseURL.map { CaddieDecisionClient(baseURL: $0) }
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
                if let caddieDecision {
                    CaddiePlanView(response: caddieDecision)
                } else {
                    CaddiePlanView(
                        options: CaddiePlanOption.defaultOptions,
                        selectedOptionId: "stock"
                    )
                }
                if isLoadingCaddieDecision {
                    ProgressView("Updating caddie")
                }
                if let caddieErrorMessage {
                    Text(caddieErrorMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Button {
                    Task {
                        await loadCaddieDecision()
                    }
                } label: {
                    Label("Refresh caddie", systemImage: "arrow.clockwise")
                }
                .disabled(isLoadingCaddieDecision)
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
        .task(id: hole.number) {
            await loadCaddieDecision()
        }
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

    @MainActor
    private func loadCaddieDecision() async {
        guard let caddieClient else {
            caddieErrorMessage = "Offline package ready. Connect to refresh caddie decision."
            return
        }
        guard let request = makeCaddieDecisionRequest() else {
            caddieErrorMessage = "No caddie context seed for this hole."
            return
        }

        isLoadingCaddieDecision = true
        defer {
            isLoadingCaddieDecision = false
        }

        do {
            caddieDecision = try await caddieClient.fetchCaddieDecision(request, endpoint: package.caddieDecisionEndpoint)
            caddieErrorMessage = nil
        } catch {
            caddieErrorMessage = "Caddie decision unavailable. Cached plan remains visible."
        }
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
