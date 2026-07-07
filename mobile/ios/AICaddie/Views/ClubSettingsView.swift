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
            ClubGappingLadder(entries: ladderEntries)
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

    /// 距离阶梯图(ClubGappingLadder)的输入:球包里勾选的每支杆 → 该杆距离(码)。距离优先用你输入
    /// 的值(distancesYd),否则退回击球历史中位数(historyYards);两者都没有则 nil = 留空(仍列出,
    /// 提示去补距离)。只用屏幕已加载的真实数据,不发明数字。按目录顺序(木→推)传入,阶梯图内部再按
    /// 距离从长到短排、留空的排最后。
    private var ladderEntries: [ClubGappingLadder.Entry] {
        ClubCatalog.all
            .map(\.zhName)
            .filter { selected.contains($0) }
            .map { zh in
                ClubGappingLadder.Entry(name: zh, yards: distancesYd[zh] ?? historyYards(zh))
            }
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
