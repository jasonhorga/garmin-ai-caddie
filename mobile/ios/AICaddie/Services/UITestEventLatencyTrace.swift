import Foundation

#if DEBUG
/// Temporary, opt-in timing evidence for the real-flow simulator. It records stage names and byte
/// counts only (never event payloads or credentials) into the app container so CI can collect it
/// beside the screenshots when `UITEST_TRACE_EVENT_LATENCY=1`.
enum UITestEventLatencyTrace {
    private static let enabled = ProcessInfo.processInfo.environment["UITEST_TRACE_EVENT_LATENCY"] == "1"
    private static let fileURL: URL = {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return documents
            .appendingPathComponent("real-screenshots", isDirectory: true)
            .appendingPathComponent("event-latency-\(ProcessInfo.processInfo.processIdentifier).txt")
    }()

    static func record(_ message: String) {
        guard enabled else { return }
        let directory = fileURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let uptime = String(format: "%.6f", ProcessInfo.processInfo.systemUptime)
        guard let data = "\(uptime) \(message)\n".data(using: .utf8) else { return }

        if FileManager.default.fileExists(atPath: fileURL.path),
           let handle = try? FileHandle(forWritingTo: fileURL) {
            defer { try? handle.close() }
            try? handle.seekToEnd()
            try? handle.write(contentsOf: data)
        } else {
            try? data.write(to: fileURL, options: .atomic)
        }
    }
}
#endif
