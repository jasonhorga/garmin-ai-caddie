import { describe, expect, it } from 'vitest'
import type { CoursePrepOverlay } from '../types'
import { atCum, nearestCum, routeIntervalReadout, routeYardageReadout } from './coursePrepPanelLogic'

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
