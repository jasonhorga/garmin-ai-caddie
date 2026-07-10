import SwiftUI

/// Watch design-system #12: 洞详情 / 本洞击球列表 — reached by tapping a hole row in the scorecard. Shows
/// the hole's score header + the per-shot list (order · club · distance in 码); tapping a shot reuses the
/// club picker overlay to fix it; a bottom 「+ 补记一杆」 adds one. Presentational VStack for snapshots.
public struct WatchHoleDetailView: View {
    public struct Shot: Identifiable, Equatable {
        public let order: Int
        public let club: String
        public let yards: Int?
        public var id: Int { order }
        public init(order: Int, club: String, yards: Int?) {
            self.order = order
            self.club = club
            self.yards = yards
        }
    }

    public let hole: Int
    public let par: Int
    public let score: Int
    public let shots: [Shot]

    public init(hole: Int, par: Int, score: Int, shots: [Shot]) {
        self.hole = hole
        self.par = par
        self.score = score
        self.shots = shots
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text("第\(hole)洞 · Par \(par)").font(.system(size: 13, weight: .bold))
                Spacer()
                Text("\(score)").font(.system(size: 18, weight: .bold, design: .rounded)).monospacedDigit()
                    .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: score - par))
            }
            ForEach(shots) { shot in
                HStack(spacing: 7) {
                    Text("\(shot.order)").font(.system(size: 11, weight: .bold)).foregroundStyle(.secondary).frame(width: 16, alignment: .leading)
                    Text(shot.club).font(.system(size: 13, weight: .semibold))
                    Spacer()
                    if let y = shot.yards {
                        Text("\(y) 码").font(.system(size: 12)).foregroundStyle(.secondary).monospacedDigit()
                    } else {
                        Text("推杆").font(.system(size: 11)).foregroundStyle(.tertiary)
                    }
                }
                .padding(.vertical, 5)
                .overlay(alignment: .bottom) { Divider() }
            }
            HStack {
                Spacer()
                Text("+ 补记一杆").font(.system(size: 12, weight: .bold)).foregroundStyle(AICaddieDesignTokens.par)
                Spacer()
            }
            .padding(.vertical, 7)
            .background(RoundedRectangle(cornerRadius: 10).fill(AICaddieDesignTokens.par.opacity(0.16)))
            .padding(.top, 3)
        }
        .padding(8)
    }
}
