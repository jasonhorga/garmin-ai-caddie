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

    public init(
        package: LiveRoundPackage,
        hole: Hole,
        caddieBaseURL: URL? = nil,
        adminToken: String? = nil,
        caddieClient: CaddieDecisionClient? = nil,
        offlineStore: OfflineStore? = nil,
        watchBridge: WatchEventBridge? = nil,
        liveRoundState: LiveRoundStateSnapshot? = nil,
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
        let seed = package.caddieContextSeeds.first { $0.hole == hole.number }
        let restoredHoleState = liveRoundState?.holeState(for: hole.number)
        self._score = State(initialValue: restoredHoleState?.score ?? hole.par)
        self._puttCount = State(initialValue: restoredHoleState?.putts ?? 2)
        self._penaltyCount = State(initialValue: restoredHoleState?.penaltyCount ?? 0)
        self._selectedClub = State(initialValue: zhClubName(restoredHoleState?.selectedClub ?? package.clubProfiles.first?.clubName ?? ""))
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
                        Text("球童建议 · \(strategyModeLabel(selectedStrategyMode))")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(LiveHoleStyle.green)
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
                        Text("选球杆").font(.caption).foregroundStyle(.secondary)
                        ClubStripView(clubs: clubNames, selected: selectedClub) { selectedClub = $0 }
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
                            Picker("策略", selection: $selectedStrategyMode) {
                                ForEach(strategyModeOptions, id: \.self) { Text(strategyModeLabel($0)).tag($0) }
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
            await loadCaddieDecision()
        }
        .task(id: hole.number) {
            await loadHoleMap()
        }
        .onChange(of: liveRoundState) { _, newState in
            applyRestoredStateIfNeeded(newState)
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
    /// Player's clubs from the backend (real bag): normalized to clear Chinese names (zhClubName),
    /// deduped (keep the most-sampled profile per club), filtered by lie (no 一号木 off the tee),
    /// and ordered longest→shortest. Drops empty/"Unknown".
    private var clubNames: [String] {
        var best: [String: ClubProfile] = [:]
        for profile in package.clubProfiles {
            let raw = profile.clubName.trimmingCharacters(in: .whitespaces)
            guard !raw.isEmpty, raw.lowercased() != "unknown" else { continue }
            let name = zhClubName(raw)
            if clubIsTeeOnly(name), selectedLie != "tee" { continue }
            if let existing = best[name], existing.sampleSize >= profile.sampleSize { continue }
            best[name] = profile
        }
        // Only the 3 clubs most relevant to THIS shot: nearest to the to-pin distance when known
        // (so a 150-yard approach never offers chip/putt), else the 3 longest. Always keep the
        // currently-selected club visible so the highlight isn't lost.
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

    /// The selected club's typical distance (metres) from the bag model — drives the live map marker.
    private var selectedClubMetres: Double? {
        guard let profile = package.clubProfiles.first(where: { zhClubName($0.clubName) == selectedClub }) else {
            return nil
        }
        return profile.medianM
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
    private func loadCaddieDecision() async {
        guard let caddieClient else {
            caddieDecision = makeOfflineCaddieDecision()
            caddieErrorMessage = caddieDecision == nil
                ? "No cached caddie decision is available for this hole."
                : "Offline caddie using cached package."
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
            return
        }
        guard let request = makeCaddieDecisionRequest() else {
            caddieErrorMessage = "No caddie context seed for this hole."
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
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        } catch {
            if let offlineDecision = makeOfflineCaddieDecision() {
                caddieDecision = offlineDecision
                caddieErrorMessage = "Network caddie unavailable. Using cached offline decision."
            } else {
                caddieErrorMessage = "Caddie decision unavailable. Cached plan remains visible."
            }
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
        selectedClub = restoredHoleState.selectedClub
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
