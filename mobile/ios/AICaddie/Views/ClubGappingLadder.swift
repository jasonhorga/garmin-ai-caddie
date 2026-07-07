import SwiftUI

/// 各杆距离阶梯图(gapping ladder):把球包里每支杆按距离(码)从长到短排成一条阶梯,每支画一条
/// 与距离成正比的横条,一眼看清相邻球杆之间的距离缺口。没有距离数据的杆仍然列出(显示「留空」、
/// 不画横条),提示去补一个距离,这样一支都不漏。
///
/// 纯展示 —— 不持有 / 不修改任何选择或设置状态。每支杆的距离由调用方算好传入(球杆设置屏用勾选的
/// 球包 + 已输入距离 / 击球历史中位数),不在这里发明数字。整体是 VStack(无 ScrollView),所以
/// CI 的 ImageRenderer / 窗口快照能直接渲染。距离一律用码(产品规则)。
struct ClubGappingLadder: View {
    /// 阶梯里的一支杆:中文名 + 距离(码)。`yards == nil` 表示没有距离数据 → 显示「留空」、不画条。
    struct Entry: Identifiable, Equatable {
        let name: String
        let yards: Int?
        var id: String { name }
        init(name: String, yards: Int?) {
            self.name = name
            self.yards = yards
        }
    }

    let entries: [Entry]
    init(entries: [Entry]) { self.entries = entries }

    /// 有距离的杆按距离从长到短在上;没有距离的(留空)排在最后,保持传入顺序。
    private var ordered: [Entry] {
        let withDistance = entries
            .filter { $0.yards != nil }
            .sorted { ($0.yards ?? 0) > ($1.yards ?? 0) }
        let blanks = entries.filter { $0.yards == nil }
        return withDistance + blanks
    }

    /// 归一化横条用的最长距离(码);至少 1,避免除零。
    private var maxYards: Int {
        max(1, entries.compactMap(\.yards).max() ?? 1)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("距离阶梯 · 各杆距离(码)")
                .font(.caption)
                .foregroundStyle(.secondary)
            if ordered.isEmpty {
                Text("数据不足")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 12)
            } else {
                ForEach(ordered) { row($0) }
                Text("横条长度按距离成正比,一眼看清各杆之间的缺口;显示「留空」的杆还没有距离,去上面补一个。")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .hubCard()
    }

    private func row(_ entry: Entry) -> some View {
        HStack(spacing: 10) {
            Text(entry.name)
                .font(.subheadline.weight(.semibold))
                .frame(width: 76, alignment: .leading)
                .lineLimit(1)
            bar(for: entry.yards)
            distanceLabel(entry.yards)
        }
    }

    /// 与距离成正比的横条:灰色轨道打底 + 绿色填充(填充宽 = 距离 / 最长距离)。留空 → 只有灰轨道。
    private func bar(for yards: Int?) -> some View {
        GeometryReader { geo in
            let fillWidth = yards.map { max(6, geo.size.width * CGFloat($0) / CGFloat(maxYards)) }
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color(.systemGray5))
                    .frame(height: 8)
                if let fillWidth {
                    Capsule()
                        .fill(LiveHoleStyle.green)
                        .frame(width: fillWidth, height: 8)
                }
            }
            .frame(maxHeight: .infinity, alignment: .center)
        }
        .frame(height: 16)
    }

    @ViewBuilder private func distanceLabel(_ yards: Int?) -> some View {
        if let yards {
            Text("\(yards)")
                .font(.subheadline.monospacedDigit().weight(.bold))
                .foregroundStyle(.primary)
                .frame(width: 48, alignment: .trailing)
        } else {
            Text("留空")
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 48, alignment: .trailing)
        }
    }
}
