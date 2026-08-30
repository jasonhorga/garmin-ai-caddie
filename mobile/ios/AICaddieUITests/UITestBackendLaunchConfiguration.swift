import Foundation

/// Keeps live UI-test launches free of fixture markers while preserving malformed marker values so
/// the app's fail-closed fixture guard remains effective in fixture-contract tests.
enum UITestBackendLaunchConfiguration {
    static let markerKeys = [
        "AI_CADDIE_FIXTURE_MODE",
        "AI_CADDIE_DATA_MODE",
    ]

    static func markers(fixtureMode: String?, dataMode: String?) -> [String: String] {
        let mode = fixtureMode ?? "0"
        let data = dataMode ?? ""
        // The workflow's live defaults are "0" and an empty data mode. Omitting both keys is
        // required because AICaddieApp treats the presence of either key as fixture mode.
        guard mode != "0" || !data.isEmpty else { return [:] }
        return [
            "AI_CADDIE_FIXTURE_MODE": mode,
            "AI_CADDIE_DATA_MODE": data,
        ]
    }
}
