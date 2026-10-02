import Foundation
import SwiftUI

/// 球包 (B5c, README §9, `stats.html` 3): the distance ladder that replaces 成绩 → 球杆 and the old
/// 球杆设置 checklist. Each club is a p10–p90 bar with its median and the gap to the next club; tap a
/// club to set the distance the caddie uses or take it out of the bag; "＋ 球杆" adds one. Every change
/// is saved on the device at once and pushed to the backend manual bag (which the caddie reads).
public struct ClubSettingsView: View {
    public let clubProfiles: [ClubProfile]
    public let apiBaseURL: URL?
    public let adminToken: String?
    @State private var bag: Set<String>
    @State private var didLoadRealBag = false
    @State private var distancesYd: [String: Int] = ClubBagStore.manualDistancesYd()
    @State private var editing: BagPresentation.Row?
    @State private var isAdding = false
    /// Bumped on every change; the latest one is pushed after a short pause.
    @State private var revision = 0
    @State private var syncFailed = false

    public init(clubProfiles: [ClubProfile] = [], apiBaseURL: URL? = nil, adminToken: String? = nil) {
        self.clubProfiles = clubProfiles
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        let derived = Set(clubProfiles.compactMap { profile -> String? in
            let name = zhClubName(profile.clubName.trimmingCharacters(in: .whitespaces))
            return ClubCatalog.names.contains(name) ? name : nil
        })
        // Manual override wins; else the cached real Garmin bag; else derive from shot history.
        _bag = State(initialValue: ClubBagStore.bag() ?? ClubBagStore.realBag() ?? derived)
    }

    public var body: some View {
        let rows = BagPresentation.rows(bag: bag, profiles: clubProfiles, manual: distancesYd)
        ScrollView {
            BagContent(rows: rows, syncFailed: syncFailed, onSelect: { editing = $0 },
                       onReset: (apiBaseURL != nil || ClubBagStore.realBag() != nil) ? resetToGarminBag : nil)
        }
        .background(HubStyle.grouped)
        .navigationTitle("球包")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("＋ 球杆") { isAdding = true }
                    .accessibilityIdentifier("bag-add")
            }
        }
        .sheet(item: $editing) { row in
            BagClubEditor(
                row: row,
                onSet: { setDistance(row.name, $0) },
                onRemove: { remove(row.name); editing = nil }
            )
            .presentationDetents([.medium])
        }
        .sheet(isPresented: $isAdding) {
            BagAddClubSheet(clubs: BagPresentation.addable(bag: bag)) { name in
                add(name)
                isAdding = false
            }
        }
        .task { await loadRealBag() }
        .task(id: revision) {
            guard revision > 0 else { return }
            try? await Task.sleep(nanoseconds: 800_000_000)
            guard !Task.isCancelled else { return }
            await saveToBackend()
        }
    }

    /// Fetch the real Garmin bag once. If the player hasn't changed their bag here, use the real bag
    /// so the default reflects what they actually carry — with real names.
    private func loadRealBag() async {
        guard !didLoadRealBag else { return }
        didLoadRealBag = true
        guard let names = await refreshRealClubBag(apiBaseURL: apiBaseURL, adminToken: adminToken) else { return }
        if ClubBagStore.bag() == nil {
            bag = names
        }
    }

    /// Drop the manual bag and snap back to the real Garmin bag (re-fetched if possible, else the
    /// cached copy).
    private func resetToGarminBag() {
        ClubBagStore.clearManual()
        Task {
            if let names = await refreshRealClubBag(apiBaseURL: apiBaseURL, adminToken: adminToken) {
                bag = names
            } else if let cached = ClubBagStore.realBag() {
                bag = cached
            }
        }
    }

    private func setDistance(_ name: String, _ yards: Int?) {
        distancesYd[name] = yards.flatMap { $0 > 0 ? $0 : nil }
        ClubBagStore.saveManualDistancesYd(distancesYd)
        if let row = editing, row.name == name {
            editing = BagPresentation.rows(bag: bag, profiles: clubProfiles, manual: distancesYd).first { $0.name == name }
        }
        revision += 1
    }

    private func remove(_ name: String) {
        bag.remove(name)
        ClubBagStore.save(bag)
        revision += 1
    }

    private func add(_ name: String) {
        bag.insert(name)
        ClubBagStore.save(bag)
        revision += 1
    }

    /// PUT the bag (token + yards→metres) to `/api/v2/players/me/clubs/bag`, which the caddie reads.
    /// The device copy is already saved; a failure is shown and retried on the next change.
    private func saveToBackend() async {
        guard let apiBaseURL else { return }
        let client = SyncClient(baseURL: apiBaseURL, adminToken: adminToken)
        let inputs = ClubBagStore.manualClubInputs(selected: bag, distancesYd: distancesYd)
        do {
            _ = try await client.putManualClubBag(clubs: inputs)
            syncFailed = false
        } catch {
            if !Task.isCancelled { syncFailed = true }
        }
    }
}

/// The ladder for given rows (no ScrollView, so the CI snapshots render it).
struct BagContent: View {
    let rows: [BagPresentation.Row]
    var syncFailed = false
    var onSelect: (BagPresentation.Row) -> Void = { _ in }
    var onReset: (() -> Void)? = nil

    private static let barColor = Color(red: 92 / 255, green: 196 / 255, blue: 127 / 255)

    var body: some View {
        let axis = BagPresentation.axis(rows)
        VStack(alignment: .leading, spacing: 10) {
            Text(BagPresentation.summary(rows))
                .font(.footnote).foregroundStyle(.secondary)
            if syncFailed {
                Text("没能同步到云端，下次改动时会再试").font(.caption).foregroundStyle(HubStyle.bogey)
            }
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
                    Button { onSelect(row) } label: { ladderRow(row, axis: axis) }
                        .buttonStyle(.plain)
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
    var onSet: (Int?) -> Void
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
                Button { step(-1) } label: { Image(systemName: "minus").frame(width: 36, height: 32) }
                    .accessibilityIdentifier("bag-edit-minus")
                Text(row.median.map { "\($0) 码" } ?? "—")
                    .font(.headline.monospacedDigit())
                    .frame(minWidth: 64)
                    .accessibilityIdentifier("bag-edit-value")
                Button { step(1) } label: { Image(systemName: "plus").frame(width: 36, height: 32) }
                    .accessibilityIdentifier("bag-edit-plus")
            }
            .buttonStyle(.bordered)
            if row.isManual, row.historyMedian != nil {
                Button("用历史中位数") { onSet(nil) }
                    .font(.subheadline)
                    .accessibilityIdentifier("bag-edit-reset")
            }
            Spacer(minLength: 0)
            Button(role: .destructive, action: onRemove) {
                Text("从球包拿掉").font(.headline).frame(maxWidth: .infinity).padding(.vertical, 12)
            }
            .buttonStyle(.bordered)
            .accessibilityIdentifier("bag-edit-remove")
        }
        .padding(20)
    }

    /// From the distance in use; a club with none starts from 100 yards.
    private func step(_ delta: Int) {
        onSet(max(1, (row.median ?? 100) + delta))
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
