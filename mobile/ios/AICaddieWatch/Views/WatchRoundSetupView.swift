import SwiftUI

/// The last explicit gate before a real Watch round starts: choose the playable loop(s) and tee.
/// It intentionally has no synthetic score-only fallback; unavailable data stays unavailable.
public struct WatchRoundSetupView: View {
    public let front: WatchCourseOption
    public let courses: [WatchCourseOption]
    public let hasCachedVersion: Bool
    public let isPreparing: Bool
    public let errorMessage: String?
    public let ensureGeometry: Bool
    public let onLoadTees: (Int) async -> [WatchCourseTee]
    public let onStart: (WatchCourseSelection) -> Void

    @State private var selectedTee: String
    @State private var selectedBackGlobalId: Int?
    @State private var loadedTees: [WatchCourseTee] = []
    @State private var isLoadingTees = false
    @State private var teeLoadAttempted = false

    public init(
        front: WatchCourseOption,
        courses: [WatchCourseOption],
        hasCachedVersion: Bool = false,
        isPreparing: Bool = false,
        errorMessage: String? = nil,
        ensureGeometry: Bool = false,
        onLoadTees: @escaping (Int) async -> [WatchCourseTee] = { _ in [] },
        onStart: @escaping (WatchCourseSelection) -> Void = { _ in }
    ) {
        self.front = front
        self.courses = courses
        self.hasCachedVersion = hasCachedVersion
        self.isPreparing = isPreparing
        self.errorMessage = errorMessage
        self.ensureGeometry = ensureGeometry
        self.onLoadTees = onLoadTees
        self.onStart = onStart
        _selectedTee = State(initialValue: front.preferredTee)
        _selectedBackGlobalId = State(initialValue: nil)
    }

