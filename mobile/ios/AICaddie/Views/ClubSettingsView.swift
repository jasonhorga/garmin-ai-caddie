import Foundation
import SwiftUI

/// 球杆设置:按 Garmin 标准分类(木/混合/铁/挖起/推)勾选你**真实**有的球杆。实战选杆和球童建议
/// 只用勾选的杆,没有的杆(如一条误标的"二号小鸡腿")不会再出现。每支显示击球历史里的常用距离
/// (码)。改动即时本地保存。首次进入默认从击球历史出现过的杆预填。
public struct ClubSettingsView: View {
    public let clubProfiles: [ClubProfile]
    public let apiBaseURL: URL?
    public let adminToken: String?
    @State private var selected: Set<String>
    @State private var didLoadRealBag = false
    @State private var distancesYd: [String: Int] = ClubBagStore.manualDistancesYd()

    public init(clubProfiles: [ClubProfile] = [], apiBaseURL: URL? = nil, adminToken: String? = nil) {
        self.clubProfiles = clubProfiles
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        let derived = Set(clubProfiles.compactMap { profile -> String? in
            let name = zhClubName(profile.clubName.trimmingCharacters(in: .whitespaces))
            return ClubCatalog.names.contains(name) ? name : nil
        })
        // Manual override wins; else the cached real Garmin bag; else derive from shot history.
        _selected = State(initialValue: ClubBagStore.bag() ?? ClubBagStore.realBag() ?? derived)
    }

    public var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                ClubSettingsContent(
                    selected: selected,
                    clubProfiles: clubProfiles,
                    distancesYd: $distancesYd,
                    onToggle: toggle,
                    onReset: (apiBaseURL != nil || ClubBagStore.realBag() != nil) ? resetToGarminBag : nil
                )
                Button {
                    Task { await saveToBackend() }
                } label: {
                    Label("保存到云端", systemImage: "icloud.and.arrow.up")
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(LiveHoleStyle.green)
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 14)
                .padding(.bottom, 14)
            }
        }
        .background(HubStyle.grouped)
        .navigationTitle("球杆设置")
        .task { await loadRealBag() }
    }

    /// Fetch the real Garmin bag once. If the player hasn't manually configured their bag, pre-check
    /// the real bag so the default reflects what they actually carry — with real names.
    private func loadRealBag() async {
        guard !didLoadRealBag else { return }
        didLoadRealBag = true
        guard let names = await refreshRealClubBag(apiBaseURL: apiBaseURL, adminToken: adminToken) else { return }
        if ClubBagStore.bag() == nil {
            selected = names
        }
    }

    /// Drop any manual customization and snap back to the real Garmin bag (re-fetched if possible,
    /// else the cached copy). Fixes a stale manual selection (e.g. an old default that had 三/四号铁).
    private func resetToGarminBag() {
        ClubBagStore.clearManual()
        Task {
            if let names = await refreshRealClubBag(apiBaseURL: apiBaseURL, adminToken: adminToken) {
                selected = names
            } else if let cached = ClubBagStore.realBag() {
                selected = cached
            }
        }
    }

    private func toggle(_ name: String) {
        if selected.contains(name) {
            selected.remove(name)
        } else {
            selected.insert(name)
        }
        ClubBagStore.save(selected)
    }

    /// Persist the manual bag to the backend: cache the typed distances locally, then PUT the selected
    /// clubs (token + yards→metres) to `/api/v2/players/me/clubs/bag`. The owner's admin token edits
    /// "me". Failures are swallowed (the local UserDefaults cache already holds the selection).
    private func saveToBackend() async {
        ClubBagStore.saveManualDistancesYd(distancesYd)
        guard let apiBaseURL else { return }
        let client = SyncClient(baseURL: apiBaseURL, adminToken: adminToken)
        let inputs = ClubBagStore.manualClubInputs(selected: selected, distancesYd: distancesYd)
        _ = try? await client.putManualClubBag(clubs: inputs)
    }
}

/// Presentational catalog (split from the ScrollView so the CI ImageRenderer snapshot renders it).
struct ClubSettingsContent: View {
    let selected: Set<String>
    let clubProfiles: [ClubProfile]
    @Binding var distancesYd: [String: Int]
    var onToggle: (String) -> Void = { _ in }
    var onReset: (() -> Void)? = nil

