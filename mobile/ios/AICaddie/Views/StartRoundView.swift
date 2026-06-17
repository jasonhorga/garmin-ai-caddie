import SwiftUI

/// 开始一场 — 选起始 9 洞 + 球场,直接开始记分。
/// 默认自动选中第一个真实球场(发球台随之带出),所以「开始记分」开箱即用。
/// 手动 ID / 仅刷新离线包 / 后端连接等工程项收进折叠的「高级设置」,默认不打扰。
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
        // Pre-select a real course (the given default, else the most-played) so the
        // primary action works out of the box instead of stranding on "manual entry".
        let mostPlayed = courseOptions.max { $0.roundCount < $1.roundCount }
        let resolvedCourseId = defaultCourseGlobalId.map(String.init)
            ?? mostPlayed.map { String($0.globalId) }
            ?? ""
        let selected = courseOptions.first { String($0.globalId) == resolvedCourseId }
        self._courseGlobalIdText = State(initialValue: resolvedCourseId)
        self._roundId = State(initialValue: selected?.suggestedLiveRoundId ?? defaultRoundId)
        let resolvedTee = selected?.teeBox.flatMap { $0 == "unknown" ? nil : $0 }
            ?? (defaultTeeBox == "unknown" ? "" : defaultTeeBox)
        self._teeBox = State(initialValue: resolvedTee)
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
        VStack(alignment: .leading, spacing: 12) {
            Text("球场").font(.caption).foregroundStyle(.secondary)
            if !displayedCourses.isEmpty {
                Picker("最近球场", selection: $courseGlobalIdText) {
                    ForEach(displayedCourses) { option in
                        Text(baseCourseName(option.name)).tag(String(option.globalId))
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: .infinity, alignment: .leading)
                .onChange(of: courseGlobalIdText) { _, nextValue in
                    applySelectedCourse(globalIdText: nextValue)
                }
            }
            HStack(spacing: 8) {
                Text("发球台").font(.subheadline).foregroundStyle(.secondary)
                Spacer()
                Menu {
                    ForEach(teeOptions, id: \.self) { tee in
                        Button(zhTeeLabel(tee)) { teeBox = tee }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text(teeBox.isEmpty ? "默认" : zhTeeLabel(teeBox))
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(LiveHoleStyle.green)
                        Image(systemName: "chevron.up.chevron.down").font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .liveCard()
    }

    /// 发球台:内部保留 Garmin 原始 key(传给后端),仅显示中文。当前球场的发球台并入选项。
    private var teeOptions: [String] {
        var seen = Set<String>()
        var result: [String] = []
        for tee in [teeBox, "blue", "white", "red", "gold", "black", "green", "yellow", "silver"] {
            let trimmed = tee.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty, seen.insert(trimmed.lowercased()).inserted else { continue }
            result.append(trimmed)
        }
        return result
    }

    private func zhTeeLabel(_ tee: String) -> String {
        switch tee.lowercased() {
        case "blue":
            return "蓝 T"
        case "white":
            return "白 T"
        case "red":
            return "红 T"
        case "gold":
            return "金 T"
        case "black", "championship", "tips":
            return "黑 T(锦标)"
        case "green":
            return "绿 T"
        case "yellow":
            return "黄 T"
        case "silver":
            return "银 T"
        default:
            return tee
        }
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
            if isPreparing {
                ProgressView("准备中…").font(.caption)
            }
        }
    }

    /// One row per overall course (drop the " ~ A/B/C" nine suffix), most-played first.
    /// The specific nine is resolved later from the round / Garmin data, not chosen here.
    private var displayedCourses: [MobileCourseOption] {
        var bestByName: [String: MobileCourseOption] = [:]
        for option in courseOptions {
            let key = baseCourseName(option.name)
            if let existing = bestByName[key], existing.roundCount >= option.roundCount {
                continue
            }
            bestByName[key] = option
        }
        return bestByName.values.sorted { $0.roundCount > $1.roundCount }
    }

    private func baseCourseName(_ name: String) -> String {
        name.components(separatedBy: " ~ ").first?.trimmingCharacters(in: .whitespaces) ?? name
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
