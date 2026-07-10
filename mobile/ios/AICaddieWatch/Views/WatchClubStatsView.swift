import SwiftUI

/// Watch design-system #14: 球杆统计 — each club's typical distance (码), crown-scrolled. Per the design
/// system the ± error band is STRIPPED (no fake precision); just the club + its median carry.
/// Presentational VStack so it renders in ImageRenderer snapshots.
public struct WatchClubStatsView: View {
    public struct Row: Identifiable, Equatable {
        public let club: String
        public let carryYd: Int
        public var id: String { club }
        public init(club: String, carryYd: Int) {
            self.club = club
            self.carryYd = carryYd
        }
    }

    public let rows: [Row]

    public init(rows: [Row]) {
        self.rows = rows
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("球杆数据 · 平均").font(.headline.weight(.bold)).padding(.bottom, 2)
            ForEach(rows) { row in
                HStack(spacing: 6) {
                    Text(row.club).font(.system(size: 14, weight: .semibold))
                    Spacer()
                    Text("\(row.carryYd)").font(.system(size: 18, weight: .bold, design: .rounded)).monospacedDigit()
                    Text("码").font(.system(size: 9)).foregroundStyle(.secondary)
                }
                .padding(.vertical, 6)
                .overlay(alignment: .bottom) { Divider() }
            }
        }
        .padding(8)
    }
}
