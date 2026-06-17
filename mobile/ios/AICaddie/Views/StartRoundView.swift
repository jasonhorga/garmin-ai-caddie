import SwiftUI

/// 开始一场 — 选起始 9 洞 + 发球台,然后开始记分。
/// 「起始 9 洞」分段对接后端 course package 的 `nine=front|back` 过滤:先打 9 洞,
/// 开始后可在球局里随时加打另外 9 洞凑成 18(手滑加错也能撤)。手动 ID / 仅刷新离线包
/// 收进「手动设置」段,保留给调试与离线场景。
public struct StartRoundView: View {
    public let defaultRoundId: String
    public let courseOptions: [MobileCourseOption]
    public let syncStatus: String
    public let isPreparing: Bool
    public let apiBaseURL: URL?
    public let adminTokenConfigured: Bool
    public let onPrepareRound: (String) -> Void
    public let onPrepareCourseRound: (Int, String, String, String) -> Void
    public let onSaveBackendConfiguration: (String, String?) -> Void
    public let onClearBackendConfiguration: () -> Void

    @State private var roundId: String
    @State private var courseGlobalIdText: String
    @State private var teeBox: String
    @State private var nine: String

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
        onPrepareCourseRound: @escaping (Int, String, String, String) -> Void = { _, _, _, _ in },
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
        self._nine = State(initialValue: "front")
    }

    private var courseGlobalId: Int? {
        Int(courseGlobalIdText.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private var canStart: Bool {
        !isPreparing
            && !roundId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && courseGlobalId != nil
    }

    public var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                nineCard
                courseCard
                startCard
                manualCard
                connectionCard
            }
            .padding(14)
        }
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        .navigationTitle("开始一场")
    }

    private var nineCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("起始 9 洞").font(.caption).foregroundStyle(.secondary)
            Picker("起始 9 洞", selection: $nine) {
                Text("前九 (1–9)").tag("front")
                Text("后九 (10–18)").tag("back")
            }
            .pickerStyle(.segmented)
            Text("先打 9 洞即可。开始后在球局里随时「＋加打另外 9 洞」凑成 18;手滑加错也能一键撤销。")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .liveCard()
    }

    @ViewBuilder private var courseCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("选球场").font(.caption).foregroundStyle(.secondary)
            if !courseOptions.isEmpty {
                Picker("最近球场", selection: $courseGlobalIdText) {
                    Text("手动输入").tag("")
                    ForEach(courseOptions) { option in
                        Text("\(option.name) · \(option.holes) 洞").tag(String(option.globalId))
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: .infinity, alignment: .leading)
                .onChange(of: courseGlobalIdText) { _, nextValue in
                    applySelectedCourse(globalIdText: nextValue)
                }
            }
            TextField("发球台 Tee", text: $teeBox)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textFieldStyle(.roundedBorder)
        }
        .liveCard()
    }

    private var startCard: some View {
        VStack(spacing: 8) {
            Button {
                if let courseGlobalId {
                    onPrepareCourseRound(courseGlobalId, roundId, teeBox, nine)
                }
            } label: {
                Label("开始记分", systemImage: "flag.checkered")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(canStart ? LiveHoleStyle.green : Color.gray.opacity(0.4))
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
            .disabled(!canStart)
            Text(syncStatus)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var manualCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("手动设置").font(.caption).foregroundStyle(.secondary)
            TextField("球局 ID", text: $roundId)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textFieldStyle(.roundedBorder)
            TextField("球场 ID", text: $courseGlobalIdText)
                .keyboardType(.numberPad)
                .textFieldStyle(.roundedBorder)
            Button {
                onPrepareRound(roundId)
            } label: {
                Label("仅刷新离线包", systemImage: "arrow.down.circle")
            }
            .buttonStyle(.plain)
            .foregroundStyle(LiveHoleStyle.green)
            .disabled(isPreparing || roundId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .liveCard()
    }

    private var connectionCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("连接").font(.caption).foregroundStyle(.secondary)
            NavigationLink {
                BackendSettingsView(
                    apiBaseURL: apiBaseURL,
                    adminTokenConfigured: adminTokenConfigured,
                    syncStatus: syncStatus,
                    onSave: onSaveBackendConfiguration,
                    onClear: onClearBackendConfiguration
                )
            } label: {
                HStack {
                    Label(apiBaseURL?.host ?? "后端", systemImage: "server.rack")
                    Spacer()
                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
                }
                .foregroundStyle(.primary)
            }
            .buttonStyle(.plain)
        }
        .liveCard()
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
