import Foundation

/// The round cursor follows explicit navigation intents. A native pager report is display feedback,
/// never permission to save a new active hole. All numbers here are round holes, not course holes.
struct LiveHolePagerState: Equatable {
    enum Event: Equatable {
        case pageSetChanged(ordered: [Int], activeHole: Int?)
        case programmaticHole(Int?)
        case advance(Int)
        case touchBegan
        case touchEnded(step: Int)
        case bindingReported(Int?)
        case presentationChanged(Bool)
    }

    struct Effect: Equatable {
        var activeHoleToPersist: Int? = nil
        var forceScrollTo: Int? = nil
    }

    private(set) var ordered: [Int] = []
    private(set) var activeHole: Int? = nil
    private(set) var selection: Int? = nil
    private(set) var pendingTarget: Int? = nil
    private(set) var touchOrigin: Int? = nil
    private(set) var reportedSelection: Int? = nil
    private(set) var presentationBlocksCorrection = false
    private(set) var correctionAttempts = 0
    private var correctionDeferredByPresentation = false
    private(set) var deferredOrdered: [Int]? = nil

    static func swipeStep(
        translationX: Double, translationY: Double, predictedX: Double, scrollDisabled: Bool
    ) -> Int {
        guard !scrollDisabled, abs(translationX) > abs(translationY),
              translationX * predictedX > 0,
              abs(translationX) >= 50 || abs(predictedX) >= 100 else { return 0 }
        return translationX < 0 ? 1 : -1
    }

    @discardableResult
    mutating func send(_ event: Event) -> Effect {
        var effect = Effect()
        switch event {
        case .pageSetChanged(let holes, let active):
            let requested = active ?? activeHole
            if presentationBlocksCorrection {
                deferredOrdered = holes
                // The model cursor changes immediately; only the native page order waits for the
                // sheet and its dismissal animation. Keep the old ordered pages mounted.
                setTarget(requested, clearReport: false, updateSelection: false)
            } else {
                applyPageSet(holes, active: requested, effect: &effect)
            }
        case .programmaticHole(let hole):
            setTarget(hole, updateSelection: !presentationBlocksCorrection)
        case .advance(let hole):
            // A cached page set is the model's current set (e.g. a loop added from the scorecard).
            guard (deferredOrdered ?? ordered).contains(hole) else { return effect }
            setTarget(hole, updateSelection: !presentationBlocksCorrection)
            effect.activeHoleToPersist = hole
        case .touchBegan:
            touchOrigin = activeHole
            reportedSelection = nil // Only this touch can acknowledge its finger-up destination.
        case .touchEnded(let step):
            guard let origin = touchOrigin, let index = ordered.firstIndex(of: origin) else { return effect }
            touchOrigin = nil
            let nextIndex = index + step
            let next = ordered.indices.contains(nextIndex) ? ordered[nextIndex] : origin
            let displayed = reportedSelection
            setTarget(next)
            if displayed == next {
                pendingTarget = nil
                correctionAttempts = 0
            }
            if step == 0, let displayed, displayed != next { requestCorrection(into: &effect) }
            if next != origin { effect.activeHoleToPersist = next }
        case .presentationChanged(let blocked):
            let wasBlocked = presentationBlocksCorrection
            presentationBlocksCorrection = blocked
            if wasBlocked, !blocked, let holes = deferredOrdered {
                deferredOrdered = nil
                // The cursor may have moved while the order waited (scorecard jump): apply the current one.
                applyPageSet(holes, active: activeHole, clearReport: false, effect: &effect)
            }
            if wasBlocked, !blocked, correctionDeferredByPresentation, pendingTarget != nil {
                requestCorrection(into: &effect)
            }
        case .bindingReported(let hole):
            reportedSelection = hole
            if hole == pendingTarget, pendingTarget != nil {
                selection = hole
                pendingTarget = nil
                correctionAttempts = 0
                correctionDeferredByPresentation = false
            } else if pendingTarget != nil {
                requestCorrection(into: &effect)
            } else if touchOrigin != nil, let hole, ordered.contains(hole) {
                // Native scrolling remains interactive; only touchEnded commits the round cursor.
                selection = hole
            } else if hole != activeHole {
                selection = activeHole
                pendingTarget = activeHole
                requestCorrection(into: &effect)
            }
        }
        return effect
    }

    private mutating func requestCorrection(into effect: inout Effect) {
        guard let target = pendingTarget else { return }
        if presentationBlocksCorrection {
            correctionDeferredByPresentation = true
            return
        }
        guard correctionAttempts < 3 else { return }
        correctionDeferredByPresentation = false
        // An interactive report is rejected, but it must not spend the correction budget while
        // the finger still owns the surface. The view defers it until finger-up.
        if touchOrigin == nil { correctionAttempts += 1 }
        effect.forceScrollTo = target
    }

    private mutating func applyPageSet(
        _ holes: [Int], active: Int?, clearReport: Bool = true, effect: inout Effect
    ) {
        ordered = holes
        let target = active.flatMap { holes.contains($0) ? $0 : nil } ?? holes.first
        setTarget(target, clearReport: clearReport)
        if let reportedSelection, reportedSelection != target {
            requestCorrection(into: &effect)
        }
    }

    private mutating func setTarget(
        _ hole: Int?, clearReport: Bool = true, updateSelection: Bool = true
    ) {
        if activeHole != hole { correctionAttempts = 0 }
        if clearReport { reportedSelection = nil }
        correctionDeferredByPresentation = false
        activeHole = hole
        if updateSelection { selection = hole }
        pendingTarget = hole
        touchOrigin = nil
    }
}
