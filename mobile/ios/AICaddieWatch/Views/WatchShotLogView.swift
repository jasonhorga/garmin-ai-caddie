import SwiftUI

/// Phase 2 本洞逐杆: the active hole's logged shots + a 记一杆 flow (pick 球杆 → append). Each logged shot
/// also uploads as a club event, so the backend gets per-shot club data (feeds richer stats). The watch
/// is the on-course device, so logging shots on the wrist is the natural capture point.
public struct WatchShotLogView: View {
    /// A standard bag for logging shots in a standalone round (no phone-pushed bag on the wrist).
    public static let defaultClubs = [
        "一号木", "三号木", "五号木", "四号铁", "五号铁", "六号铁", "七号铁",
        "八号铁", "九号铁", "P杆", "挖起杆", "沙杆", "推杆",
    ]

    public let shots: [WatchShot]
    public let clubs: [String]
    public let onLogShot: (String) -> Void
    public let onClose: () -> Void

    @State private var selectedClub: String

    public init(shots: [WatchShot], clubs: [String],
                onLogShot: @escaping (String) -> Void = { _ in }, onClose: @escaping () -> Void = {}) {
        self.shots = shots
        self.clubs = clubs
        self.onLogShot = onLogShot
        self.onClose = onClose
        self._selectedClub = State(initialValue: clubs.first ?? "")
    }

    public var body: some View {
        List {
            Section("本洞逐杆") {
                if shots.isEmpty {
                    Text("本洞暂无逐杆 · 点「记一杆」记录你打的每一杆")
                        .font(.footnote).foregroundStyle(.secondary)
                } else {
                    ForEach(shots) { shot in
                        HStack(spacing: 6) {
                            Text("第\(shot.n)杆").font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            Text(shot.club).font(.body.weight(.semibold))
                            if let yards = shot.yards {
                                Text("\(yards)码").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            Section {
                Picker("球杆", selection: $selectedClub) {
                    ForEach(clubs, id: \.self) { Text($0).tag($0) }
                }
                .disabled(clubs.isEmpty)
                Button {
                    if !selectedClub.isEmpty { onLogShot(selectedClub) }
                } label: {
                    Label("记一杆", systemImage: "plus.circle.fill")
                }
                .disabled(selectedClub.isEmpty)
            }
            Section {
                Button("返回", action: onClose)
            }
        }
        .navigationTitle("逐杆")
    }
}
