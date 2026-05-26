import SwiftUI

public struct StartRoundView: View {
    public let defaultRoundId: String
    public let syncStatus: String
    public let isPreparing: Bool
    public let onPrepareRound: (String) -> Void

    @State private var roundId: String

    public init(
        defaultRoundId: String = "900001",
        syncStatus: String = "Offline ready",
        isPreparing: Bool = false,
        onPrepareRound: @escaping (String) -> Void = { _ in }
    ) {
        self.defaultRoundId = defaultRoundId
        self.syncStatus = syncStatus
        self.isPreparing = isPreparing
        self.onPrepareRound = onPrepareRound
        self._roundId = State(initialValue: defaultRoundId)
    }

    public var body: some View {
        Form {
            Section("Start Round") {
                TextField("Round ID", text: $roundId)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button {
                    onPrepareRound(roundId)
                } label: {
                    Label("Prepare offline package", systemImage: "arrow.down.circle")
                }
                .disabled(isPreparing || roundId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Text(syncStatus)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Start Round")
    }
}
