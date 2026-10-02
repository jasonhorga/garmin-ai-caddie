import Foundation
import SwiftUI

/// The 球包 state and its intents, outside the view so the transitions are testable. Every intent
/// saves on the device at once and hands the whole manual bag to the long-lived
/// `ClubBagSyncCoordinator`, which owns the backend write — leaving the screen never drops an edit.
@MainActor
final class ClubBagEditorModel: ObservableObject {
    let clubProfiles: [ClubProfile]
    let sync: ClubBagSyncCoordinator
    @Published private(set) var bag: Set<String>
    @Published private(set) var distancesYd: [String: Int]

    init(clubProfiles: [ClubProfile], sync: ClubBagSyncCoordinator) {
        self.clubProfiles = clubProfiles
        self.sync = sync
        // Manual override wins; else the cached real Garmin bag; else derive from shot history.
        bag = ClubBagStore.bag() ?? ClubBagStore.realBag() ?? Self.historyBag(clubProfiles)
        distancesYd = ClubBagStore.manualDistancesYd()
    }

    var rows: [BagPresentation.Row] {
        BagPresentation.rows(bag: bag, profiles: clubProfiles, manual: distancesYd)
    }

    func row(named name: String) -> BagPresentation.Row? {
        rows.first { $0.name == name }
    }

    var addable: [CatalogClub] { BagPresentation.addable(bag: bag) }

    /// Edits wait for the cloud restore (see `ClubBagSyncCoordinator.canEdit`): a whole-bag PUT
    /// built on a partial local bag would erase the clubs and carries saved from another phone.
    var canEdit: Bool { sync.canEdit }

    func add(_ name: String) {
        guard canEdit, ClubCatalog.names.contains(name), name != "推杆", !bag.contains(name) else { return }
        bag.insert(name)
        commit()
    }

    /// The bag keeps at least one club to hit with: the server stores "no manual bag" for an empty
    /// list, so an empty roster cannot be saved — 用 Garmin 球包重置 is the way back.
    func canRemove(_ name: String) -> Bool {
        bag.contains(name) && !bag.subtracting([name, "推杆"]).isEmpty
    }

    /// Taking a club out also drops its typed distance.
    func remove(_ name: String) {
        guard canEdit, canRemove(name) else { return }
        bag.remove(name)
        distancesYd[name] = nil
        commit()
    }

    func setDistance(_ name: String, _ yards: Int?) {
        guard canEdit else { return }
        distancesYd[name] = yards.flatMap { $0 > 0 ? $0 : nil }
        commit()
    }

    /// − / ＋ from the distance in use; a club with none starts from 100 yards.
    func step(_ name: String, by delta: Int) {
        let current = row(named: name)?.median ?? 100
        setDistance(name, max(1, current + delta))
    }

    /// 用 Garmin 球包重置, one intent: drop the manual selection AND the typed distances on the
    /// device, show the Garmin bag, and clear the server's manual bag (`{"clubs": []}`) through the
    /// same durable outbox as every edit — so a later edit simply supersedes it.
    func resetToGarminBag() {
        guard canEdit else { return }
        ClubBagStore.clearManual()
        ClubBagStore.saveManualDistancesYd([:])
        distancesYd = [:]
        bag = ClubBagStore.realBag() ?? Self.historyBag(clubProfiles)
        sync.enqueue([])
    }

    /// A freshly fetched Garmin bag is shown only while there is no manual selection.
    func applyRealBag(_ names: Set<String>) {
        if ClubBagStore.bag() == nil { bag = names }
    }

    /// Re-read the bound player's store (after the cloud bag was restored).
    func reloadFromStore() {
        bag = ClubBagStore.bag() ?? ClubBagStore.realBag() ?? Self.historyBag(clubProfiles)
        distancesYd = ClubBagStore.manualDistancesYd()
    }

    private func commit() {
        ClubBagStore.save(bag)
        ClubBagStore.saveManualDistancesYd(distancesYd)
        sync.enqueue(ClubBagStore.manualClubInputs(selected: bag, distancesYd: distancesYd))
    }

    private static func historyBag(_ profiles: [ClubProfile]) -> Set<String> {
        Set(profiles.compactMap { profile -> String? in
            let name = zhClubName(profile.clubName.trimmingCharacters(in: .whitespaces))
            return ClubCatalog.names.contains(name) ? name : nil
        })
    }
}

/// 球包 (B5c, README §9, `stats.html` 3): the distance ladder that replaces 成绩 → 球杆 and the old
/// 球杆设置 checklist. Each club is a p10–p90 bar with its median and the gap to the next club; tap a
/// club to set the distance the caddie uses or take it out of the bag; "＋ 球杆" adds one.
public struct ClubSettingsView: View {
    public let apiBaseURL: URL?
    public let adminToken: String?
    @StateObject private var model: ClubBagEditorModel
    @ObservedObject private var sync: ClubBagSyncCoordinator
    @State private var editingName: String?
    @State private var isAdding: Bool
    @State private var didLoadRealBag = false
    private let fetchesRealBag: Bool

