import Foundation
import XCTest
@testable import AICaddie

/// App-model goals share the production bag coordinator. Keep its storage and player binding
/// inside a fresh suite, and finish any restore before returning storage to the next test.
@MainActor
final class GoalClubBagIsolation {
    private let previousDefaults = ClubBagStore.defaults
    private let previousPlayer = ClubBagStore.playerId
    private let previousCoordinator: ClubBagSyncCoordinator.TestIsolationState
    private let suite = "goal-bag-\(UUID().uuidString)"

    init() throws {
        previousCoordinator = ClubBagSyncCoordinator.shared.snapshotForTesting()
        ClubBagStore.defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        ClubBagSyncCoordinator.shared.activate(playerId: suite, migrateLegacy: false)
    }

    func restore() async {
        await ClubBagSyncCoordinator.shared.flush()
        ClubBagStore.defaults = previousDefaults
        ClubBagSyncCoordinator.shared.restoreForTesting(previousCoordinator)
        ClubBagSyncCoordinator.shared.activate(playerId: previousPlayer, migrateLegacy: false)
        UserDefaults().removePersistentDomain(forName: suite)
    }
}
