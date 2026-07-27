import SwiftUI

/// The last explicit gate before a real Watch round starts: choose the playable loop(s) and tee.
/// It intentionally has no synthetic score-only fallback; unavailable data stays unavailable.
public struct WatchRoundSetupView: View {
    public let front: WatchCourseOption
    public let courses: [WatchCourseOption]
    public let hasCachedVersion: Bool
    public let isPreparing: Bool
    public let errorMessage: String?
    public let onStart: (WatchCourseSelection) -> Void

    @State private var selectedTee: String
    @State private var selectedBackGlobalId: Int?

    public init(
        front: WatchCourseOption,
        courses: [WatchCourseOption],
        hasCachedVersion: Bool = false,
        isPreparing: Bool = false,
        errorMessage: String? = nil,
        onStart: @escaping (WatchCourseSelection) -> Void = { _ in }
    ) {
        self.front = front
        self.courses = courses
        self.hasCachedVersion = hasCachedVersion
        self.isPreparing = isPreparing
        self.errorMessage = errorMessage
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
                        title: "只打 (loopName(front)) · (front.playableHoleCount) 洞",
                        selected: selectedBackGlobalId == nil
                    ) {
                        selectedBackGlobalId = nil
                    }
                    ForEach(backOptions) { option in
                        choiceRow(
                            title: "(loopName(front)) + (loopName(option)) · 18 洞",
                            selected: selectedBackGlobalId == option.globalId
                        ) {
                            selectedBackGlobalId = option.globalId
                        }
                    }
                }
            }

            Section("发球台") {
                ForEach(teeOptions, id: \.self) { tee in
                    choiceRow(
                        title: teeLabel(tee),
                        selected: tee.caseInsensitiveCompare(selectedTee) == .orderedSame
                    ) {
                        selectedTee = tee
                    }
                }
            }

            Section {
                Button {
                    onStart(WatchCourseSelection(front: front, back: selectedBack, teeBox: selectedTee))
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
                .disabled(isPreparing)
            } footer: {
                if hasCachedVersion {
                    Text("已有离线版本；更换洞组或发球台时需要联网更新。")
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
            .filter { $0.playableHoleCount == 9 && venueName($0) == venueName(front) }
            .sorted { loopName($0).localizedStandardCompare(loopName($1)) == .orderedAscending }
    }

    private var teeOptions: [String] {
        var seen = Set<String>()
        var result: [String] = []
        for value in front.tees + [front.preferredTee] {
            let tee = value.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !tee.isEmpty, seen.insert(tee.lowercased()).inserted else { continue }
            result.append(tee)
        }
        return result
    }

    private var selectionSummary: String {
        if let selectedBack {
            return "(loopName(front)) + (loopName(selectedBack)) · (selectedTee) T · 18 洞"
        }
        return "(loopName(front)) · (selectedTee) T · (front.playableHoleCount) 洞"
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

    private func teeLabel(_ tee: String) -> String {
        switch tee.lowercased() {
        case "blue": "蓝 T"
        case "white": "白 T"
        case "red": "红 T"
        case "gold": "金 T"
        case "black", "championship", "tips": "黑 T"
        case "green": "绿 T"
        case "yellow": "黄 T"
        case "silver": "银 T"
        default: "(tee) T"
        }
    }
}
