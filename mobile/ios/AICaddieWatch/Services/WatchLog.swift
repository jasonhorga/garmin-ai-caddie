import os

/// Centralized `os.Logger` handles for the Watch target (P1-11).
///
/// The watch app previously had no logging at all — every `try?` (persist / decode / flush / Watch
/// Connectivity send) swallowed its failure with no trail, so an on-wrist save or sync failure was
/// undiagnosable. These category loggers give a filterable trail in Console and sysdiagnose; the
/// subsystem mirrors `AICaddieLog` on the phone with a `.watch` suffix.
enum WatchLog {
    private static let subsystem = "com.ai-caddie.mobile.watch"

    static let sync = Logger(subsystem: subsystem, category: "sync")
    static let storage = Logger(subsystem: subsystem, category: "storage")
    static let connectivity = Logger(subsystem: subsystem, category: "connectivity")
}
