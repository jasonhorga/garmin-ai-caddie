import SwiftUI
import AICaddieDomain

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
    public let onBack: () -> Void

    @State private var selectedTee: String
    @State private var selectedPrimaryGlobalId: Int
    @State private var selectedBackGlobalId: Int?
    /// 18-hole course: the half the round starts on (前九 preselected). B4b-2 §7.
    @State private var selectedHalf: String = "front"
    @State private var loadedTeesByCourseId: [Int: [WatchCourseTee]] = [:]
    @State private var isLoadingTees = false
    @State private var teeLoadAttempted = false
    @State private var teeRequestToken: UUID?
    @State private var stage: WatchRoundSetupStage
    @State private var didSubmitStart = false
    let initialStage: WatchRoundSetupStage

    public init(
        front: WatchCourseOption,
        courses: [WatchCourseOption],
        hasCachedVersion: Bool = false,
        isPreparing: Bool = false,
        errorMessage: String? = nil,
        ensureGeometry: Bool = false,
        onLoadTees: @escaping (Int) async -> [WatchCourseTee] = { _ in [] },
        onStart: @escaping (WatchCourseSelection) -> Void = { _ in },
        onBack: @escaping () -> Void = {}
    ) {
        self.front = front
        self.courses = courses
        self.hasCachedVersion = hasCachedVersion
        self.isPreparing = isPreparing
        self.errorMessage = errorMessage
        self.ensureGeometry = ensureGeometry
        self.onLoadTees = onLoadTees
        self.onStart = onStart
        self.onBack = onBack
        _selectedTee = State(initialValue: Self.initialTee(for: front))
        _selectedPrimaryGlobalId = State(initialValue: front.globalId)
        _selectedBackGlobalId = State(initialValue: nil)
        let startsWithHoles = Self.hasCompatibleBackLoop(front: front, courses: courses)
            || Self.playsHalves(front)
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
        .task(id: selectedPrimary.globalId) {
            await loadTeesIfNeeded()
        }
        .onChange(of: errorMessage) { _, newValue in
            // A start that failed closed (malformed selection, unpersistable template) stays on
            // this screen with its message; the start button becomes retryable.
            if newValue != nil {
                didSubmitStart = false
            }
        }
        .simultaneousGesture(
            DragGesture(minimumDistance: 24)
                .onEnded { value in
                    guard WatchEdgeBackGesture.shouldTrigger(
                        startX: value.startLocation.x,
                        translation: value.translation
                    ) else { return }
                    handleBack()
                }
        )
        .persistentSystemOverlays(.hidden)
    }

    private var holeSelection: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 7) {
                WatchInstrumentHeader(
                    Self.playsHalves(front) ? "从哪个 9 洞开始" : "打几洞",
                    backLabel: "返回球场",
                    onBack: handleBack
                )

                ForEach(Self.playsHalves(front) ? halfChoices : loopChoices) { choice in
                    Button {
                        if Self.playsHalves(front) {
                            selectHalf(choice.id)
                        } else {
                            selectLoop(choice.id)
                        }
                        withAnimation(.easeOut(duration: 0.16)) { stage = .tees }
                    } label: {
                        HStack(spacing: 7) {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(choice.title)
                                    .font(.system(size: 16, weight: .black))
                                Text(choice.detail)
                                    .font(.system(size: 12, weight: .bold))
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
                    .accessibilityIdentifier(choice.id)
                    .accessibilityValue(choice.isSelected ? "已选择" : "未选择")
                }
            }
            .padding(.horizontal, 8)
            .padding(.top, 8)
        }
        .ignoresSafeArea(edges: .top)
        .scrollIndicators(.hidden)
    }

    private var teeSelection: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                WatchInstrumentHeader("发球台", backLabel: "返回", onBack: handleBack)

                if isLoadingTees {
                    HStack(spacing: 6) {
                        ProgressView()
                            .controlSize(.small)
                        Text("正在获取真实发球台")
                    }
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(.secondary)
                    .padding(7)
                    .frame(maxWidth: .infinity, alignment: .leading)
                } else if teeChoices.isEmpty {
                        HStack(spacing: 6) {
                            Image(systemName: "clock.arrow.circlepath")
                                .foregroundStyle(.yellow)
                            Text("发球台资料稍后补齐 · 先按 \(teeSummary(selectedTee)) 开局")
                    }
                    .font(.system(size: 13, weight: .bold))
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
                    Text("真实发球台到达后会自动替换；现在仍可先开局。")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.secondary)
                }

                if let errorMessage {
                    Text(errorMessage)
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.orange)
                        .padding(7)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .fill(Color.orange.opacity(0.10))
                        )
                }

                setupFooter
                    .padding(.top, 42)
            }
            .padding(.horizontal, 8)
            .padding(.top, 8)
            .padding(.bottom, 6)
        }
        .ignoresSafeArea(edges: .top)
        .scrollIndicators(.hidden)
    }

    private var setupFooter: some View {
        VStack(spacing: 3) {
            HStack(spacing: 5) {
                Circle()
                    .fill(hasCachedVersion ? AICaddieDesignTokens.par : .orange)
                    .frame(width: 5, height: 5)
                Text("\(availabilityText) · \(availabilityDetail)")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .minimumScaleFactor(0.68)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 3)
            startAction
        }
    }

    private var startAction: some View {
        Button {
            guard !isPreparing, !didSubmitStart else { return }
            didSubmitStart = true
            onStart(startSelection)
        } label: {
            HStack(spacing: 5) {
                if isPreparing {
                    ProgressView()
                        .controlSize(.small)
                }
                Text(isPreparing ? "正在准备" : startActionLabel)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
            .font(.system(size: 16, weight: .black))
            .foregroundStyle(.black)
            .frame(maxWidth: .infinity, minHeight: 48)
            .background(
                AICaddieDesignTokens.par,
                in: RoundedRectangle(cornerRadius: 10, style: .continuous)
            )
        }
        .buttonStyle(.plain)
        .disabled(isPreparing || didSubmitStart)
        .opacity(isPreparing || didSubmitStart ? 0.52 : 1)
        .accessibilityIdentifier("watch-setup-start")
    }

    /// Exactly what 开始 submits: the selected loop(s) or, for an 18-hole course, one ordered half
    /// (`G:front` / `G:back`); the second half is chosen at the turn.
    var startSelection: WatchCourseSelection {
        WatchCourseSelection(
            front: configuredFront,
            back: Self.playsHalves(front) ? nil : selectedBack,
            teeBox: selectedTee,
            ensureGeometry: ensureGeometry,
            firstHalf: Self.playsHalves(front) ? selectedHalf : nil
        )
    }

    /// An 18-hole course (a normal `segmentHoles: 18` row) is played as 前九 / 后九.
    static func playsHalves(_ option: WatchCourseOption) -> Bool {
        option.playableHoleCount == 18
    }

    /// 前九 / 后九 start tiles; `id` is the accessibility identifier.
    var halfChoices: [WatchRoundSetupChoicePresentation] {
        guard Self.playsHalves(front) else { return [] }
        return WatchCourseSelection.halves.map { half in
            WatchRoundSetupChoicePresentation(
                id: "watch-setup-half-\(half)",
                title: WatchCourseSelection.halfName(half),
                detail: half == "back" ? "第 10–18 洞" : "第 1–9 洞",
                isSelected: selectedHalf == half
            )
        }
    }

    /// "从 后九 开始 · 蓝 T" — the shared `NineLoopPlan` start title for a half.
    static func halfStartTitle(globalId: Int, half: String, teeName: String?) -> String {
        let loops = WatchCourseSelection.halves.map {
            NineLoop(id: "\(globalId):\($0)", name: WatchCourseSelection.halfName($0))
        }
        let plan = NineLoopPlan(
            course: NineLoopCourse(id: String(globalId), loops: loops),
            first: "\(globalId):\(WatchCourseSelection.normalizedHalf(half) ?? "front")"
        )
        return plan?.startTitle(teeName: teeName) ?? "从 \(WatchCourseSelection.halfName(half)) 开始"
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
                    .font(.system(size: 15, weight: .black))
                    .foregroundStyle(.primary)
                Spacer(minLength: 0)
                Text(choice.detail)
                    .font(.system(size: 13, weight: .black, design: .rounded))
                    .foregroundStyle(.primary)
                    .monospacedDigit()
                if choice.isSelected {
                    Image(systemName: "checkmark")
                        .font(.system(size: 13, weight: .black))
                        .foregroundStyle(AICaddieDesignTokens.par)
                }
            }
            .padding(.horizontal, 9)
            .frame(maxWidth: .infinity, minHeight: 46, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color.white.opacity(choice.isSelected ? 0.10 : 0.06))
            )
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(choice.title) \(choice.detail)")
        .accessibilityValue(choice.isSelected ? "已选择" : "未选择")
    }

    /// The shared tee-colour mapping (`AICaddieDomain.TeeColor`, same as the phone's 开始一场).
    private func teeColor(_ id: String) -> Color {
        let tee = TeeColor.forTee(id)
        return Color(red: tee.red, green: tee.green, blue: tee.blue)
    }

    var loopChoices: [WatchRoundSetupChoicePresentation] {
        let repeatsOnly = backOptions.count == 1 && backOptions[0].globalId == front.globalId
        let fullChoices = backOptions.map { option in
            WatchRoundSetupChoicePresentation(
                id: "loop:full:\(option.globalId)",
                title: repeatsOnly ? "全 18 洞" : "\(loopName(front)) + \(loopName(option))",
                detail: repeatsOnly ? "同一球场打两轮" : "18 洞",
                isSelected: selectedPrimaryGlobalId == front.globalId
                    && selectedBackGlobalId == option.globalId
            )
        }
        let frontChoice = WatchRoundSetupChoicePresentation(
            id: "loop:front:\(front.globalId)",
            title: repeatsOnly ? "只打 9 洞" : "只打\(loopName(front))",
            detail: repeatsOnly ? loopName(front) : "\(front.playableHoleCount) 洞",
            isSelected: selectedPrimaryGlobalId == front.globalId && selectedBackGlobalId == nil
        )
        let backChoices = backOptions.filter { $0.globalId != front.globalId }.map { option in
            WatchRoundSetupChoicePresentation(
                id: "loop:back:\(option.globalId)",
                title: "只打\(loopName(option))",
                detail: "\(option.playableHoleCount) 洞",
                isSelected: selectedPrimaryGlobalId == option.globalId && selectedBackGlobalId == nil
            )
        }
        return fullChoices + [frontChoice] + backChoices
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
            detail: tee.yards.map {
                "\($0.formatted(.number.grouping(.automatic))) 码"
            } ?? "码数未知",
            isSelected: isSelected
        )
    }

    var availabilityText: String {
        hasCachedVersion ? "已有离线版本" : "可立即开局"
    }

    var availabilityDetail: String {
        if hasCachedVersion {
            return "更换洞组或发球台时需要联网更新"
        }
        return ensureGeometry ? "球场与地图后台补齐" : "球场数据后台补齐"
    }

    var startActionLabel: String {
        if Self.playsHalves(front) {
            let teeName = WatchCourseSelection.hasExplicitTee(selectedTee) ? selectedTeeSummary : nil
            return Self.halfStartTitle(globalId: front.globalId, half: selectedHalf, teeName: teeName)
        }
        return hasCachedVersion ? "开始" : "立即开始"
    }

    private var selectedBack: WatchCourseOption? {
        guard let selectedBackGlobalId else { return nil }
        return backOptions.first { $0.globalId == selectedBackGlobalId }
    }

    private var selectedPrimary: WatchCourseOption {
        ([front] + backOptions).first { $0.globalId == selectedPrimaryGlobalId } ?? front
    }

    private var backOptions: [WatchCourseOption] {
        guard front.playableHoleCount == 9 else { return [] }
        var seen = Set<Int>()
        return ([front] + courses)
            .filter {
                $0.playableHoleCount == 9
                    && venueName($0) == venueName(front)
                    && seen.insert($0.globalId).inserted
            }
            .sorted { lhs, rhs in
                let left = loopSortKey(lhs)
                let right = loopSortKey(rhs)
                return left == right ? lhs.globalId < rhs.globalId : left < right
            }
    }

    private static func hasCompatibleBackLoop(
        front: WatchCourseOption,
        courses _: [WatchCourseOption]
    ) -> Bool {
        // Every factual 9-hole course can be played twice even when the catalogue has no sibling
        // loop row. Additional same-venue rows merely add A+B/A+C choices.
        return front.playableHoleCount == 9
    }

    private var teeOptions: [WatchCourseTee] {
        if let loadedTees = loadedTeesByCourseId[selectedPrimary.globalId], !loadedTees.isEmpty {
            return loadedTees
        }

        var seen = Set<String>()
        var result: [WatchCourseTee] = []
        let defaultTee = selectedPrimary.teeBox?.trimmingCharacters(in: .whitespacesAndNewlines)
        for value in selectedPrimary.tees + [defaultTee].compactMap({ $0 }) {
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
        teeOptions.isEmpty
            ? selectedPrimary
            : selectedPrimary.withTees(teeOptions, selectedTee: selectedTee)
    }

    private var selectionSummary: String {
        let teeSummary = teeOptions.isEmpty ? "发球台待加载" : selectedTeeSummary
        if let selectedBack {
            return "\(loopName(front)) + \(loopName(selectedBack)) · \(teeSummary) · 18 洞"
        }
        return "\(teeSummary) · \(front.playableHoleCount) 洞"
    }

    private var selectedTeeSummary: String {
        teeChoices.first(where: \.isSelected)?.title ?? teeSummary(selectedTee)
    }

    private func venueName(_ option: WatchCourseOption) -> String {
        GarminCourseNameAuthority.canonicalVenueName(
            providerName: option.name,
            venueName: option.venueName,
            venueNameSource: option.venueNameSource,
            segmentLabel: option.segmentLabel
        )
    }

    private func loopName(_ option: WatchCourseOption) -> String {
        option.segmentDisplayTitle
    }

    private func loopSortKey(_ option: WatchCourseOption) -> String {
        option.resolvedSegmentLabel?.lowercased() ?? ""
    }

    private func selectLoop(_ id: String) {
        let parts = id.split(separator: ":")
        guard parts.count == 3, let globalId = Int(parts[2]) else { return }
        switch parts[1] {
        case "full":
            selectedPrimaryGlobalId = front.globalId
            selectedBackGlobalId = globalId
            selectedTee = Self.initialTee(for: front)
        case "front":
            selectedPrimaryGlobalId = front.globalId
            selectedBackGlobalId = nil
            selectedTee = Self.initialTee(for: front)
        case "back":
            guard let option = backOptions.first(where: { $0.globalId == globalId }) else { return }
            selectedPrimaryGlobalId = option.globalId
            selectedBackGlobalId = nil
            selectedTee = Self.initialTee(for: option)
        default:
            return
        }
        teeLoadAttempted = false
    }

    private func selectHalf(_ id: String) {
        guard let half = WatchCourseSelection.normalizedHalf(
            String(id.dropFirst("watch-setup-half-".count))
        ) else { return }
        selectedHalf = half
    }

    private func handleBack() {
        // A failed/aborted setup must be retryable when the same destination is opened again. The
        // guard is only a double-tap fence for the current submission, not a persistent course lock.
        didSubmitStart = false
        if stage == .tees, initialStage == .holes {
            withAnimation(.easeOut(duration: 0.16)) { stage = .holes }
        } else {
            onBack()
        }
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
        case "back": "后 T"
        case "middle": "中 T"
        case "forward": "前 T"
        default:
            tee.name.hasSuffix("台") || tee.name.uppercased().hasSuffix(" T")
                ? tee.name
                : "\(tee.name) T"
        }
    }

    private static func initialTee(for course: WatchCourseOption) -> String {
        let explicit = course.teeBox?.trimmingCharacters(in: .whitespacesAndNewlines)
        let hasExplicit = explicit.map {
            !$0.isEmpty && $0.caseInsensitiveCompare("unknown") != .orderedSame
        } ?? false
        if course.tees.isEmpty && !hasExplicit {
            return "unknown"
        }
        return course.preferredTee
    }

    private func teeSummary(_ tee: String) -> String {
        tee.caseInsensitiveCompare("unknown") == .orderedSame ? "球场默认 T" : "\(tee) T"
    }

    @MainActor
    private func loadTeesIfNeeded() async {
        let requestToken = UUID()
        teeRequestToken = requestToken
        let course = selectedPrimary
        guard course.tees.isEmpty else {
            isLoadingTees = false
            return
        }
        if let teeBox = course.teeBox?.trimmingCharacters(in: .whitespacesAndNewlines),
           !teeBox.isEmpty,
           teeBox.caseInsensitiveCompare("unknown") != .orderedSame {
            isLoadingTees = false
            return
        }

        teeLoadAttempted = true
        isLoadingTees = true
        defer {
            if teeRequestToken == requestToken {
                isLoadingTees = false
            }
        }
        let tees = await onLoadTees(course.globalId)
        guard !Task.isCancelled,
              teeRequestToken == requestToken,
              selectedPrimary.globalId == course.globalId else { return }
        loadedTeesByCourseId[course.globalId] = tees
        if let defaultTee = tees.first(where: \.isDefault) ?? tees.first {
            selectedTee = defaultTee.teeBox
        }
    }
}