    var body: some View {
        VStack(spacing: 12) {
            Text("勾选你球包里真实有的球杆 —— 实战选杆和球童建议只用这些,没有的杆不会出现。")
                .font(.caption).foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
            gappingLadderCard
            ForEach(ClubCategory.allCases, id: \.self) { category in
                categoryCard(category)
            }
            Text("已选 \(selected.count) 支").font(.caption2).foregroundStyle(.secondary)
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

    /// 距离阶梯:已选球杆按常用距离(码)从远到近排,每支画出 P10–P90 落点带 + 中位数标记。只用真实
    /// 击球历史(clubProfiles);没有样本的杆不进阶梯,全空则「数据不足」。纯展示,不改任何选择状态。
    private struct LadderRow: Identifiable {
        let id: String
        let name: String
        let p10: Int
        let mid: Int
        let p90: Int
    }

    private var ladderRows: [LadderRow] {
        clubProfiles
            .filter { $0.medianM > 0 && selected.contains(zhClubName($0.clubName)) }
            .map { profile in
                let mid = CoursePrepRoute.yards(fromMetres: profile.medianM)
                let lo = profile.p10M > 0 ? CoursePrepRoute.yards(fromMetres: profile.p10M) : mid
                let hi = profile.p90M > 0 ? CoursePrepRoute.yards(fromMetres: profile.p90M) : mid
                let name = zhClubName(profile.clubName)
                return LadderRow(id: name, name: name, p10: min(lo, mid), mid: mid, p90: max(hi, mid))
            }
            .sorted { $0.mid > $1.mid }
    }

    @ViewBuilder private var gappingLadderCard: some View {
        let rows = ladderRows
        VStack(alignment: .leading, spacing: 10) {
            Text("距离阶梯 · 各杆常用落点(码)").font(.caption).foregroundStyle(.secondary)
            if rows.isEmpty {
                Text("数据不足").font(.subheadline).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center).padding(.vertical, 12)
            } else {
                let lo = rows.map(\.p10).min() ?? 0
                let hi = rows.map(\.p90).max() ?? 1
                ForEach(rows) { row in
                    HStack(spacing: 10) {
                        Text(row.name).font(.subheadline.weight(.semibold)).frame(width: 72, alignment: .leading).lineLimit(1)
                        ladderBar(p10: row.p10, mid: row.mid, p90: row.p90, lo: lo, hi: hi)
                        Text("\(row.mid)").font(.subheadline.monospacedDigit().weight(.bold)).frame(width: 40, alignment: .trailing)
                    }
                }
                Text("落点带 = 常见 10–90% 区间,竖线 = 中位数").font(.caption2).foregroundStyle(.secondary)
            }
        }
        .hubCard()
    }

    private func ladderBar(p10: Int, mid: Int, p90: Int, lo: Int, hi: Int) -> some View {
        GeometryReader { geo in
            let span = CGFloat(max(1, hi - lo))
            let x0 = geo.size.width * CGFloat(p10 - lo) / span
            let x1 = geo.size.width * CGFloat(p90 - lo) / span
            let xm = geo.size.width * CGFloat(mid - lo) / span
            ZStack(alignment: .leading) {
                Capsule().fill(Color(.systemGray5)).frame(height: 6)
                Capsule().fill(LiveHoleStyle.green.opacity(0.35))
                    .frame(width: max(6, x1 - x0), height: 6).offset(x: x0)
                Capsule().fill(LiveHoleStyle.green)
                    .frame(width: 3, height: 14).offset(x: max(0, xm - 1.5))
            }
            .frame(maxHeight: .infinity, alignment: .center)
        }
        .frame(height: 16)
    }

    private func categoryCard(_ category: ClubCategory) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(category.rawValue).font(.caption).foregroundStyle(.secondary)
            ForEach(ClubCatalog.byCategory(category)) { club in
                row(club)
            }
        }
        .hubCard()
    }

    private func row(_ club: CatalogClub) -> some View {
        let isOn = selected.contains(club.zhName)
        // The toggle (icon + name) is its own Button so the distance field — a sibling, not nested in
        // the Button — can take keyboard focus instead of toggling the club when tapped.
        return HStack(spacing: 10) {
            Button {
                onToggle(club.zhName)
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: isOn ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(isOn ? LiveHoleStyle.green : .secondary)
                    Text(club.zhName)
                        .font(.subheadline.weight(isOn ? .semibold : .regular))
                        .foregroundStyle(.primary)
                }
            }
            .buttonStyle(.plain)
            Spacer()
            if isOn {
                HStack(spacing: 4) {
                    TextField("—", text: distanceBinding(club.zhName))
                        .keyboardType(.numberPad)
                        .multilineTextAlignment(.trailing)
                        .font(.caption.monospacedDigit())
                        .frame(width: 52)
                    Text("码").font(.caption2).foregroundStyle(.secondary)
                }
            } else {
                Text(distanceText(club.zhName))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 7)
        .overlay(alignment: .bottom) { Divider() }
    }

    /// String binding for the per-club yards field: shows the typed value, else the history median as a
    /// prefill; on edit, stores yards into `distancesYd` (cleared when blank). Only typed values persist.
    private func distanceBinding(_ zhName: String) -> Binding<String> {
        Binding(
            get: {
                if let yd = distancesYd[zhName] { return String(yd) }
                if let yd = historyYards(zhName) { return String(yd) }
                return ""
            },
            set: { newValue in
                let digits = newValue.filter { $0.isNumber }
                if let yd = Int(digits), yd > 0 {
                    distancesYd[zhName] = yd
                } else {
                    distancesYd[zhName] = nil
                }
            }
        )
    }

    /// 该杆击球历史的常用距离(码),无样本时 nil。
    private func historyYards(_ zhName: String) -> Int? {
        guard let profile = clubProfiles.first(where: { zhClubName($0.clubName) == zhName }), profile.medianM > 0 else {
            return nil
        }
        return CoursePrepRoute.yards(fromMetres: profile.medianM)
    }

    /// 该杆击球历史的常用距离(码);没有样本显示「—」。
    private func distanceText(_ zhName: String) -> String {
        guard let yd = historyYards(zhName) else { return "—" }
        return "\(yd) 码"
    }
}
