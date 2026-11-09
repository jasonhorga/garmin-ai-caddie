import Foundation

/// The slice of WatchConnectivity the phone bridge and the Watch sync client use to talk to their
/// counterpart. `WCSession` conforms in each app target; tests and macOS `swift test` substitute a
/// fake so the payload and queue logic can run without a paired device or simulator.
public protocol WatchSessioning: AnyObject {
    var isSessionActivated: Bool { get }
    var isCounterpartReachable: Bool { get }
    /// The latest application context received from the counterpart.
    var receivedContext: [String: Any] { get }
    /// The latest application context this side sent.
    var sentContext: [String: Any] { get }

    func activateSession()
    func send(
        _ message: [String: Any],
        onReply: (([String: Any]) -> Void)?,
        onError: ((Error) -> Void)?
    )
    func queueUserInfo(_ userInfo: [String: Any])
    func replaceContext(_ context: [String: Any]) throws
}
