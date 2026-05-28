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
        self.offlineStore = offlineStore
        self.watchBridge = watchBridge
        self.liveRoundState = liveRoundState
        let seed = package.caddieContextSeeds.first { $0.hole == hole.number }
        let restoredHoleState = liveRoundState?.holeState(for: hole.number)
        self._score = State(initialValue: restoredHoleState?.score ?? hole.par)
        self._puttCount = State(initialValue: restoredHoleState?.putts ?? 2)
        self._penaltyCount = State(initialValue: restoredHoleState?.penaltyCount ?? 0)
        self._selectedClub = State(initialValue: restoredHoleState?.selectedClub ?? package.clubProfiles.first?.clubName ?? "")
        self._selectedShotType = State(initialValue: restoredHoleState?.selectedShotType ?? seed?.shotTypes.first ?? "approach")
        self._selectedStrategyMode = State(initialValue: restoredHoleState?.selectedStrategyMode ?? "stock")
        self._distanceToPinText = State(initialValue: restoredHoleState?.distanceToPinM.map(Self.distanceText) ?? "")
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
        Form {
            Section {
                HStack {
                    Text("Hole \(hole.number)")
                        .font(.title3.weight(.semibold))
                    Spacer()
                    Text("Par \(hole.par)")
                        .foregroundStyle(.secondary)
                }
                if let caddieDecision {
                    CaddiePlanView(response: caddieDecision)
                } else {
                    CaddiePlanView(seed: caddieContextSeed)
                }
                if isLoadingCaddieDecision {
                    ProgressView("Updating caddie")
                }
                if let caddieErrorMessage {
                    Text(caddieErrorMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Button {
                    Task {
                        await loadCaddieDecision()
                    }
                } label: {
                    Label("Refresh caddie", systemImage: "arrow.clockwise")
                }
                .disabled(isLoadingCaddieDecision)
            }

            Section("Input") {
                Picker("Shot", selection: $selectedShotType) {
                    ForEach(shotTypeOptions, id: \.self) { shotType in
                        Text(shotType.capitalized).tag(shotType)
                    }
                }
                Picker("Strategy", selection: $selectedStrategyMode) {
                    ForEach(strategyModeOptions, id: \.self) { mode in
                        Text(strategyModeLabel(mode)).tag(mode)
                    }
                }
                TextField("Distance m", text: $distanceToPinText)
                    .keyboardType(.decimalPad)
                Button {
                    targetCoordinate = currentCoordinate
                } label: {
                    Label("Set target", systemImage: "mappin.and.ellipse")
                }
                .disabled(currentCoordinate == nil)
                Picker("Lie", selection: $selectedLie) {
                    ForEach(lieOptions, id: \.self) { lie in
                        Text(lie.capitalized).tag(lie)
                    }
                }
                Stepper("Score \(score)", value: $score, in: 1...12)
                Stepper("Putts \(puttCount)", value: $puttCount, in: 0...6)
                Stepper("Penalty \(penaltyCount)", value: $penaltyCount, in: 0...4)
                Picker("Club", selection: $selectedClub) {
                    ForEach(package.clubProfiles) { club in
                        Text(club.clubName).tag(club.clubName)
                    }
                }
                TextField("Note", text: $note)
                Button {
                    submitEvents()
                } label: {
                    Label("Save", systemImage: "checkmark.circle")
                }
            }

            Section("Media") {
                MediaCaptureView(
                    roundId: package.roundId,
                    hole: hole.number,
                    targetId: caddieContextSeed?.sourceRef ?? "\(package.roundId):\(hole.number)",
                    offlineStore: offlineStore,
                    uploadClient: mediaUploadClient,
                    onEvent: onEvent,
                    onVisionFindings: { findings in
                        visionFindings = findings
                        Task {
                            await loadCaddieDecision()
                        }
                    }
                )
            }
        }
        .navigationTitle("Hole \(hole.number)")
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
        .onChange(of: liveRoundState) { _, newState in
            applyRestoredStateIfNeeded(newState)
        }
    }

    private var caddieContextSeed: CaddieContextSeed? {
        package.caddieContextSeeds.first { $0.hole == hole.number }
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
            return "Protect"
        case "attack":
            return "Attack"
        default:
            return "Stock"
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
                distanceToPinM: Double(distanceToPinText),
                lie: selectedLie,
                coordinate: currentCoordinate,
                targetCoordinate: targetCoordinate,
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
            distanceToPinM: Double(distanceToPinText.trimmingCharacters(in: .whitespacesAndNewlines)),
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
        distanceToPinText = restoredHoleState.distanceToPinM.map(Self.distanceText) ?? ""
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
        guard let distanceToPin = Double(distanceToPinText.trimmingCharacters(in: .whitespacesAndNewlines)) else {
            return .null
        }
        return .number(distanceToPin)
    }

    private func actualShotPayload() -> [String: JSONValue] {
        var payload: [String: JSONValue] = [
            "clubName": .string(selectedClub),
            "shotOrder": .number(1),
            "end": .object(["lie": .string(selectedLie)]),
        ]
        if let distanceToPin = Double(distanceToPinText) {
            payload["remainingToTarget_m"] = .number(distanceToPin)
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

    private static func distanceText(_ value: Double) -> String {
        if value.rounded(.towardZero) == value {
            return String(Int(value))
        }
        return String(value)
    }
}
