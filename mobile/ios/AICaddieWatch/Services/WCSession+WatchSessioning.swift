import AICaddieCore
import WatchConnectivity

/// The production phone link: `WCSession` already provides every call `WatchSessioning` names.
extension WCSession: WatchSessioning {
    public var isSessionActivated: Bool { activationState == .activated }
    public var isCounterpartReachable: Bool { isReachable }
    public var receivedContext: [String: Any] { receivedApplicationContext }
    public var sentContext: [String: Any] { applicationContext }

    public func activateSession() {
        activate()
    }

    public func send(
        _ message: [String: Any],
        onReply: (([String: Any]) -> Void)?,
        onError: ((Error) -> Void)?
    ) {
        sendMessage(message, replyHandler: onReply, errorHandler: onError)
    }

    public func queueUserInfo(_ userInfo: [String: Any]) {
        transferUserInfo(userInfo)
    }

    public func replaceContext(_ context: [String: Any]) throws {
        try updateApplicationContext(context)
    }
}
