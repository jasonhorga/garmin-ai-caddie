import SwiftUI

public struct StartRoundView: View {
    public let defaultRoundId: String
    public let syncStatus: String
    public let isPreparing: Bool
    public let onPrepareRound: (String) -> Void
    public let onPrepareCourseRound: (Int, String, String) -> Void

    @State private var roundId: String
    @State private var courseGlobalIdText: String
    @State private var teeBox: String

    public init(
        defaultRoundId: String = "900001",
        defaultCourseGlobalId: Int? = nil,
        defaultTeeBox: String = "unknown",
        syncStatus: String = "Offline ready",
        isPreparing: Bool = false,
        onPrepareRound: @escaping (String) -> Void = { _ in },
        onPrepareCourseRound: @escaping (Int, String, String) -> Void = { _, _, _ in }
    ) {
        self.defaultRoundId = defaultRoundId
        self.syncStatus = syncStatus
        self.isPreparing = isPreparing
        self.onPrepareRound = onPrepareRound
        self.onPrepareCourseRound = onPrepareCourseRound
        self._roundId = State(initialValue: defaultRoundId)
        self._courseGlobalIdText = State(initialValue: defaultCourseGlobalId.map(String.init) ?? "")
        self._teeBox = State(initialValue: defaultTeeBox)
    }

    public var body: some View {
        Form {
            Section("Start Round") {
                TextField("Round ID", text: $roundId)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                TextField("Course global ID", text: $courseGlobalIdText)
                    .keyboardType(.numberPad)
                TextField("Tee box", text: $teeBox)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button {
                    if let courseGlobalId = Int(courseGlobalIdText.trimmingCharacters(in: .whitespacesAndNewlines)) {
                        onPrepareCourseRound(courseGlobalId, roundId, teeBox)
                    }
                } label: {
                    Label("Prepare course package", systemImage: "flag")
                }
                .disabled(isPreparing || roundId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || Int(courseGlobalIdText.trimmingCharacters(in: .whitespacesAndNewlines)) == nil)
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