    public init(clubProfiles: [ClubProfile] = [], apiBaseURL: URL? = nil, adminToken: String? = nil) {
        self.init(clubProfiles: clubProfiles, apiBaseURL: apiBaseURL, adminToken: adminToken, sync: .shared)
    }

    /// Injected storage/sync for tests and design snapshots; `editing`/`adding` open the real sheets.
    init(
        clubProfiles: [ClubProfile],
        apiBaseURL: URL?,
        adminToken: String?,
        sync: ClubBagSyncCoordinator,
        editing: String? = nil,
        adding: Bool = false,
        fetchesRealBag: Bool = true
    ) {
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        _model = StateObject(wrappedValue: ClubBagEditorModel(clubProfiles: clubProfiles, sync: sync))
        _sync = ObservedObject(wrappedValue: sync)
        _editingName = State(initialValue: editing)
        _isAdding = State(initialValue: adding)
        self.fetchesRealBag = fetchesRealBag
    }

    public var body: some View {
        ScrollView {
            // While this phone has not yet read the player's cloud bag, 球包 is an explicitly
            // view-only ladder: a 只能查看 card says so (and offers 重新读取 after a failed read),
            // there is no ＋, no reset, and rows do not open the editor. Sync progress itself lives
            // in 设置 → 球包同步 (README: no process status on business screens).
            if !sync.canEdit {
                BagViewOnlyCard(onReload: sync.restoreState == .failed ? { sync.retryNow() } : nil)
                    .padding(.horizontal, 14)
                    .padding(.top, 14)
            }
            BagContent(rows: model.rows,
                       onSelect: sync.canEdit ? { editingName = $0.name } : nil,
                       onReset: sync.canEdit && (apiBaseURL != nil || ClubBagStore.realBag() != nil)
                           ? { model.resetToGarminBag() } : nil)
        }
        .refreshable {
            if await sync.restoreFromServer() { model.reloadFromStore() }
        }
        .background(HubStyle.grouped)
        .navigationTitle("球包")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                if sync.canEdit {
                    Button("＋ 球杆") { isAdding = true }
                        .accessibilityIdentifier("bag-add")
                }
            }
        }
        .onChange(of: sync.restoreState) { _, state in
            // A restore started elsewhere (launch, foreground) landed while this screen is open.
            if state == .restored { model.reloadFromStore() }
        }
        .sheet(isPresented: Binding(get: { editingName != nil }, set: { if !$0 { editingName = nil } })) {
            if let name = editingName, let row = model.row(named: name) {
                BagClubEditor(
                    row: row,
                    canEdit: sync.canEdit,
                    canRemove: model.canRemove(name),
                    onStep: { model.step(name, by: $0) },
                    onUseHistory: { model.setDistance(name, nil) },
                    onRemove: { model.remove(name); editingName = nil }
                )
                .presentationDetents([.medium])
            }
        }
        .sheet(isPresented: $isAdding) {
            BagAddClubSheet(clubs: model.addable) { name in
                model.add(name)
                isAdding = false
            }
        }
        .task {
            sync.configure(apiBaseURL: apiBaseURL, adminToken: adminToken)
            // Restore this player's cloud bag (another phone, a reinstall) before it is edited here.
            if fetchesRealBag, await sync.restoreFromServer() {
                model.reloadFromStore()
            }
            await loadRealBag()
        }
    }

    /// Fetch the real Garmin bag once; it becomes the default while the player has no manual bag.
    private func loadRealBag() async {
        guard fetchesRealBag, !didLoadRealBag else { return }
        didLoadRealBag = true
        guard let names = await refreshRealClubBag(apiBaseURL: apiBaseURL, adminToken: adminToken) else { return }
        model.applyRealBag(names)
    }
}

/// The ladder for given rows (no ScrollView, so the CI snapshots render it).
struct BagContent: View {
    let rows: [BagPresentation.Row]
    /// `nil`: a read-only ladder (rows do not open the editor).
    var onSelect: ((BagPresentation.Row) -> Void)? = { _ in }
    var onReset: (() -> Void)? = nil

    private static let barColor = Color(red: 92 / 255, green: 196 / 255, blue: 127 / 255)

