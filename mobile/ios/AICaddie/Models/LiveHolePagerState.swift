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

    @discardableResult
    mutating func send(_ event: Event) -> Effect {
        var effect = Effect()
        switch event {
        case .pageSetChanged(let holes, let active):
            ordered = holes
            setTarget(active ?? activeHole ?? holes.first)
        case .programmaticHole(let hole):
            setTarget(hole)
        case .advance(let hole):
            guard ordered.contains(hole) else { return effect }
            setTarget(hole)
            effect.activeHoleToPersist = hole
        case .touchBegan:
            touchOrigin = activeHole
        case .touchEnded(let step):
            guard let origin = touchOrigin, let index = ordered.firstIndex(of: origin) else { return effect }
            touchOrigin = nil
            let nextIndex = index + step
            let next = ordered.indices.contains(nextIndex) ? ordered[nextIndex] : origin
            let displayed = reportedSelection
            setTarget(next)
            if displayed == next { pendingTarget = nil }
            if step == 0, let displayed, displayed != next { effect.forceScrollTo = next }
            if next != origin { effect.activeHoleToPersist = next }
        case .presentationChanged:
            break // Existing behaviour: presentation does not gate display correction.
        case .bindingReported(let hole):
            reportedSelection = hole
            if hole == pendingTarget, pendingTarget != nil {
                selection = hole
                pendingTarget = nil
            } else if pendingTarget != nil {
                effect.forceScrollTo = pendingTarget
            } else if touchOrigin != nil, let hole, ordered.contains(hole) {
                // Native scrolling remains interactive; only touchEnded commits the round cursor.
                selection = hole
            } else if hole != activeHole {
                selection = activeHole
                pendingTarget = activeHole
                effect.forceScrollTo = activeHole
            }
        }
        return effect
    }

    private mutating func setTarget(_ hole: Int?) {
        activeHole = hole
        selection = hole
        pendingTarget = hole
        touchOrigin = nil
    }
}
