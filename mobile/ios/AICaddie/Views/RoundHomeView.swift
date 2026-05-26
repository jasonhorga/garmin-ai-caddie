import SwiftUI

public struct RoundHomeView: View {
    public let package: LiveRoundPackage
    public let pendingEventCount: Int
    public let syncStatus: String
    public let onEvent: (LiveRoundEvent) -> Void

    public init(
        package: LiveRoundPackage,
        pendingEventCount: Int = 0,
        syncStatus: String = "Offline ready",
        onEvent: @escaping (LiveRoundEvent) -> Void = { _ in }
    ) {
        self.package = package
        self.pendingEventCount = pendingEventCount
        self.syncStatus = syncStatus
        self.onEvent = onEvent
    }

    public var body: some View {
        NavigationStack {
            List {
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(package.course.name)
                            .font(.title2.weight(.semibold))
                        Text("Tee \(package.course.teeBox) / \(package.geometryCoverage.readyHoles)/\(package.geometryCoverage.totalHoles) geometry")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    HStack {
                        Label("\(package.clubProfiles.count)", systemImage: "golfclub")
                        Spacer()
                        Label("\(pendingEventCount)", systemImage: "tray.full")
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }

                Section("Holes") {
                    ForEach(package.holes) { hole in
                        NavigationLink {
                            CurrentHoleView(package: package, hole: hole, onEvent: onEvent)
                        } label: {
                            HStack {
                                Text("\(hole.number)")
                                    .font(.headline.monospacedDigit())
                                    .frame(width: 32, alignment: .leading)
                                VStack(alignment: .leading) {
                                    Text("Par \(hole.par)")
                                    Text(hole.geometryCoverage.rawValue)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption)
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Live Round")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Text(syncStatus)
                        .font(.caption.weight(.medium))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}