    public var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 3) {
                    Text(front.displayName)
                        .font(.headline)
                    Text(selectionSummary)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            if !backOptions.isEmpty {
                Section("洞组") {
                    choiceRow(
                        title: "只打 \(loopName(front)) · \(front.playableHoleCount) 洞",
                        selected: selectedBackGlobalId == nil
                    ) {
                        selectedBackGlobalId = nil
                    }
                    ForEach(backOptions) { option in
                        choiceRow(
                            title: "\(loopName(front)) + \(loopName(option)) · 18 洞",
                            selected: selectedBackGlobalId == option.globalId
                        ) {
                            selectedBackGlobalId = option.globalId
                        }
                    }
                }
            }

            Section("发球台") {
                if isLoadingTees {
                    ProgressView("正在获取发球台")
                } else if teeOptions.isEmpty {
                    Text("暂无可用发球台")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(teeOptions) { tee in
                        choiceRow(
                            title: teeLabel(tee),
                            selected: tee.teeBox.caseInsensitiveCompare(selectedTee) == .orderedSame
                        ) {
                            selectedTee = tee.teeBox
                        }
                    }
                }
            }

            Section {
                Button {
                    onStart(WatchCourseSelection(
                        front: configuredFront,
                        back: selectedBack,
                        teeBox: selectedTee,
                        ensureGeometry: ensureGeometry
                    ))
                } label: {
                    HStack {
                        if isPreparing {
                            ProgressView()
                                .controlSize(.small)
                        }
                        Text(isPreparing ? "正在准备" : "准备并开始")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                }
                .disabled(isPreparing || isLoadingTees || teeOptions.isEmpty)
            } footer: {
                if hasCachedVersion {
                    Text("已有离线版本；更换洞组或发球台时需要联网更新。")
                } else if teeLoadAttempted, teeOptions.isEmpty, !isLoadingTees {
                    Text("无法取得真实发球台时不会用猜测值开局。")
                }
            }

            if let errorMessage {
                Section {
                    Text(errorMessage)
                        .font(.caption2)
                        .foregroundStyle(.orange)
                }
            }
        }
        .navigationTitle("开局设置")
        .task(id: front.globalId) {
            await loadTeesIfNeeded()
        }
    }

    @ViewBuilder
    private func choiceRow(title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(selected ? AICaddieDesignTokens.par : .secondary)
                Text(title)
                    .foregroundStyle(.primary)
                Spacer(minLength: 0)
            }
        }
        .accessibilityValue(selected ? "已选择" : "未选择")
    }

    private var selectedBack: WatchCourseOption? {
        guard let selectedBackGlobalId else { return nil }
        return backOptions.first { $0.globalId == selectedBackGlobalId }
    }

    private var backOptions: [WatchCourseOption] {
        guard front.playableHoleCount == 9 else { return [] }
        return courses
            .filter {
                $0.globalId != front.globalId
                    && $0.playableHoleCount == 9
                    && venueName($0) == venueName(front)
            }
            .sorted { loopName($0).localizedStandardCompare(loopName($1)) == .orderedAscending }
    }

    private var teeOptions: [WatchCourseTee] {
        if !loadedTees.isEmpty { return loadedTees }

        var seen = Set<String>()
        var result: [WatchCourseTee] = []
        let defaultTee = front.teeBox?.trimmingCharacters(in: .whitespacesAndNewlines)
        for value in front.tees + [defaultTee].compactMap({ $0 }) {
            let tee = value.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !tee.isEmpty,
                  tee.caseInsensitiveCompare("unknown") != .orderedSame,
                  seen.insert(tee.lowercased()).inserted else { continue }
            result.append(WatchCourseTee(
                teeBox: tee,
                name: tee,
                isDefault: defaultTee?.caseInsensitiveCompare(tee) == .orderedSame
            ))
        }
        return result
    }

    private var configuredFront: WatchCourseOption {
        teeOptions.isEmpty ? front : front.withTees(teeOptions, selectedTee: selectedTee)
    }

    private var selectionSummary: String {
        let teeSummary = teeOptions.isEmpty ? "发球台待加载" : selectedTeeSummary
        if let selectedBack {
            return "\(loopName(front)) + \(loopName(selectedBack)) · \(teeSummary) · 18 洞"
        }
        return "\(loopName(front)) · \(teeSummary) · \(front.playableHoleCount) 洞"
    }

    private var selectedTeeSummary: String {
        guard let tee = teeOptions.first(where: {
            $0.teeBox.caseInsensitiveCompare(selectedTee) == .orderedSame
        }) else {
            return "\(selectedTee.capitalized) T"
        }
        let code = tee.teeBox.trimmingCharacters(in: .whitespacesAndNewlines)
        let name = tee.name.trimmingCharacters(in: .whitespacesAndNewlines)
        let canonicalNames = [code.lowercased(), "\(code.lowercased()) tee"]
        if !name.isEmpty, !canonicalNames.contains(name.lowercased()) {
            return name.hasSuffix("台") ? name : "\(name) T"
        }
        return "\(code.capitalized) T"
    }

    private func venueName(_ option: WatchCourseOption) -> String {
        option.venueName
            ?? option.name.components(separatedBy: " ~ ").first
            ?? option.name
    }

    private func loopName(_ option: WatchCourseOption) -> String {
        if let label = option.segmentLabel, !label.isEmpty { return label }
        return option.playableHoleCount == 18 ? "全场" : option.displayName
    }

    private func teeLabel(_ tee: WatchCourseTee) -> String {
        let label = switch tee.teeBox.lowercased() {
        case "blue": "蓝 T"
        case "white": "白 T"
        case "red": "红 T"
        case "gold": "金 T"
        case "black", "championship", "tips": "黑 T"
        case "green": "绿 T"
        case "yellow": "黄 T"
        case "silver": "银 T"
        default: "\(tee.name) T"
        }
        return tee.yards.map { "\(label) · \($0) 码" } ?? label
    }

    @MainActor
    private func loadTeesIfNeeded() async {
        guard front.tees.isEmpty else { return }
        if let teeBox = front.teeBox?.trimmingCharacters(in: .whitespacesAndNewlines),
           !teeBox.isEmpty,
           teeBox.caseInsensitiveCompare("unknown") != .orderedSame {
            return
        }

        teeLoadAttempted = true
        isLoadingTees = true
        let tees = await onLoadTees(front.globalId)
        isLoadingTees = false
        loadedTees = tees
        if let defaultTee = tees.first(where: \.isDefault) ?? tees.first {
            selectedTee = defaultTee.teeBox
        }
    }
}
