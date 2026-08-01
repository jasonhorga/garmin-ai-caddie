import SwiftUI

struct WatchRoundSetupChoicePresentation: Equatable, Identifiable {
    let id: String
    let title: String
    let detail: String
    let isSelected: Bool
}

enum WatchRoundSetupStage: Equatable {
    case holes
    case tees
}

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
    @State private var stage: WatchRoundSetupStage
    let initialStage: WatchRoundSetupStage

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
        let startsWithHoles = Self.hasCompatibleBackLoop(front: front, courses: courses)
        let initialStage: WatchRoundSetupStage = startsWithHoles ? .holes : .tees
        self.initialStage = initialStage
        _stage = State(initialValue: initialStage)
    }

    public var body: some View {
        Group {
            if stage == .holes {
                holeSelection
            } else {
                teeSelection
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .task(id: front.globalId) {
            await loadTeesIfNeeded()
        }
    }

    private var holeSelection: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 7) {
                Text("打几洞")
                    .font(.system(size: 16, weight: .bold))
                    .padding(.horizontal, 2)

                ForEach(loopChoices) { choice in
                    Button {
                        selectedBackGlobalId = backOptions.first {
                            choice.id == "loop:\($0.globalId)"
                        }?.globalId
                        withAnimation(.easeOut(duration: 0.16)) { stage = .tees }
                    } label: {
                        HStack(spacing: 7) {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(choice.title)
                                    .font(.system(size: 14, weight: .semibold))
                                Text(choice.detail)
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundStyle(.secondary)
                            }
                            Spacer(minLength: 2)
                            Image(systemName: "chevron.forward")
                                .font(.system(size: 9, weight: .bold))
                                .foregroundStyle(.secondary)
                        }
                        .padding(.horizontal, 10)
                        .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(Color.white.opacity(0.07))
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 8)
            .padding(.top, 8)
        }
        .scrollIndicators(.hidden)
    }

    private var teeSelection: some View {
        VStack(spacing: 5) {
            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 6) {
                        if initialStage == .holes {
                            Button {
                                withAnimation(.easeOut(duration: 0.16)) { stage = .holes }
                            } label: {
                                Image(systemName: "chevron.backward")
                                    .font(.system(size: 12, weight: .bold))
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("返回选择洞数")
                        }
                        Text("发球台")
                            .font(.system(size: 16, weight: .bold))
                    }

                    if isLoadingTees {
                        HStack(spacing: 6) {
                            ProgressView()
                                .controlSize(.small)
                            Text("正在获取真实发球台")
                        }
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(.secondary)
                        .padding(7)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    } else if teeChoices.isEmpty {
                        HStack(spacing: 6) {
                            Image(systemName: "exclamationmark.triangle")
                                .foregroundStyle(.orange)
                            Text("暂无可用发球台")
                        }
                        .font(.system(size: 10, weight: .semibold))
                        .padding(7)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .fill(Color.orange.opacity(0.10))
                        )
                    } else {
                        ForEach(teeChoices) { choice in
                            teeChoiceRow(choice) {
                                guard let tee = teeOptions.first(where: {
                                    choice.id == "tee:\($0.teeBox.lowercased())"
                                }) else { return }
                                selectedTee = tee.teeBox
                            }
                        }
                    }

                    if teeLoadAttempted, teeChoices.isEmpty, !isLoadingTees {
                        Text("无法取得真实发球台时不会用猜测值开局。")
                            .font(.system(size: 8, weight: .medium))
                            .foregroundStyle(.secondary)
                    }

                    if let errorMessage {
                        Text(errorMessage)
                            .font(.system(size: 9, weight: .medium))
                            .foregroundStyle(.orange)
                            .padding(7)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .fill(Color.orange.opacity(0.10))
                            )
                    }
                }
                .padding(.horizontal, 6)
                .padding(.top, 4)
            }
            .scrollIndicators(.hidden)

            setupFooter
                .padding(.horizontal, 6)
                .padding(.bottom, 4)
        }
    }

    private var setupFooter: some View {
        VStack(spacing: 3) {
            HStack(spacing: 5) {
                Circle()
                    .fill(hasCachedVersion ? AICaddieDesignTokens.par : .orange)
                    .frame(width: 5, height: 5)
                Text("\(availabilityText) · \(availabilityDetail)")
                    .font(.system(size: 8.5, weight: .medium))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 3)
            startAction
        }
    }

    private var startAction: some View {
        Button {
            onStart(WatchCourseSelection(
                front: configuredFront,
                back: selectedBack,
                teeBox: selectedTee,
                ensureGeometry: ensureGeometry
            ))
        } label: {
            HStack(spacing: 5) {
                if isPreparing {
                    ProgressView()
                        .controlSize(.small)
                }
                Text(isPreparing ? "正在准备" : startActionLabel)
            }
            .font(.system(size: 13, weight: .bold))
            .foregroundStyle(.black)
            .frame(maxWidth: .infinity, minHeight: 34)
            .background(
                AICaddieDesignTokens.par,
                in: RoundedRectangle(cornerRadius: 10, style: .continuous)
            )
        }
        .buttonStyle(.plain)
        .disabled(isPreparing || isLoadingTees || teeChoices.isEmpty)
        .opacity(isPreparing || isLoadingTees || teeChoices.isEmpty ? 0.52 : 1)
    }

    private func teeChoiceRow(
        _ choice: WatchRoundSetupChoicePresentation,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Circle()
                    .fill(teeColor(choice.id))
                    .frame(width: 12, height: 12)
                Text(choice.title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.primary)
                Spacer(minLength: 0)
                Text(choice.detail)
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(.primary)
                    .monospacedDigit()
                if choice.isSelected {
                    Image(systemName: "checkmark")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(AICaddieDesignTokens.par)
                }
            }
            .padding(.horizontal, 9)
            .frame(maxWidth: .infinity, minHeight: 38, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color.white.opacity(choice.isSelected ? 0.10 : 0.06))
            )
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(choice.title) \(choice.detail)")
        .accessibilityValue(choice.isSelected ? "已选择" : "未选择")
    }

    private func teeColor(_ id: String) -> Color {
        let key = id.replacingOccurrences(of: "tee:", with: "").lowercased()
        switch key {
        case "blue": return .blue
        case "white": return .white
        case "red": return .red
        case "gold", "yellow": return .yellow
        case "black", "championship", "tips": return Color(white: 0.32)
        case "green": return .green
        case "silver": return Color(white: 0.72)
        default: return .gray
        }
    }

    var loopChoices: [WatchRoundSetupChoicePresentation] {
        [
            WatchRoundSetupChoicePresentation(
                id: "loop:front",
                title: "只打 \(loopName(front))",
                detail: "\(front.playableHoleCount) 洞",
                isSelected: selectedBackGlobalId == nil
            ),
        ] + backOptions.map { option in
            WatchRoundSetupChoicePresentation(
                id: "loop:\(option.globalId)",
                title: "\(loopName(front)) + \(loopName(option))",
                detail: "18 洞",
                isSelected: selectedBackGlobalId == option.globalId
            )
        }
    }

    var teeChoices: [WatchRoundSetupChoicePresentation] {
        teeOptions.map { tee in
            Self.teeChoice(
                for: tee,
                isSelected: tee.teeBox.caseInsensitiveCompare(selectedTee) == .orderedSame
            )
        }
    }

    static func teeChoice(
        for tee: WatchCourseTee,
        isSelected: Bool
    ) -> WatchRoundSetupChoicePresentation {
        WatchRoundSetupChoicePresentation(
            id: "tee:\(tee.teeBox.lowercased())",
            title: teeTitle(tee),
            detail: tee.yards.map { "\($0) 码" } ?? "码数未知",
            isSelected: isSelected
        )
    }

    var availabilityText: String {
        hasCachedVersion ? "已有离线版本" : "首次开局需下载"
    }

    var availabilityDetail: String {
        if hasCachedVersion {
            return "更换洞组或发球台时需要联网更新"
        }
        return ensureGeometry ? "将获取真实球场与地图数据" : "将获取真实球场数据"
    }

    var startActionLabel: String {
        hasCachedVersion ? "准备并开始" : "下载并开始"
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

    private static func hasCompatibleBackLoop(
        front: WatchCourseOption,
        courses: [WatchCourseOption]
    ) -> Bool {
        guard front.playableHoleCount == 9 else { return false }
        let venue = front.venueName
            ?? front.name.components(separatedBy: " ~ ").first
            ?? front.name
        return courses.contains {
            let candidateVenue = $0.venueName
                ?? $0.name.components(separatedBy: " ~ ").first
                ?? $0.name
            return $0.globalId != front.globalId
                && $0.playableHoleCount == 9
                && candidateVenue == venue
        }
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
        return "\(teeSummary) · \(front.playableHoleCount) 洞"
    }

    private var selectedTeeSummary: String {
        teeChoices.first(where: \.isSelected)?.title ?? "\(selectedTee.capitalized) T"
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

    private static func teeTitle(_ tee: WatchCourseTee) -> String {
        switch tee.teeBox.lowercased() {
        case "blue": "蓝 T"
        case "white": "白 T"
        case "red": "红 T"
        case "gold": "金 T"
        case "black", "championship", "tips": "黑 T"
        case "green": "绿 T"
        case "yellow": "黄 T"
        case "silver": "银 T"
        default:
            tee.name.hasSuffix("台") || tee.name.uppercased().hasSuffix(" T")
                ? tee.name
                : "\(tee.name) T"
        }
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
