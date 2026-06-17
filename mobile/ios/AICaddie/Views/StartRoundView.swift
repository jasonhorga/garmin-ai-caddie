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

    @Environment(\.dismiss) private var dismiss
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
        // The chosen segment (a 9-hole loop, or a whole 18) IS the unit now → no front/back slice.
        self._nine = State(initialValue: "all")
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
                courseCard
                startCard
            }
            .padding(14)
        }
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        .navigationTitle("开始一场")
    }

    /// 按真实结构选场:每个球场列出它的各 9 洞环(黑骑士 A/B/C)或整场(北湖 18);选一个开始。
    @ViewBuilder private var courseCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("选择球场").font(.caption).foregroundStyle(.secondary)
            if venueGroups.isEmpty {
                Text("暂无球场,先在设置里同步 Garmin 球局。").font(.subheadline).foregroundStyle(.secondary)
            }
            ForEach(venueGroups, id: \.venue) { group in
                VStack(alignment: .leading, spacing: 6) {
                    Text(group.venue).font(.subheadline.weight(.bold))
                    ForEach(group.segments) { segment in
                        segmentRow(segment)
                    }
                }
            }
            Text("先选一个 9 洞开始;「加打另一个 9 洞凑 18」稍后更新。")
                .font(.caption2)
                .foregroundStyle(.secondary)
            Divider().padding(.vertical, 2)
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

    /// 单个可打段(9 洞环 / 整场)的可选行;选中绿描边高亮。
    @ViewBuilder private func segmentRow(_ segment: MobileCourseOption) -> some View {
        let selected = String(segment.globalId) == courseGlobalIdText
        Button {
            courseGlobalIdText = String(segment.globalId)
            applySelectedCourse(globalIdText: courseGlobalIdText)
        } label: {
            HStack(spacing: 10) {
                Image(systemName: selected ? "largecircle.fill.circle" : "circle")
                    .foregroundStyle(selected ? LiveHoleStyle.green : .secondary)
                Text(segmentTitle(segment))
                    .font(.subheadline.weight(selected ? .semibold : .regular))
                    .foregroundStyle(.primary)
                Spacer()
                Text(segmentHolesText(segment))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            .padding(.vertical, 8)
            .padding(.horizontal, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(selected ? LiveHoleStyle.green.opacity(0.10) : Color.clear)
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(selected ? LiveHoleStyle.green : LiveHoleStyle.line))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
    }

    private func segmentTitle(_ segment: MobileCourseOption) -> String {
        if let label = segment.segmentLabel, !label.isEmpty {
            return "\(label) 场"
        }
        return "全场"
    }

    private func segmentHolesText(_ segment: MobileCourseOption) -> String {
        "\(segment.segmentHoles ?? segment.holes) 洞"
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
                    // Pop back to the Hub; it now shows this round's 进行中 card (继续这场).
                    // When 开始一场 is the root fallback (no package), dismiss is a safe no-op
                    // and the model's new package swaps the root to the Hub.
                    dismiss()
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

    /// Group options by venue → each venue lists its playable segments (9-hole loops A/B/C, or a
    /// whole 18). Loops sorted by label (A/B/C…), single course last; venues by most-played first.
    private var venueGroups: [(venue: String, segments: [MobileCourseOption])] {
        var byVenue: [String: [MobileCourseOption]] = [:]
        for option in courseOptions {
            let venue = option.venueName ?? baseCourseName(option.name)
            byVenue[venue, default: []].append(option)
        }
        return byVenue
            .map { entry in
                (venue: entry.key, segments: entry.value.sorted { segmentSortKey($0) < segmentSortKey($1) })
            }
            .sorted { ($0.segments.map(\.roundCount).max() ?? 0) > ($1.segments.map(\.roundCount).max() ?? 0) }
    }

    private func segmentSortKey(_ segment: MobileCourseOption) -> String {
        // Labelled loops first (A < B < C), a single whole course (nil label) last.
        segment.segmentLabel ?? "~~"
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