    var body: some View {
        let axis = BagPresentation.axis(rows)
        VStack(alignment: .leading, spacing: 10) {
            Text(BagPresentation.summary(rows))
                .font(.footnote).foregroundStyle(.secondary)
            VStack(spacing: 0) {
                if let axis {
                    axisRow(axis)
                }
                ForEach(Array(rows.enumerated()), id: \.element.id) { index, row in
                    if index > 0, let gap = BagPresentation.gap(rows[index - 1], row) {
                        Text(gap.text)
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(gap.isFlagged ? HubStyle.bogey : Color.secondary)
                            .fontWeight(gap.isFlagged ? .semibold : .regular)
                            .frame(maxWidth: .infinity, alignment: .center)
                            .padding(.vertical, 2)
                            .accessibilityIdentifier("bag-gap-\(row.name)")
                    }
                    Button { onSelect?(row) } label: { ladderRow(row, axis: axis) }
                        .buttonStyle(.plain)
                        .disabled(onSelect == nil)
                        .accessibilityIdentifier("bag-club-\(row.name)")
                }
            }
            .hubCard(padding: 12)
            if let onReset {
                Button(action: onReset) {
                    Label("用 Garmin 球包重置", systemImage: "arrow.clockwise")
                        .font(.subheadline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                }
                .buttonStyle(.plain)
                .foregroundStyle(LiveHoleStyle.green)
                .hubCard()
            }
        }
        .padding(14)
    }

    private static let nameWidth: CGFloat = 78
    private static let valueWidth: CGFloat = 44

    private func axisRow(_ axis: ClosedRange<Int>) -> some View {
        HStack(spacing: 8) {
            Color.clear.frame(width: Self.nameWidth, height: 14)
            GeometryReader { geo in
                ForEach(BagPresentation.ticks(axis), id: \.self) { tick in
                    Text("\(tick)")
                        .font(.system(size: 10).monospacedDigit())
                        .foregroundStyle(.secondary)
                        .position(x: geo.size.width * fraction(tick, axis), y: 7)
                }
            }
            .frame(height: 14)
            Text("码").font(.system(size: 10)).foregroundStyle(.secondary)
                .frame(width: Self.valueWidth, alignment: .trailing)
        }
        .padding(.bottom, 4)
    }

    private func ladderRow(_ row: BagPresentation.Row, axis: ClosedRange<Int>?) -> some View {
        HStack(spacing: 8) {
            Text(row.name).font(.subheadline.weight(.semibold)).lineLimit(1).minimumScaleFactor(0.8)
                .frame(width: Self.nameWidth, alignment: .leading)
            GeometryReader { geo in
                let width = geo.size.width
                ZStack(alignment: .leading) {
                    Rectangle().fill(Color.primary.opacity(0.08)).frame(height: 1)
                    if let axis, let p10 = row.p10, let p90 = row.p90 {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Self.barColor.opacity(0.55))
                            .frame(width: max(width * (fraction(p90, axis) - fraction(p10, axis)), 2), height: 10)
                            .offset(x: width * fraction(p10, axis))
                    }
                    if let axis, let median = row.median {
                        if row.isManual {
                            Circle().fill(Color.primary).frame(width: 10, height: 10)
                                .overlay { Circle().stroke(Color.white, lineWidth: 2) }
                                .offset(x: width * fraction(median, axis) - 5)
                        } else {
                            RoundedRectangle(cornerRadius: 1).fill(Color.primary)
                                .frame(width: 2, height: 14)
                                .offset(x: width * fraction(median, axis) - 1)
                        }
                    }
                }
                .frame(height: geo.size.height)
            }
            .frame(height: 16)
            Text(row.median.map(String.init) ?? "—")
                .font(.subheadline.monospacedDigit().weight(.bold))
                .foregroundStyle(row.median == nil ? Color.secondary : Color.primary)
                .frame(width: Self.valueWidth, alignment: .trailing)
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
    }

    private func fraction(_ value: Int, _ axis: ClosedRange<Int>) -> CGFloat {
        let span = CGFloat(axis.upperBound - axis.lowerBound)
        guard span > 0 else { return 0 }
        return min(max(CGFloat(value - axis.lowerBound) / span, 0), 1)
    }
}

/// Tap a club: its history, the distance the caddie uses (− / ＋, or back to the history median),
/// and 从球包拿掉.
struct BagClubEditor: View {
    let row: BagPresentation.Row
    var canEdit = true
    var canRemove = true
    var onStep: (Int) -> Void
    var onUseHistory: () -> Void
    var onRemove: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(row.name).font(.title3.weight(.bold))
                Spacer()
                Button("完成") { dismiss() }.accessibilityIdentifier("bag-edit-done")
            }
            Text(BagPresentation.historyText(row)).font(.footnote.monospacedDigit()).foregroundStyle(.secondary)
            HStack {
                Text("算球童建议时用").font(.subheadline)
                Spacer()
                Button { onStep(-1) } label: { Image(systemName: "minus").frame(width: 36, height: 32) }
                    .accessibilityIdentifier("bag-edit-minus")
                Text(row.median.map { "\($0) 码" } ?? "—")
                    .font(.headline.monospacedDigit())
                    .frame(minWidth: 64)
                    .accessibilityIdentifier("bag-edit-value")
                Button { onStep(1) } label: { Image(systemName: "plus").frame(width: 36, height: 32) }
                    .accessibilityIdentifier("bag-edit-plus")
            }
            .buttonStyle(.bordered)
            .disabled(!canEdit)
            if row.isManual, row.historyMedian != nil {
                Button("用历史中位数", action: onUseHistory)
                    .font(.subheadline)
                    .accessibilityIdentifier("bag-edit-reset")
                    .disabled(!canEdit)
            }
            Spacer(minLength: 0)
            Button(role: .destructive, action: onRemove) {
                Text("从球包拿掉").font(.headline).frame(maxWidth: .infinity).padding(.vertical, 12)
            }
            .buttonStyle(.bordered)
            .disabled(!(canEdit && canRemove))
            .accessibilityIdentifier("bag-edit-remove")
            if !canRemove {
                Text("球包里至少留一支能打的球杆；要换回 Garmin 球包请用重置")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(20)
    }
}

