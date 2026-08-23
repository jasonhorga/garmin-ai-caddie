import { describe, expect, it } from 'vitest'
import type { CoursePrepHole, CoursePrepOverlay } from '../types'
import { atCum, layoutHazardLabels, nearestCum, resolveCoursePrepOverlay, routeIntervalReadout, routeYardageReadout } from './coursePrepPanelLogic'

const overlay: CoursePrepOverlay = {
  w: 200,
  h: 200,
  ppm: 1,
  ln: 200,
  route: [
    [0, 0, 0],
    [100, 0, 100],
    [100, 100, 200],
  ],
}

describe('resolveCoursePrepOverlay', () => {
  it('projects the CourseView local-metre route into the shared display frame', () => {
    const hole = {
      route: [[0, 0, 0], [60, 120, 134]],
      route_len_m: 134,
      holeImageProjection: {
        available: true,
        widthPx: 360,
        heightPx: 560,
        refs: [
          { lat: 30, lon: 120, px: 10, py: 20 },
          { lat: 30, lon: 120.001, px: 130, py: 20 },
          { lat: 30.001, lon: 120, px: 10, py: 140 },
        ],
      },
    } as CoursePrepHole

    expect(resolveCoursePrepOverlay(hole)).toEqual({
      w: 360,
      h: 560,
      ppm: 1,
      ln: 134,
      route: [[10, 20, 0], [70, 140, 134]],
    })
  })
})

// Characterization tests for the drag helpers extracted from PrepHoleCard
// (now shared with the 实战 LiveSandbox map canvas).
describe('atCum', () => {
  it('interpolates the px point at a cumulative distance, following the dogleg', () => {
    expect(atCum(overlay.route, 0)).toEqual({ x: 0, y: 0 })
    expect(atCum(overlay.route, 50)).toEqual({ x: 50, y: 0 })
    expect(atCum(overlay.route, 150)).toEqual({ x: 100, y: 50 })
  })

  it('clamps past the route end to the final point', () => {
    expect(atCum(overlay.route, 999)).toEqual({ x: 100, y: 100 })
  })
})

describe('nearestCum', () => {
  it('projects an off-route pointer onto the nearest segment and returns its metres', () => {
    expect(nearestCum(overlay.route, 60, 25)).toBe(60)
    expect(nearestCum(overlay.route, 80, 70)).toBe(170)
  })

  it('clamps pointers beyond the route ends to 0 and the full length', () => {
    expect(nearestCum(overlay.route, -40, -10)).toBe(0)
    expect(nearestCum(overlay.route, 100, 180)).toBe(200)
  })
})

describe('routeYardageReadout', () => {
  it('uses route cumulative distance instead of straight-line chord distance', () => {
    const readout = routeYardageReadout(overlay, 100)

    expect(readout.distT).toBe(109)
    expect(readout.toGreen).toBe(109)
  })

  it('reports hazard yardage from the ball along the same route', () => {
    expect(routeYardageReadout(overlay, 120, 180).hazard).toBe(66)
  })
})

describe('routeIntervalReadout', () => {
  it('reports carry to enter and clear water when the ball is before the interval', () => {
    expect(routeIntervalReadout(overlay, 70, 100, 130)).toEqual({
      toStart: 33,
      toClear: 66,
      isBehind: true,
      isInside: false,
      isCleared: false,
    })
  })

  it('reports remaining carry when the ball is inside the water interval', () => {
    expect(routeIntervalReadout(overlay, 110, 100, 130)).toEqual({
      toStart: 0,
      toClear: 22,
      isBehind: false,
      isInside: true,
      isCleared: false,
    })
  })

  it('marks intervals behind the ball as cleared', () => {
    expect(routeIntervalReadout(overlay, 150, 100, 130)).toEqual({
      toStart: 0,
      toClear: 0,
      isBehind: false,
      isInside: false,
      isCleared: true,
    })
  })
})

describe('layoutHazardLabels', () => {
  it('leaves labels that already clear each other untouched', () => {
    const out = layoutHazardLabels([{ y: 20, text: '水55y' }, { y: 60, text: '沙87y' }], 14)
    expect(out).toEqual([
      { labelY: 20, showLabel: true },
      { labelY: 60, showLabel: true },
    ])
  })

  it('pushes a colliding label down to clear the previous one by minGap', () => {
    const out = layoutHazardLabels([{ y: 50, text: '水' }, { y: 55, text: '沙' }], 14)
    expect(out).toEqual([
      { labelY: 50, showLabel: true },
      { labelY: 64, showLabel: true },
    ])
  })

  it('cascades a stack of three overlapping labels', () => {
    const out = layoutHazardLabels([{ y: 50, text: 'a' }, { y: 52, text: 'b' }, { y: 54, text: 'c' }], 14)
    expect(out.map((p) => p.labelY)).toEqual([50, 64, 78])
    expect(out.every((p) => p.showLabel)).toBe(true)
  })

  it('hides a duplicate label that would collide with an identical one', () => {
    const out = layoutHazardLabels([{ y: 50, text: '沙20y' }, { y: 53, text: '沙20y' }], 14)
    expect(out).toEqual([
      { labelY: 50, showLabel: true },
      { labelY: 53, showLabel: false },
    ])
  })

  it('keeps an identical label that is far enough away to not collide', () => {
    const out = layoutHazardLabels([{ y: 20, text: '沙20y' }, { y: 80, text: '沙20y' }], 14)
    expect(out).toEqual([
      { labelY: 20, showLabel: true },
      { labelY: 80, showLabel: true },
    ])
  })

  it('returns placements in the original row order even when input is unsorted', () => {
    const out = layoutHazardLabels([{ y: 60, text: '沙' }, { y: 50, text: '水' }], 14)
    // row 0 (y=60) is the lower of the two, so it gets pushed below row 1 (y=50)
    expect(out).toEqual([
      { labelY: 64, showLabel: true },
      { labelY: 50, showLabel: true },
    ])
  })
})
