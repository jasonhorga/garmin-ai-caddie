import os

/// Centralized `os.Logger` handles for the app.
///
/// The services previously swallowed sync / storage / location / caddie failures
/// (`try?` with no trail), so a round that failed to sync on the course left no
/// diagnostics. These category loggers give a filterable trail in Console and
/// sysdiagnose; the subsystem matches the bundle id.
enum AICaddieLog {
    private static let subsystem = "com.ai-caddie.mobile"

    static let network = Logger(subsystem: subsystem, category: "network")
    static let storage = Logger(subsystem: subsystem, category: "storage")
    static let location = Logger(subsystem: subsystem, category: "location")
    static let caddie = Logger(subsystem: subsystem, category: "caddie")
    static let watch = Logger(subsystem: subsystem, category: "watch")
}
