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
    }

    struct Effect: Equatable {
        var activeHoleToPersist: Int?
        var forceScrollTo: Int?
    }

    private(set) var ordered: [Int] = []
    private(set) var activeHole: Int?
    private(set) var selection: Int?
    private(set) var pendingTarget: Int?
    private(set) var touchOrigin: Int?

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
            setTarget(next)
            if next != origin { effect.activeHoleToPersist = next }
        case .bindingReported(let hole):
            // Red-test seam: r9's selection onChange saved any valid page back into the cursor,
            // including a delayed round-hole 9 report from the reused 9-to-18-page TabView.
            guard let hole, ordered.contains(hole) else { return effect }
            selection = hole
            activeHole = hole
            pendingTarget = nil
            effect.activeHoleToPersist = hole
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
