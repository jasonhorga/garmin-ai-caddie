import CoreLocation
import Foundation
import SwiftUI

public struct CurrentHoleView: View {
    public let package: LiveRoundPackage
    public let hole: Hole
    public let onEvent: (LiveRoundEvent) -> Void
    private let requestBuilder = CaddieDecisionRequestBuilder()
    private let offlineDecisionEvaluator = OfflineCaddieDecisionEvaluator()
    private let caddieClient: CaddieDecisionClient?
    private let mediaUploadClient: MediaUploadClient?
    private let caddieBaseURL: URL?
    private let adminToken: String?
    private let offlineStore: OfflineStore?
    private let watchBridge: WatchEventBridge?
    private let liveRoundState: LiveRoundStateSnapshot?
    // 球局调整(加打 / 减九洞 / 结束本场)— round-11: 从首页 Hub 移进开球后的实战屏(用户反馈:
    // 这些该在球局里、不放首页)。控件与闭包原样保留,仅换了容身的屏。
    private let courseOptions: [MobileCourseOption]
    private let startingNine: String?
    private let isPreparingRound: Bool
    private let onChangeNine: (String) -> Void
    private let onPrepareCourseRound: (Int, String, String, String) -> Void
    private let onPrepareCompositeRound: (Int, Int, String, String) -> Void
    private let onDiscard: () -> Void

    @StateObject private var locationProvider = LocationProvider()
    @State private var score: Int
    @State private var puttCount: Int = 2
    @State private var penaltyCount: Int = 0
    @State private var selectedClub: String
    @State private var selectedShotType: String
    @State private var selectedStrategyMode: String = "stock"
    @State private var holePrep: CoursePrepHole?
    @State private var distanceToPinText: String = ""
    @State private var selectedLie: String = "fairway"
    @State private var currentCoordinate: CLLocationCoordinate2D?
    @State private var targetCoordinate: CLLocationCoordinate2D?
    @State private var currentHorizontalAccuracyM: Double?
    @State private var note: String = ""
    @State private var caddieDecision: CaddieDecisionResponse?
    @State private var isLoadingCaddieDecision = false
    @State private var caddieErrorMessage: String?
    @State private var visionFindings: [[String: JSONValue]] = []
    @State private var lastAppliedRestoredHoleState: LiveHoleStateSnapshot?
    @State private var showManage = false
    @State private var showDiscardConfirm = false

    public init(
        package: LiveRoundPackage,
        hole: Hole,
        caddieBaseURL: URL? = nil,
        adminToken: String? = nil,
        caddieClient: CaddieDecisionClient? = nil,
        offlineStore: OfflineStore? = nil,
        watchBridge: WatchEventBridge? = nil,
        liveRoundState: LiveRoundStateSnapshot? = nil,
        courseOptions: [MobileCourseOption] = [],
        startingNine: String? = nil,
        isPreparingRound: Bool = false,
        onChangeNine: @escaping (String) -> Void = { _ in },
        onPrepareCourseRound: @escaping (Int, String, String, String) -> Void = { _, _, _, _ in },
        onPrepareCompositeRound: @escaping (Int, Int, String, String) -> Void = { _, _, _, _ in },
        onDiscard: @escaping () -> Void = {},
        onEvent: @escaping (LiveRoundEvent) -> Void = { _ in }
    ) {
        self.package = package
        self.hole = hole
        self.onEvent = onEvent
        self.caddieClient = caddieClient ?? caddieBaseURL.map { CaddieDecisionClient(baseURL: $0, adminToken: adminToken) }
        self.mediaUploadClient = caddieBaseURL.map { MediaUploadClient(baseURL: $0, adminToken: adminToken) }
        self.caddieBaseURL = caddieBaseURL
        self.adminToken = adminToken
        self.offlineStore = offlineStore
        self.watchBridge = watchBridge
        self.liveRoundState = liveRoundState
        self.courseOptions = courseOptions
        self.startingNine = startingNine
        self.isPreparingRound = isPreparingRound
        self.onChangeNine = onChangeNine
        self.onPrepareCourseRound = onPrepareCourseRound
        self.onPrepareCompositeRound = onPrepareCompositeRound
        self.onDiscard = onDiscard
        let seed = package.caddieContextSeeds.first { $0.hole == hole.number }
        let restoredHoleState = liveRoundState?.holeState(for: hole.number)
        self._score = State(initialValue: restoredHoleState?.score ?? hole.par)
        self._puttCount = State(initialValue: restoredHoleState?.putts ?? 2)
        self._penaltyCount = State(initialValue: restoredHoleState?.penaltyCount ?? 0)
        self._selectedClub = State(initialValue: restoredHoleState.map { zhClubName($0.selectedClub) }
            ?? Self.defaultClub(par: hole.par, holeYards: hole.yards, profiles: package.clubProfiles))
        self._selectedShotType = State(initialValue: restoredHoleState?.selectedShotType ?? seed?.shotTypes.first ?? "approach")
        self._selectedStrategyMode = State(initialValue: restoredHoleState?.selectedStrategyMode ?? "stock")
        self._distanceToPinText = State(initialValue: restoredHoleState?.distanceToPinM.map(Self.yardsText(fromMetres:)) ?? "")
        self._selectedLie = State(initialValue: restoredHoleState?.lie ?? "fairway")
        self._currentHorizontalAccuracyM = State(initialValue: restoredHoleState?.horizontalAccuracyM)
        self._lastAppliedRestoredHoleState = State(initialValue: restoredHoleState)
        if let latitude = restoredHoleState?.latitude, let longitude = restoredHoleState?.longitude {
            self._currentCoordinate = State(initialValue: CLLocationCoordinate2D(latitude: latitude, longitude: longitude))
        } else {
            self._currentCoordinate = State(initialValue: nil)
        }
        if let targetLatitude = restoredHoleState?.targetLatitude, let targetLongitude = restoredHoleState?.targetLongitude {
            self._targetCoordinate = State(initialValue: CLLocationCoordinate2D(latitude: targetLatitude, longitude: targetLongitude))
        } else {
            self._targetCoordinate = State(initialValue: nil)
        }
    }

