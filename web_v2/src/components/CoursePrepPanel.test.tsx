import { describe, expect, it } from 'vitest'
import type { CoursePrepOverlay } from '../types'
import { routeYardageReadout } from './CoursePrepPanel'

describe('routeYardageReadout', () => {
  it('uses route cumulative distance instead of straight-line chord distance', () => {
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

    const readout = routeYardageReadout(overlay, 100)

    expect(readout.distT).toBe(109)
    expect(readout.toGreen).toBe(109)
  })

  it('reports hazard yardage from the ball along the same route', () => {
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

    expect(routeYardageReadout(overlay, 120, 180).hazard).toBe(66)
  })
})
