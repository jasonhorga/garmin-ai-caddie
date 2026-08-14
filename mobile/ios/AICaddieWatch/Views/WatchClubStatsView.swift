import SwiftUI

struct WatchClubStatRow: Equatable, Identifiable {
    var id: String { name.lowercased() }

    let name: String
    let yards: Int
}

/// The downloaded bag already carries measured median distance per club. This screen exposes those
/// facts in the approved compact Watch list without manufacturing averages for missing clubs.
public struct WatchClubStatsView: View {
    public let clubs: [WatchClubOption]
    public let onBack: () -> Void

    public init(
        clubs: [WatchClubOption],
        onBack: @escaping () -> Void = {}
    ) {
        self.clubs = clubs
        self.onBack = onBack
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text("球杆数据 · 典型")
                    .font(.system(size: 15, weight: .bold))
                    .padding(.bottom, 3)

                if rows.isEmpty {
                    Text("暂无真实球杆距离")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.secondary)
                        .padding(.vertical, 8)
                } else {
                    ForEach(rows) { row in
                        HStack(alignment: .firstTextBaseline, spacing: 5) {
                            Text(row.name)
                                .font(.system(size: 14, weight: .semibold))
                                .lineLimit(1)
                            Spacer(minLength: 4)
                            Text("\(row.yards)")
                                .font(.system(size: 18, weight: .bold, design: .rounded))
                                .monospacedDigit()
                            Text("码")
                                .font(.system(size: 9, weight: .medium))
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 6.75)
                        .overlay(alignment: .bottom) { Divider() }
                    }
                }
            }
            .padding(.horizontal, 8)
            .padding(.top, 7)
        }
        .ignoresSafeArea(edges: .top)
        .scrollIndicators(.hidden)
        .simultaneousGesture(
            DragGesture(minimumDistance: 24)
                .onEnded { value in
                    guard value.startLocation.x <= 28,
                          value.translation.width >= 60,
                          abs(value.translation.height) < 50 else { return }
                    onBack()
                }
        )
        .accessibilityAction(named: Text("返回菜单"), onBack)
    }

    var rows: [WatchClubStatRow] {
        var seen = Set<String>()
        return clubs.compactMap { club in
            let name = WatchClubDisplay.name(club.clubName)
            let key = name.lowercased()
            guard !name.isEmpty,
                  let metres = club.medianM,
                  metres.isFinite,
                  metres > 0,
                  seen.insert(key).inserted else { return nil }
            return WatchClubStatRow(name: name, yards: WatchUnits.yards(metres))
        }
    }
}
