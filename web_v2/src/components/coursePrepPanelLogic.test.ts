import { describe, expect, it } from 'vitest'
import type { CoursePrepOverlay } from '../types'
import { routeIntervalReadout, routeYardageReadout } from './coursePrepPanelLogic'

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
