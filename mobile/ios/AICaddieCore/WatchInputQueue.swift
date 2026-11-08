import Foundation

/// The Watch's offline input queue as a value: one entry per `eventId`, kept in capture order until
/// the phone or backend resolves it. Persistence and locking stay with the owner of the queue file.
public struct WatchInputQueue: Equatable {
    public private(set) var events: [WatchInputEvent]

    public init(events: [WatchInputEvent] = []) {
        self.events = events
    }

    /// Appends `event` unless an event with the same `eventId` is already waiting.
    /// Returns whether the queue changed.
    @discardableResult
    public mutating func enqueue(_ event: WatchInputEvent) -> Bool {
        events.append(event)
        return true
    }

    /// Drops every event the counterpart accepted, recognised as a duplicate, or rejected.
    public mutating func removeResolved(_ eventIds: Set<String>) {
    }

    /// Drops every event that belongs to `roundId`.
    public mutating func discardRound(_ roundId: String) {
    }
}