/// "＋ 球杆": the catalog clubs not in the bag, grouped like Garmin's club setup.
struct BagAddClubSheet: View {
    let clubs: [CatalogClub]
    var onAdd: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                ForEach(ClubCategory.allCases, id: \.self) { category in
                    let inCategory = clubs.filter { $0.category == category }
                    if !inCategory.isEmpty {
                        Section(category.rawValue) {
                            ForEach(inCategory) { club in
                                Button(club.zhName) { onAdd(club.zhName) }
                                    .foregroundStyle(.primary)
                            }
                        }
                    }
                }
            }
            .navigationTitle("加一支球杆")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
            }
        }
    }
}

/// The view-only state of 球包 as a product state, not a progress message: what the player can do
/// now (look, not change) and, after a failed read, the one action that changes it.
struct BagViewOnlyCard: View {
    var onReload: (() -> Void)?

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: "lock.fill")
                .font(.title3)
                .foregroundStyle(.secondary)
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text("暂时只能查看").font(.subheadline.weight(.semibold))
                Text("拿到你账号里的球包后就能改距离、加减球杆")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            if let onReload {
                Button("重新读取", action: onReload)
                    .font(.subheadline.weight(.semibold))
                    .buttonStyle(.bordered)
                    .tint(LiveHoleStyle.green)
                    .accessibilityIdentifier("bag-reload")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .hubCard(padding: 12)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("bag-view-only")
    }
}

/// 设置 → 球包同步: the only place 球包 sync state is shown (README §… no process status on
/// business screens). Nothing pending → "已同步"; otherwise what is waiting and a retry.
struct ClubBagSyncSettingsRow: View {
    @ObservedObject var sync: ClubBagSyncCoordinator

    var body: some View {
        HStack {
            Label("球包同步", systemImage: "arrow.triangle.2.circlepath")
            Spacer()
            Text(Self.text(
                status: sync.status, restore: sync.restoreState, canEdit: sync.canEdit,
                hasBackend: sync.hasBackend, synced: ClubBagStore.hasSyncedWithCloud
            ))
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.trailing)
        }
        .accessibilityIdentifier("settings-bag-sync")
        if Self.canRetry(status: sync.status, restore: sync.restoreState) {
            Button("重新同步球包") { sync.retryNow() }
                .foregroundStyle(LiveHoleStyle.green)
                .accessibilityIdentifier("settings-bag-sync-retry")
        }
    }

    static func text(
        status: ClubBagSyncCoordinator.Status,
        restore: ClubBagSyncCoordinator.RestoreState,
        canEdit: Bool,
        hasBackend: Bool = true,
        synced: Bool = true
    ) -> String {
        switch status {
        case .rejected(let code) where code == 401 || code == 403:
            return "云端没接受上次保存（\(code)），重新登录后重试"
        case .rejected(let code):
            return "云端没接受上次保存（\(code)）"
        case .failed:
            return "上传失败，正在自动重试"
        case .pending, .syncing:
            return "等待上传"
        case .idle:
            break
        }
        switch restore {
        case .restoring: return "正在读取云端球包"
        case .failed where !canEdit: return "还没读到云端球包，读到后才能修改"
        case .failed: return "读取云端球包失败"
        case .restored: return "已同步"
        // Nothing has been read this session: only claim 已同步 when this phone has matched the
        // cloud before.
        case .unknown where !hasBackend: return "只保存在这台手机上"
        case .unknown: return synced ? "已同步" : "还没读取云端球包"
        }
    }

    static func canRetry(status: ClubBagSyncCoordinator.Status, restore: ClubBagSyncCoordinator.RestoreState) -> Bool {
        if case .rejected = status { return true }
        return status == .failed || restore == .failed
    }
}
