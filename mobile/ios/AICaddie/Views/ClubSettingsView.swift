import Foundation
import SwiftUI

/// 球杆设置:按 Garmin 标准分类(木/混合/铁/挖起/推)勾选你**真实**有的球杆。实战选杆和球童建议
/// 只用勾选的杆,没有的杆(如一条误标的"二号小鸡腿")不会再出现。每支显示击球历史里的常用距离
/// (码)。改动即时本地保存。首次进入默认从击球历史出现过的杆预填。
public struct ClubSettingsView: View {
    public let clubProfiles: [ClubProfile]
    @State private var selected: Set<String>

    public init(clubProfiles: [ClubProfile] = []) {
        self.clubProfiles = clubProfiles
        let derived = Set(clubProfiles.compactMap { profile -> String? in
            let name = zhClubName(profile.clubName.trimmingCharacters(in: .whitespaces))
            return ClubCatalog.names.contains(name) ? name : nil
        })
        _selected = State(initialValue: ClubBagStore.bag() ?? derived)
    }

    public var body: some View {
        ScrollView {
            ClubSettingsContent(selected: selected, clubProfiles: clubProfiles, onToggle: toggle)
        }
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        .navigationTitle("球杆设置")
    }

    private func toggle(_ name: String) {
        if selected.contains(name) {
            selected.remove(name)
        } else {
            selected.insert(name)
        }
        ClubBagStore.save(selected)
    }
}

/// Presentational catalog (split from the ScrollView so the CI ImageRenderer snapshot renders it).
struct ClubSettingsContent: View {
    let selected: Set<String>
    let clubProfiles: [ClubProfile]
    var onToggle: (String) -> Void = { _ in }

    var body: some View {
        VStack(spacing: 12) {
            Text("勾选你球包里真实有的球杆 —— 实战选杆和球童建议只用这些,没有的杆不会出现。")
                .font(.caption).foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
            ForEach(ClubCategory.allCases, id: \.self) { category in
                categoryCard(category)
            }
            Text("已选 \(selected.count) 支").font(.caption2).foregroundStyle(.secondary)
        }
        .padding(14)
    }

    private func categoryCard(_ category: ClubCategory) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(category.rawValue).font(.caption).foregroundStyle(.secondary)
            ForEach(ClubCatalog.byCategory(category)) { club in
                row(club)
            }
        }
        .liveCard()
    }

    private func row(_ club: CatalogClub) -> some View {
        let isOn = selected.contains(club.zhName)
        return Button {
            onToggle(club.zhName)
        } label: {
            HStack(spacing: 10) {
                Image(systemName: isOn ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(isOn ? LiveHoleStyle.green : .secondary)
                Text(club.zhName)
                    .font(.subheadline.weight(isOn ? .semibold : .regular))
                    .foregroundStyle(.primary)
                Spacer()
                Text(distanceText(club.zhName))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            .padding(.vertical, 7)
            .overlay(alignment: .bottom) { Divider() }
        }
        .buttonStyle(.plain)
    }

    /// 该杆击球历史的常用距离(码);没有样本显示「—」。
    private func distanceText(_ zhName: String) -> String {
        guard let profile = clubProfiles.first(where: { zhClubName($0.clubName) == zhName }), profile.medianM > 0 else {
            return "—"
        }
        return "\(CoursePrepRoute.yards(fromMetres: profile.medianM)) 码"
    }
}