    public var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                HoleDistanceHeader(
                    course: package.course.name,
                    holeNumber: hole.number,
                    holeCount: package.holes.count,
                    par: hole.par,
                    toPinYards: Int(distanceToPinText.trimmingCharacters(in: .whitespacesAndNewlines)),
                    carryFrontYards: nil,
                    toParText: holeToParText
                )

                VStack(spacing: 12) {
                    holeMapCard

                    // Caddie recommendation — the focal card. Embeds the proven
                    // CaddiePlanView for the decision content; chrome is redesigned.
                    VStack(alignment: .leading, spacing: 10) {
                        Text("球童建议")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(LiveHoleStyle.green)
                        // 策略开关移到球童卡上(原埋在「更多调整」里):护分/标准/进攻直接切,建议随即重算。
                        Picker("策略", selection: $selectedStrategyMode) {
                            ForEach(strategyModeOptions, id: \.self) { Text(strategyModeLabel($0)).tag($0) }
                        }
                        .pickerStyle(.segmented)
                        if let caddieDecision {
                            CaddiePlanView(response: caddieDecision, hazards: caddiePlanHazards)
                        } else {
                            CaddiePlanView(seed: caddieContextSeed, hazards: caddiePlanHazards)
                        }
                        if isLoadingCaddieDecision {
                            ProgressView("更新球童建议…")
                        }
                        if let caddieErrorMessage {
                            Text(caddieErrorMessage).font(.caption).foregroundStyle(.secondary)
                        }
                        Button {
                            Task { await loadCaddieDecision() }
                        } label: {
                            Label("刷新球童", systemImage: "arrow.clockwise").font(.subheadline)
                        }
                        .disabled(isLoadingCaddieDecision)
                    }
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.white)
                    .overlay(RoundedRectangle(cornerRadius: 16).stroke(LiveHoleStyle.green, lineWidth: 1.5))
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

