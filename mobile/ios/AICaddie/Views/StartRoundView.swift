import SwiftUI

public struct StartRoundView: View {
    public let defaultRoundId: String
    public let courseOptions: [MobileCourseOption]
    public let syncStatus: String
    public let isPreparing: Bool
    public let apiBaseURL: URL?
    public let adminTokenConfigured: Bool
    public let onPrepareRound: (String) -> Void
    public let onPrepareCourseRound: (Int, String, String) -> Void
    public let onSaveBackendConfiguration: (String, String?) -> Void
    public let onClearBackendConfiguration: () -> Void

    @State private var roundId: String
    @State private var courseGlobalIdText: String
    @State private var teeBox: String

    public init(
        defaultRoundId: String = "900001",
        defaultCourseGlobalId: Int? = nil,
        defaultTeeBox: String = "unknown",
        courseOptions: [MobileCourseOption] = [],
        syncStatus: String = "Offline ready",
        isPreparing: Bool = false,
        apiBaseURL: URL? = nil,
        adminTokenConfigured: Bool = false,
        onPrepareRound: @escaping (String) -> Void = { _ in },
        onPrepareCourseRound: @escaping (Int, String, String) -> Void = { _, _, _ in },
        onSaveBackendConfiguration: @escaping (String, String?) -> Void = { _, _ in },
        onClearBackendConfiguration: @escaping () -> Void = {}
    ) {
        self.defaultRoundId = defaultRoundId
        self.courseOptions = courseOptions
        self.syncStatus = syncStatus
        self.isPreparing = isPreparing
        self.apiBaseURL = apiBaseURL
        self.adminTokenConfigured = adminTokenConfigured
        self.onPrepareRound = onPrepareRound
        self.onPrepareCourseRound = onPrepareCourseRound
        self.onSaveBackendConfiguration = onSaveBackendConfiguration
        self.onClearBackendConfiguration = onClearBackendConfiguration
        self._roundId = State(initialValue: defaultRoundId)
        self._courseGlobalIdText = State(initialValue: defaultCourseGlobalId.map(String.init) ?? "")
        self._teeBox = State(initialValue: defaultTeeBox)
    }

    public var body: some View {
        Form {
            Section("Connection") {
                NavigationLink {
                    BackendSettingsView(
                        apiBaseURL: apiBaseURL,
                        adminTokenConfigured: adminTokenConfigured,
                        syncStatus: syncStatus,
                        onSave: onSaveBackendConfiguration,
                        onClear: onClearBackendConfiguration
                    )
                } label: {
                    Label(apiBaseURL?.host ?? "Backend", systemImage: "server.rack")
                }
            }

            Section("Start Round") {
                if !courseOptions.isEmpty {
                    Picker("Recent course", selection: $courseGlobalIdText) {
                        Text("Manual course ID").tag("")
                        ForEach(courseOptions) { option in
                            Text("\(option.name) / \(option.holes) holes").tag(String(option.globalId))
                        }
                    }
                    .onChange(of: courseGlobalIdText) { _, nextValue in
                        applySelectedCourse(globalIdText: nextValue)
                    }
                }
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

    private func applySelectedCourse(globalIdText: String) {
        guard let globalId = Int(globalIdText),
              let option = courseOptions.first(where: { $0.globalId == globalId }) else {
            return
        }
        roundId = option.suggestedLiveRoundId ?? "live-\(option.globalId)"
        if let optionTeeBox = option.teeBox, optionTeeBox != "unknown" {
            teeBox = optionTeeBox
        }
    }
}
