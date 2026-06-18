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
    /// 组合 18 洞:(front 环 globalId, back 环 globalId, teeBox, roundId)。选了第二个环时调用。
    public let onPrepareCompositeRound: (Int, Int, String, String) -> Void
    public let onSaveBackendConfiguration: (String, String?) -> Void
    public let onClearBackendConfiguration: () -> Void

    @StateObject private var locationProvider = LocationProvider()
    @State private var roundId: String
    @State private var courseGlobalIdText: String
    @State private var backGlobalIdText: String = ""
    @State private var userPickedVenue = false
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
        onPrepareCompositeRound: @escaping (Int, Int, String, String) -> Void = { _, _, _, _ in },
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
        self.onPrepareCompositeRound = onPrepareCompositeRound
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
        // Default to the course's real tee (prefer Blue/White), else the given/played tee.
        let courseTees = selected?.tees ?? []
        let resolvedTee = courseTees.first(where: { ["blue", "white"].contains($0.lowercased()) })
            ?? courseTees.first
            ?? selected?.teeBox.flatMap { $0 == "unknown" ? nil : $0 }
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
                secondNineCard
                startCard
            }
            .padding(14)
        }
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        .navigationTitle("开始一场")
        .onAppear {
            locationProvider.requestAuthorization()
            locationProvider.startUpdatingLocation()
            ensureDefaultSelection()
        }
        .onChange(of: locationProvider.latestFix?.coordinate.latitude) { _, _ in
            // GPS arrived → if the player hasn't picked yet, jump to the nearest course.
            ensureDefaultSelection()
        }
    }

    /// The venue of the currently selected segment — the single source of truth (no separate state
    /// that can desync from courseGlobalIdText). Falls back to the top venue when nothing is selected.
    private var selectedVenueName: String {
        selectedSegment.map { $0.venueName ?? baseCourseName($0.name) } ?? displayVenues.first?.venue ?? ""
    }

    private var selectedVenueBinding: Binding<String> {
        Binding(
            get: { selectedVenueName },
            set: { newVenue in selectVenue(newVenue, userInitiated: true) }
        )
    }

    /// Select a venue → switch the chosen segment to that venue's first segment (keeps venue +
    /// segment list + 加打 + tee all consistent).
    private func selectVenue(_ venue: String, userInitiated: Bool) {
        guard let group = displayVenues.first(where: { $0.venue == venue }) ?? displayVenues.first,
              let first = group.segments.first else {
            return
        }
        if userInitiated {
            userPickedVenue = true
        }
        courseGlobalIdText = String(first.globalId)
        backGlobalIdText = ""
        applySelectedCourse(globalIdText: courseGlobalIdText)
    }

    /// Default to the top venue (nearest when GPS is available, else most-played) until the player
    /// picks one — and recover if the current selection isn't a real course.
    private func ensureDefaultSelection() {
        guard let top = displayVenues.first else { return }
        let currentIsValid = selectedSegment != nil
        if !currentIsValid {
            selectVenue(top.venue, userInitiated: false)
        } else if !userPickedVenue, !top.segments.contains(where: { String($0.globalId) == courseGlobalIdText }) {
            selectVenue(top.venue, userInitiated: false)
        }
    }

    /// Venues ordered nearest-first when GPS is available, else most-played first.
    private var displayVenues: [(venue: String, segments: [MobileCourseOption])] {
        let groups = venueGroups
        guard let fix = locationProvider.latestFix else {
            return groups
        }
        func distance(_ group: (venue: String, segments: [MobileCourseOption])) -> Double {
            group.segments.compactMap { segment -> Double? in
                guard let lat = segment.latitude, let lon = segment.longitude else { return nil }
                return haversineMetres(fix.coordinate.latitude, fix.coordinate.longitude, lat, lon)
            }.min() ?? .greatestFiniteMagnitude
        }
        return groups.sorted { distance($0) < distance($1) }
    }

    private func haversineMetres(_ lat1: Double, _ lon1: Double, _ lat2: Double, _ lon2: Double) -> Double {
        let r = 6_371_000.0
        let dLat = (lat2 - lat1) * .pi / 180
        let dLon = (lon2 - lon1) * .pi / 180
        let a = sin(dLat / 2) * sin(dLat / 2)
            + cos(lat1 * .pi / 180) * cos(lat2 * .pi / 180) * sin(dLon / 2) * sin(dLon / 2)
        return r * 2 * atan2(sqrt(a), sqrt(1 - a))
    }

    /// 按真实结构选场:每个球场列出它的各 9 洞环(黑骑士 A/B/C)或整场(北湖 18);选一个开始。
    @ViewBuilder private var courseCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("选择球场").font(.caption).foregroundStyle(.secondary)
            if displayVenues.isEmpty {
                Text("暂无球场,先在设置里同步 Garmin 球局。").font(.subheadline).foregroundStyle(.secondary)
            } else {
                if locationProvider.latestFix != nil {
                    Label("已按距离排序 · 最近在前", systemImage: "location.fill")
                        .font(.caption2).foregroundStyle(LiveHoleStyle.green)
                }
                // 下拉选球场(GPS 可用时最近在前,否则最常打在前)。球场名从选中环派生,不会空白。
                Picker("球场", selection: selectedVenueBinding) {
                    ForEach(displayVenues, id: \.venue) { group in
                        Text(group.venue).tag(group.venue)
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: .infinity, alignment: .leading)
                // 选中球场的各 9 洞环 / 整场。
                if let group = displayVenues.first(where: { $0.venue == selectedVenueName }) ?? displayVenues.first {
                    ForEach(group.segments) { segment in
                        segmentRow(segment)
                    }
                }
            }
            Text("选一个 9 洞环开始;想打 18 洞就在下方加打另一个环。")
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
            userPickedVenue = true
            courseGlobalIdText = String(segment.globalId)
            backGlobalIdText = ""  // changing the front loop resets any "add second nine" choice
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

    private var selectedSegment: MobileCourseOption? {
        courseOptions.first { String($0.globalId) == courseGlobalIdText }
    }

    /// 选中的是 9 洞环、且同球场还有可作为第二环的 9 洞环时,才提供「加打凑 18」。
    private var secondNineCandidates: [MobileCourseOption] {
        guard let selectedSegment, (selectedSegment.segmentHoles ?? selectedSegment.holes) == 9 else {
            return []
        }
        let venue = selectedSegment.venueName ?? baseCourseName(selectedSegment.name)
        return courseOptions
            .filter { ($0.venueName ?? baseCourseName($0.name)) == venue && ($0.segmentHoles ?? $0.holes) == 9 }
            .sorted { segmentSortKey($0) < segmentSortKey($1) }
    }

    /// 加打另一个 9 洞凑 18(可选):列出同球场的各 9 洞环 + 「不加打」。
    @ViewBuilder private var secondNineCard: some View {
        if !secondNineCandidates.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text("加打另一个 9 洞(可选,凑 18 洞)").font(.caption).foregroundStyle(.secondary)
                secondNineRow(title: "不加打 · 只打 9 洞", globalId: nil)
                ForEach(secondNineCandidates) { segment in
                    secondNineRow(title: "＋ \(segmentTitle(segment)) · 后九", globalId: segment.globalId)
                }
            }
            .liveCard()
        }
    }

    @ViewBuilder private func secondNineRow(title: String, globalId: Int?) -> some View {
        let value = globalId.map(String.init) ?? ""
        let selected = backGlobalIdText == value
        Button {
            backGlobalIdText = value
        } label: {
            HStack(spacing: 10) {
                Image(systemName: selected ? "largecircle.fill.circle" : "circle")
                    .foregroundStyle(selected ? LiveHoleStyle.green : .secondary)
                Text(title)
                    .font(.subheadline.weight(selected ? .semibold : .regular))
                    .foregroundStyle(.primary)
                Spacer()
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

    /// 发球台:优先用所选球场 Garmin CourseView 的真实 Tee(金/黑/蓝/白/红…),没有才回退通用集。
    /// 内部保留原始 key(传给后端),仅显示中文。
    private var teeOptions: [String] {
        let courseTees = selectedSegment?.tees ?? []
        let base = courseTees.isEmpty ? ["blue", "white", "red", "gold", "black", "green", "yellow", "silver"] : courseTees
        var seen = Set<String>()
        var result: [String] = []
        for tee in [teeBox] + base {
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
                    if let backGlobalId = Int(backGlobalIdText), backGlobalId != 0 {
                        onPrepareCompositeRound(courseGlobalId, backGlobalId, teeBox, roundId)
                    } else {
                        onPrepareCourseRound(courseGlobalId, roundId, teeBox, nine)
                    }
                    // Don't pop manually — once the round is prepared the Hub navigates straight
                    // into the live hole (pendingLiveHole → path), so 开始记分 enters the round.
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
        // Default to a sensible real tee for the chosen course (Blue/White, else the first).
        let tees = option.tees ?? []
        if !tees.isEmpty, !tees.contains(where: { $0.lowercased() == teeBox.lowercased() }) {
            teeBox = tees.first(where: { ["blue", "white"].contains($0.lowercased()) }) ?? tees.first ?? teeBox
        }
    }
}