                    // Club picker + record/save (records the current GPS fix).
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .firstTextBaseline) {
                            Text("选球杆").font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            clubPickerMenu  // round-12: 全杆下拉,默认推荐杆,选完即记
                        }
                        // 快捷:本杆最相关的 3 支(球位过滤);全部球杆走上面的下拉。
                        ClubStripView(clubs: clubNames, selected: selectedClub) { selectClub($0) }
                        RecordShotButton(title: "📍 保存本洞 · 含定位", lastShotText: recordHintText) { submitEvents() }
                    }
                    .liveCard()

                    // Compact score.
                    VStack(alignment: .leading, spacing: 10) {
                        Text("本洞成绩").font(.caption).foregroundStyle(.secondary)
                        HoleScoreSteppers(score: $score, putts: $puttCount)
                    }
                    .liveCard()

                    // All the original inputs are preserved, tucked into 更多调整.
                    DisclosureGroup("更多调整(打法 / 球位 / 距离 / 目标 / 备注)") {
                        VStack(spacing: 10) {
                            Picker("打法", selection: $selectedShotType) {
                                ForEach(shotTypeOptions, id: \.self) { Text(zhShotType($0)).tag($0) }
                            }
                            Picker("球位", selection: $selectedLie) {
                                ForEach(lieOptions, id: \.self) { Text(zhLie($0)).tag($0) }
                            }
                            TextField("到旗杆距离(码)", text: $distanceToPinText)
                                .keyboardType(.decimalPad)
                            Button {
                                targetCoordinate = currentCoordinate
                            } label: {
                                Label("设为目标点", systemImage: "mappin.and.ellipse")
                            }
                            .disabled(currentCoordinate == nil)
                            Stepper("罚杆 \(penaltyCount)", value: $penaltyCount, in: 0...4)
                            TextField("备注", text: $note)
                        }
                        .padding(.top, 6)
                    }
                    .liveCard()

                    // Media capture (unchanged behavior).
                    VStack(alignment: .leading, spacing: 10) {
                        Text("拍照取证").font(.caption).foregroundStyle(.secondary)
                        MediaCaptureView(
                            roundId: package.roundId,
                            hole: hole.number,
                            targetId: caddieContextSeed?.sourceRef ?? "\(package.roundId):\(hole.number)",
                            offlineStore: offlineStore,
                            uploadClient: mediaUploadClient,
                            onEvent: onEvent,
                            onVisionFindings: { findings in
                                visionFindings = findings
                                Task { await loadCaddieDecision() }
                            }
                        )
                    }
                    .liveCard()

                    // 球局调整(加打 / 减九洞 / 结束本场)— 移自首页,收在底部折叠区,不打扰记分主流程。
                    manageSection
                }
                .padding(14)
            }
        }
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        .navigationTitle("第 \(hole.number) 洞")
        .onAppear {
            locationProvider.requestAuthorization()
            locationProvider.startUpdatingLocation()
        }
        .onReceive(locationProvider.$latestFix) { latestFix in
            guard let latestFix else {
                return
            }
            currentCoordinate = latestFix.coordinate
            currentHorizontalAccuracyM = latestFix.horizontalAccuracyM
        }
        .task(id: hole.number) {
            // Sync the selected club to the caddie's recommendation on a FRESH hole (so we never sit
            // on an arbitrary default); a hole the player already recorded keeps their chosen club.
            let alreadyRecorded = liveRoundState?.holeState(for: hole.number)?.selectedClub.isEmpty == false
            await loadCaddieDecision(syncClub: !alreadyRecorded)
        }
        .task(id: hole.number) {
            await loadHoleMap()
        }
        .onChange(of: liveRoundState) { _, newState in
            applyRestoredStateIfNeeded(newState)
        }
        .onChange(of: selectedStrategyMode) { _, _ in
            // Changing strategy re-plans the shot → adopt the new strategy's recommended club so the
            // club strip + landing marker move with it (保守/激进 选不同杆,图上的落点要跟着变).
            Task { await loadCaddieDecision(syncClub: true) }
        }
    }

    private var caddieContextSeed: CaddieContextSeed? {
        package.caddieContextSeeds.first { $0.hole == hole.number }
    }

    /// 球洞俯视图(2D):服务端渲染的真实球场图 + 推荐打法叠加。无图时不显示。
    @ViewBuilder private var holeMapCard: some View {
        if let holePrep, holePrep.map?.overlay != nil {
            VStack(alignment: .leading, spacing: 8) {
                Text("球洞俯视图").font(.caption).foregroundStyle(.secondary)
                HoleImageMapView(hole: holePrep, selectedClub: selectedClub, selectedClubMetres: selectedClubMetres)
            }
            .liveCard()
        }
    }

    private func loadHoleMap() async {
        guard let caddieBaseURL else {
            return
        }
        // 每洞用自己的 source 球场 + 本地洞号(组合局后九在第二个环的 gid)。
        let mapGlobalId = hole.sourceGlobalId ?? package.course.globalId
        let mapLocalHole = hole.sourceLocalHole ?? hole.number
        guard mapGlobalId != 0 else {
            return
        }
        let client = SyncClient(baseURL: caddieBaseURL, adminToken: adminToken)
        holePrep = try? await client.fetchHolePrep(globalId: mapGlobalId, localHole: mapLocalHole)
    }

    /// 本洞避开区:取按洞拉取的 prep 的 hazards(沙坑/水域 米区间)供球童方案展示。
    /// (live 包为提速不再内置全洞 coursePrep;按洞 prep 随 2D 图一起加载。)
    private var caddiePlanHazards: [CaddiePlanHazard] {
        guard let holePrep else {
            return []
        }
        return CaddiePlanHazard.from(holePrep.hazards)
    }

    /// Club picker options: the player's clubs, minus empty/"Unknown" placeholders and
    /// case-insensitive duplicates (Garmin club names are user-entered and messy).
    /// Player's clubs from the backend real bag: zhClubName-normalized, deduped (keep most-sampled),
    /// restricted to the player's bag. `filterTeeOnly` drops 一号木 off the tee — applied to the
    /// quick chips, but NOT to the full dropdown (which lets the player pick ANY club).
    private func bagBest(filterTeeOnly: Bool) -> [String: ClubProfile] {
        var best: [String: ClubProfile] = [:]
        for profile in package.clubProfiles {
            let raw = profile.clubName.trimmingCharacters(in: .whitespaces)
            guard !raw.isEmpty, raw.lowercased() != "unknown" else { continue }
            let name = zhClubName(raw)
            if filterTeeOnly, clubIsTeeOnly(name), selectedLie != "tee" { continue }
            if let existing = best[name], existing.sampleSize >= profile.sampleSize { continue }
            best[name] = profile
        }
        // Restrict to the player's bag — manual override (球杆设置) if set, else the real Garmin bag —
        // so clubs they don't carry (a stray mis-tagged "二号小鸡腿") never appear. Neither known → all.
        if let bag = ClubBagStore.effectiveBag() {
            best = best.filter { bag.contains($0.key) }
        }
        return best
    }

    /// The 3 clubs most relevant to THIS shot (quick chips): nearest to the to-pin distance when
    /// known, else the 3 longest. Always keeps the selected club visible.
    private var clubNames: [String] {
        let best = bagBest(filterTeeOnly: true)
        let ordered: [String]
        if let target = distanceToPinMetres {
            ordered = best.sorted { abs($0.value.medianM - target) < abs($1.value.medianM - target) }.map(\.key)
        } else {
            ordered = best.sorted { $0.value.medianM > $1.value.medianM }.map(\.key)
        }
        var top = Array(ordered.prefix(3))
        if best[selectedClub] != nil, !top.contains(selectedClub) {
            top = [selectedClub] + top.prefix(2)
        }
        return top
    }

    /// round-12: the FULL bag for the dropdown picker — every club + its distance, longest→shortest,
    /// so the player can choose ANY club (not just the 3 quick chips). No tee-only filter here.
    private var allBagClubs: [(name: String, metres: Double)] {
        bagBest(filterTeeOnly: false)
            .sorted { $0.value.medianM > $1.value.medianM }
            .map { (name: $0.key, metres: $0.value.medianM) }
    }

    /// The caddie's currently-recommended club (zh), used to mark it in the dropdown.
    private var recommendedClub: String? {
        guard let decision = caddieDecision, let raw = recommendedClubName(from: decision) else {
            return nil
        }
        return zhClubName(raw)
    }

    /// round-12: full-bag dropdown — pick ANY club + its distance; recommended club marked; defaults
    /// to the recommendation (selectedClub is synced to it). Selecting records the pick (选完即记).
    @ViewBuilder private var clubPickerMenu: some View {
        Menu {
            ForEach(allBagClubs, id: \.name) { club in
                Button {
                    selectClub(club.name)
                } label: {
                    let label = "\(club.name) · \(CoursePrepRoute.yards(fromMetres: club.metres)) 码"
                        + (club.name == recommendedClub ? " · 推荐" : "")
                    if club.name == selectedClub {
                        Label(label, systemImage: "checkmark")
                    } else {
                        Text(label)
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "bag").font(.caption)
                Text(selectedClub.isEmpty ? "选择球杆" : selectedClub).font(.subheadline.weight(.semibold))
                Image(systemName: "chevron.down").font(.caption2)
            }
            .foregroundStyle(LiveHoleStyle.green)
        }
    }

    /// Set the selected club (chips + dropdown). round-12「选完即记」: persist the pick immediately as
    /// a lightweight club event (clubName/打法/球位/距离 — NOT a full shot/GPS record; 保存本洞 still
    /// records the shot) so the choice survives a quit/restart and drives the map landing marker.
    private func selectClub(_ club: String) {
        let changed = club != selectedClub
        selectedClub = club
        guard changed, !club.isEmpty else { return }
        emit(kind: .club, timestamp: ISO8601DateFormatter().string(from: Date()), payload: [
            "clubName": .string(selectedClub),
            "shotType": .string(selectedShotType),
            "strategyMode": .string(selectedStrategyMode),
            "lie": .string(selectedLie),
            "distanceToPinM": distanceToPinPayload(),
        ])
    }

    /// The selected club's typical distance (metres) from the bag model — drives the live map marker.
    private var selectedClubMetres: Double? {
        guard let profile = package.clubProfiles.first(where: { zhClubName($0.clubName) == selectedClub }) else {
            return nil
        }
        return profile.medianM
    }

    /// A sensible pre-decision default club: the tee club (longest trustworthy non-tee-only club) for
    /// par 4/5, or the club whose median matches the green distance for a par 3. Avoids defaulting to
    /// an arbitrary clubProfiles.first (which could be a noisy short iron — owner's "9I" reads 159m
    /// off 13 stray shots). The live caddie decision refines this to its recommendation once loaded.
    private static func defaultClub(par: Int, holeYards: Int?, profiles: [ClubProfile]) -> String {
        let usable = profiles.filter { profile in
            let raw = profile.clubName.trimmingCharacters(in: .whitespaces)
            return !raw.isEmpty && raw.lowercased() != "unknown" && profile.medianM > 0
        }
        // ≥20 samples mirrors the backend caddie trust filter (MIN_CADDIE_SAMPLE); fall back to all
        // data-backed clubs for low-data players so we still pick something reasonable.
        let trusted = usable.filter { $0.sampleSize >= 20 }
        let pool = trusted.isEmpty ? usable : trusted
        guard !pool.isEmpty else { return "" }
        let pick: ClubProfile
        if par == 3, let yards = holeYards, yards > 0 {
            let targetM = Double(yards) * 0.9144
            pick = pool.min { abs($0.medianM - targetM) < abs($1.medianM - targetM) } ?? pool[0]
        } else {
            let nonTee = pool.filter { !clubIsTeeOnly(zhClubName($0.clubName)) }
            let candidates = nonTee.isEmpty ? pool : nonTee
            pick = candidates.max { $0.medianM < $1.medianM } ?? candidates[0]
        }
        return zhClubName(pick.clubName)
    }

    /// The club the player will hit NOW under the caddie's decision: the first step of the selected
    /// sequence (the tee/advance shot) when sequences exist, else the selected single-club option.
    private func recommendedClubName(from decision: CaddieDecisionResponse) -> String? {
        let sequences = CaddiePlanSequence.sequences(from: decision)
        let selectedId = CaddiePlanSequence.selectedSequenceId(from: decision) ?? decision.selectedOptionId
        if let sequence = sequences.first(where: { $0.id == selectedId }) ?? sequences.first,
           let firstClub = sequence.steps.first?.clubName, firstClub != "-" {
            return firstClub
        }
        let options = CaddiePlanOption.options(from: decision)
        let club = (options.first { $0.id == decision.selectedOptionId } ?? options.first)?.clubName
        return (club == nil || club == "-") ? nil : club
    }

    /// Adopt the caddie's recommended club as the selected club so the club strip highlight and the
    /// hole-map landing marker follow the recommendation (and change with strategy). No-op if the
    /// decision carries no usable club.
    @MainActor
    private func syncSelectedClubToRecommendation() {
        guard let decision = caddieDecision, let club = recommendedClubName(from: decision) else {
            return
        }
        selectedClub = zhClubName(club)
    }

    // MARK: - 球局调整(加打 / 减九洞 / 结束本场)— round-11 从首页移入实战屏

    /// 收在实战屏底部的折叠区:加打/减九洞 + 结束本场。控件与闭包与原首页一致。
    @ViewBuilder private var manageSection: some View {
        DisclosureGroup(isExpanded: $showManage) {
            VStack(spacing: 8) {
                nineControl
                loopAddControl
                if let live = liveRoundState, package.holes.contains(where: { $0.number == live.activeHole }) {
                    Button(role: .destructive) {
                        showDiscardConfirm = true
                    } label: {
                        Text("结束本场").font(.subheadline).frame(maxWidth: .infinity).padding(.vertical, 6)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Color(red: 185 / 255, green: 50 / 255, blue: 40 / 255))
                    .confirmationDialog("结束本场?未保存的记录会被丢弃。", isPresented: $showDiscardConfirm, titleVisibility: .visible) {
                        Button("结束本场", role: .destructive) { onDiscard() }
                        Button("取消", role: .cancel) {}
                    }
                }
            }
            .padding(.top, 8)
        } label: {
            Label("球局调整 · 加打 / 结束本场", systemImage: "slider.horizontal.3")
                .font(.subheadline).foregroundStyle(.secondary)
        }
        .liveCard()
    }

    /// 起始九洞的加打 / 撤销:nine 是对一局 18 洞的视图过滤,已记杆按 roundId 保留。
    @ViewBuilder private var nineControl: some View {
        if package.course.globalId != 0 {
            let currentNine = package.nine ?? "all"
            if currentNine != "all" {
                Button {
                    onChangeNine("all")
                } label: {
                    Label("＋加打另外 9 洞(凑 18)", systemImage: "plus.circle")
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .foregroundStyle(LiveHoleStyle.green)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.green))
                }
                .buttonStyle(.plain)
                .disabled(isPreparingRound)
            } else if let startingNine, startingNine != "all" {
                Button {
                    onChangeNine(startingNine)
                } label: {
                    Label("移除另外 9 洞 · 只打\(nineText(startingNine))", systemImage: "minus.circle")
                        .font(.subheadline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .foregroundStyle(.secondary)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.line))
                }
                .buttonStyle(.plain)
                .disabled(isPreparingRound)
            }
        }
    }

    private func nineText(_ nine: String) -> String {
        switch nine {
        case "front":
            return "前九"
        case "back":
            return "后九"
        default:
            return "全 18 洞"
        }
    }

    /// 当前局对应的 CourseView 选项(用 course.globalId 反查;组合局的 globalId = 前环)。
    private var activeCourseOption: MobileCourseOption? {
        courseOptions.first { $0.globalId == package.course.globalId }
    }

    /// 同球场可作为「另一个 9 洞」的环(9 洞、同球场),含当前环本身。按 A/B/C 排序。
    private var siblingLoops: [MobileCourseOption] {
        guard let venue = activeCourseOption?.venueName else { return [] }
        return courseOptions
            .filter { ($0.venueName ?? "") == venue
                && ($0.segmentHoles ?? $0.holes) == 9 }
            .sorted { ($0.segmentLabel ?? "~~") < ($1.segmentLabel ?? "~~") }
    }

    private func loopLabel(_ option: MobileCourseOption) -> String {
        if let label = option.segmentLabel, !label.isEmpty {
            return "\(label) 场"
        }
        return "另一个 9 洞"
    }

    @ViewBuilder private var loopAddControl: some View {
        // 仅进行中、且当前局是某球场的一个 9 洞环时显示。
        if liveRoundState != nil, let active = activeCourseOption, (active.segmentHoles ?? active.holes) == 9 {
            if package.holes.count <= 9 {
                if !siblingLoops.isEmpty {
                    // 单 9 洞环进行中 → 选另一个环加打凑 18(同一局,已记杆保留)。
                    Menu {
                        ForEach(siblingLoops) { loop in
                            Button("＋ \(loopLabel(loop)) · 凑 18 洞") {
                                onPrepareCompositeRound(package.course.globalId, loop.globalId, package.course.teeBox, package.roundId)
                            }
                        }
                    } label: {
                        Label("＋加打另一个 9 洞(凑 18)", systemImage: "plus.circle")
                            .font(.subheadline.weight(.semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .foregroundStyle(LiveHoleStyle.green)
                            .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.green))
                    }
                    .disabled(isPreparingRound)
                }
            } else {
                // 已是组合 18(两个 9 洞环)→ 移除加打的后 9,只打起始 9 洞(前 9 已记杆保留)。
                Button {
                    onPrepareCourseRound(package.course.globalId, package.roundId, package.course.teeBox, "all")
                } label: {
                    Label("移除加打的 9 洞 · 只打前 9", systemImage: "minus.circle")
                        .font(.subheadline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .foregroundStyle(.secondary)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.line))
                }
                .disabled(isPreparingRound)
            }
        }
    }

    private var holeToParText: String {
        let delta = score - hole.par
        return delta > 0 ? "+\(delta)" : "\(delta)"
    }

    private var recordHintText: String? {
        guard currentCoordinate != nil else { return "等待 GPS 定位…" }
        if let accuracy = currentHorizontalAccuracyM {
            return "已定位 · 精度 ±\(Int(accuracy.rounded()))m · 球杆 \(selectedClub)"
        }
        return "已定位 · 球杆 \(selectedClub)"
    }

    private var shotTypeOptions: [String] {
        let options = caddieContextSeed?.shotTypes ?? []
        return options.isEmpty ? ["tee", "approach", "recovery"] : options
    }

    private var lieOptions: [String] {
        ["fairway", "rough", "bunker", "green", "tee", "recovery"]
    }

    private var strategyModeOptions: [String] {
        ["protect_score", "stock", "attack"]
    }

    private func strategyModeLabel(_ mode: String) -> String {
        switch mode {
        case "protect_score":
            return "护分"
        case "attack":
            return "进攻"
        default:
            return "标准"
        }
    }

    /// 击球类型 / 球位的封闭英文枚举 → 中文(更多调整里的选择器)。未知值原样回退。
    private func zhShotType(_ value: String) -> String {
        switch value.lowercased() {
        case "tee":
            return "开球"
        case "approach":
            return "攻果岭"
        case "recovery":
            return "解围"
        case "layup":
            return "铺垫"
        case "putt":
            return "推杆"
        default:
            return value.capitalized
        }
    }

    private func zhLie(_ value: String) -> String {
        switch value.lowercased() {
        case "fairway":
            return "球道"
        case "rough":
            return "长草"
        case "bunker":
            return "沙坑"
        case "green":
            return "果岭"
        case "tee":
            return "发球台"
        case "recovery":
            return "解围"
        default:
            return value.capitalized
        }
    }

    private func makeCaddieDecisionRequest() -> CaddieDecisionRequest? {
        guard let caddieContextSeed else {
            return nil
        }
        return requestBuilder.makeDecisionRequest(
            seed: caddieContextSeed,
            input: LiveCaddieInput(
                shotType: selectedShotType,
                distanceToPinM: distanceToPinMetres,
                lie: selectedLie,
                coordinate: currentCoordinate,
                targetCoordinate: targetCoordinate,
                targetKind: targetCoordinate == nil ? nil : "pin",
                horizontalAccuracyM: currentHorizontalAccuracyM,
                strategyMode: selectedStrategyMode,
                visionFindings: visionFindings
            )
        )
    }

    @MainActor
    private func loadCaddieDecision(syncClub: Bool = false) async {
        guard let caddieClient else {
            caddieDecision = makeOfflineCaddieDecision()
            caddieErrorMessage = caddieDecision == nil
                ? "本洞暂无缓存的球童建议。"
                : "离线模式 · 使用已缓存的球局方案。"
            if syncClub { syncSelectedClubToRecommendation() }
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
            return
        }
        guard let request = makeCaddieDecisionRequest() else {
            caddieErrorMessage = "本洞缺少球童上下文,暂无法给建议。"
            sendWatchState(decision: nil, offlineOption: selectedOfflineOption)
            return
        }

        isLoadingCaddieDecision = true
        defer {
            isLoadingCaddieDecision = false
        }

        do {
            caddieDecision = try await caddieClient.fetchCaddieDecision(request, endpoint: package.caddieDecisionEndpoint)
            caddieErrorMessage = nil
            if syncClub { syncSelectedClubToRecommendation() }
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        } catch {
            if let offlineDecision = makeOfflineCaddieDecision() {
                caddieDecision = offlineDecision
                caddieErrorMessage = "联网球童暂不可用 · 已切换到离线缓存建议。"
            } else {
                caddieErrorMessage = "球童建议暂取不到 · 仍显示已缓存的方案。"
            }
            if syncClub { syncSelectedClubToRecommendation() }
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        }
    }

    private func makeOfflineCaddieDecision() -> CaddieDecisionResponse? {
        guard let caddieContextSeed,
              let request = makeCaddieDecisionRequest()
        else {
            return nil
        }
        return offlineDecisionEvaluator.makeDecision(
            seed: caddieContextSeed,
            request: request,
            strategyMode: selectedStrategyMode
        )
    }

    private var selectedOfflineOption: OfflineCaddieOption? {
        guard let seed = caddieContextSeed else {
            return nil
        }
        return offlineDecisionEvaluator.selectedOption(in: seed, strategyMode: selectedStrategyMode)
    }

    private func sendWatchState(decision: CaddieDecisionResponse?, offlineOption: OfflineCaddieOption?) {
        let state = watchBridge?.makeWatchRoundStatePayload(
            package: package,
            hole: hole,
            score: score,
            putts: puttCount,
            penaltyCount: penaltyCount,
            selectedClub: selectedClub,
            decision: decision,
            offlineOption: offlineOption,
            distanceToPinM: distanceToPinMetres,
            targetLatitude: targetCoordinate?.latitude,
            targetLongitude: targetCoordinate?.longitude,
            targetKind: targetCoordinate == nil ? nil : "pin"
        )
        if let state {
            try? watchBridge?.sendStateToWatch(state)
        }
    }

    private func applyRestoredStateIfNeeded(_ snapshot: LiveRoundStateSnapshot?) {
        guard let restoredHoleState = snapshot?.holeState(for: hole.number) else {
            return
        }
        guard lastAppliedRestoredHoleState?.hasSameRestorableFields(as: restoredHoleState) != true else {
            return
        }
        applyRestoredState(restoredHoleState)
    }

    private func applyRestoredState(_ restoredHoleState: LiveHoleStateSnapshot) {
        score = restoredHoleState.score
        puttCount = restoredHoleState.putts
        penaltyCount = restoredHoleState.penaltyCount
        // Normalise to the same zhClubName the picker uses (init does this) so the ClubStrip highlight matches.
        selectedClub = zhClubName(restoredHoleState.selectedClub)
        selectedShotType = restoredHoleState.selectedShotType
        selectedStrategyMode = restoredHoleState.selectedStrategyMode
        selectedLie = restoredHoleState.lie
        distanceToPinText = restoredHoleState.distanceToPinM.map(Self.yardsText(fromMetres:)) ?? ""
        if let latitude = restoredHoleState.latitude, let longitude = restoredHoleState.longitude {
            currentCoordinate = CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
        } else {
            currentCoordinate = nil
        }
        if let targetLatitude = restoredHoleState.targetLatitude, let targetLongitude = restoredHoleState.targetLongitude {
            targetCoordinate = CLLocationCoordinate2D(latitude: targetLatitude, longitude: targetLongitude)
        } else {
            targetCoordinate = nil
        }
        currentHorizontalAccuracyM = restoredHoleState.horizontalAccuracyM
        lastAppliedRestoredHoleState = restoredHoleState
        sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
    }

    private func submitEvents() {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        if let currentCoordinate {
            var locationPayload: [String: JSONValue] = [
                "latitude": .number(currentCoordinate.latitude),
                "longitude": .number(currentCoordinate.longitude),
                "source": .string("ios_gps"),
            ]
            if let currentHorizontalAccuracyM {
                locationPayload["horizontalAccuracyM"] = .number(currentHorizontalAccuracyM)
            }
            if let targetCoordinate {
                locationPayload["targetLatitude"] = .number(targetCoordinate.latitude)
                locationPayload["targetLongitude"] = .number(targetCoordinate.longitude)
                locationPayload["targetSource"] = .string("ios_target")
                locationPayload["targetKind"] = .string("pin")
            }
            emit(kind: .location, timestamp: timestamp, payload: locationPayload)
        }
        emit(kind: .score, timestamp: timestamp, payload: ["strokes": .number(Double(score))])
        emit(kind: .putt, timestamp: timestamp, payload: ["putts": .number(Double(puttCount))])
        emit(kind: .penalty, timestamp: timestamp, payload: ["penalties": .number(Double(penaltyCount))])
        emit(kind: .club, timestamp: timestamp, payload: clubEventPayload())
        if !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            emit(kind: .note, timestamp: timestamp, payload: ["note": .string(note)])
        }
        sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
    }

    private func clubEventPayload() -> [String: JSONValue] {
        var payload: [String: JSONValue] = [
            "clubName": .string(selectedClub),
            "shotType": .string(selectedShotType),
            "strategyMode": .string(selectedStrategyMode),
            "lie": .string(selectedLie),
        ]
        payload["distanceToPinM"] = distanceToPinPayload()
        if let selectedOfflineOptionId = selectedOfflineOption?.optionId ?? caddieContextSeed?.selectedOfflineOptionId {
            payload["offlineOptionId"] = .string(selectedOfflineOptionId)
        }
        if let decision = caddieDecision {
            if let decisionId = decision.decisionId {
                payload["decisionId"] = .string(decisionId)
            }
            payload["decision"] = .object(decision.auditPayload)
            payload["actualShot"] = .object(actualShotPayload())
        }
        if caddieDecision == nil {
            payload["actualShot"] = .object(actualShotPayload())
        }
        return payload
    }

    private func distanceToPinPayload() -> JSONValue {
        guard let metres = distanceToPinMetres else {
            return .null
        }
        return .number(metres)
    }

    private func actualShotPayload() -> [String: JSONValue] {
        var payload: [String: JSONValue] = [
            "clubName": .string(selectedClub),
            "shotOrder": .number(1),
            "end": .object(["lie": .string(selectedLie)]),
        ]
        if let metres = distanceToPinMetres {
            payload["remainingToTarget_m"] = .number(metres)
        }
        if let currentCoordinate {
            payload["position"] = .object([
                "latitude": .number(currentCoordinate.latitude),
                "longitude": .number(currentCoordinate.longitude),
            ])
        }
        if let targetCoordinate {
            payload["targetPosition"] = .object([
                "latitude": .number(targetCoordinate.latitude),
                "longitude": .number(targetCoordinate.longitude),
                "kind": .string("pin"),
            ])
        }
        if let currentHorizontalAccuracyM {
            payload["horizontalAccuracyM"] = .number(currentHorizontalAccuracyM)
        }
        return payload
    }

    private func emit(kind: LiveRoundEventKind, timestamp: String, payload: [String: JSONValue]) {
        onEvent(
            LiveRoundEvent(
                eventId: UUID().uuidString,
                roundId: package.roundId,
                timestamp: timestamp,
                hole: hole.number,
                kind: kind,
                payload: payload
            )
        )
    }

    /// 到旗杆距离在 UI 里以「码」输入/显示;后端事件/球童请求用米,这里在边界换算回米。
    private var distanceToPinMetres: Double? {
        guard let yards = Double(distanceToPinText.trimmingCharacters(in: .whitespacesAndNewlines)) else {
            return nil
        }
        return CoursePrepRoute.metres(fromYards: yards)
    }

    /// 后端存的米 → 前端显示的整码(恢复已记距离时用)。
    private static func yardsText(fromMetres metres: Double) -> String {
        String(CoursePrepRoute.yards(fromMetres: metres))
    }
}
