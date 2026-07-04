import { describe, expect, it } from 'vitest'
import type { CoursePrepClub, CoursePrepHole } from '../types'
import {
  hazardSummary,
  headlineTargetYd,
  holeDescriptor,
  initialCum,
  landingYd,
  recosForTarget,
  slopeYd,
  toGreenYd,
  toYd,
  waterCarryYards,
} from './prepWorkbenchLogic'

function hole(overrides: Partial<CoursePrepHole> = {}): CoursePrepHole {
  return {
    hole: 1,
    par: 4,
    par_source: 'courseview',
    blue_yards: 430,
    route_len_m: 393,
    route: [],
    geometryCoverage: 'ready',
    sourceRefs: [],
    missingData: [],
    candidateRoutes: [],
    carryTargets: [],
    steps: [],
    cautions: [],
    landing_m: null,
    tee_club: null,
    hazards: { water_carry: [], bunkers: [] },
    ...overrides,
  }
}

const overlay = { w: 360, h: 360, ppm: 0.85, ln: 393, route: [] as Array<[number, number, number]> }

describe('prepWorkbenchLogic', () => {
  it('toYd rounds metres to yards', () => {
    expect(toYd(100)).toBe(109)
    expect(toYd(215)).toBe(235)
  })

  it('initialCum sits a par 3 on the green and everything else at the landing', () => {
    expect(initialCum(hole({ par: 3, route_len_m: 165 }))).toBe(165)
    expect(initialCum(hole({ par: 4, landing_m: 215, route_len_m: 393 }))).toBe(215)
    // no landing → ~55% of the hole, clamped to the route length
    expect(initialCum(hole({ par: 5, landing_m: null, route_len_m: 500 }))).toBeCloseTo(275)
  })

  it('holeDescriptor derives from par + water only', () => {
    expect(holeDescriptor(hole({ par: 3 }))).toBe('三杆洞')
    expect(holeDescriptor(hole({ par: 4, hazards: { water_carry: [[100, 150]], bunkers: [] } }))).toBe('四杆洞 · 跨水')
    expect(holeDescriptor(hole({ par: 6 }))).toBe('Par 6')
  })

  it('hazardSummary counts water + bunkers, else 无', () => {
    expect(hazardSummary(hole({ hazards: { water_carry: [[1, 2]], bunkers: [[3, 4], [5, 6]] } })).text).toBe('水×1 · 沙×2')
    expect(hazardSummary(hole()).text).toBe('无')
  })

  it('waterCarryYards clears each water interval end, capped at 2', () => {
    expect(waterCarryYards(hole({ hazards: { water_carry: [[100, 150], [200, 240], [300, 330]], bunkers: [] } }))).toEqual([
      toYd(150),
      toYd(240),
    ])
  })

  it('slopeYd only surfaces a non-zero available delta', () => {
    expect(slopeYd(hole({ playsLike: { available: true, deltaYd: 8 } }))).toBe(8)
    expect(slopeYd(hole({ playsLike: { available: true, deltaYd: 0 } }))).toBeNull()
    expect(slopeYd(hole({ playsLike: { available: false, deltaYd: 8 } }))).toBeNull()
    expect(slopeYd(hole())).toBeNull()
  })

  it('landingYd converts landing_m when present', () => {
    expect(landingYd(hole({ landing_m: 215 }))).toBe(235)
    expect(landingYd(hole({ landing_m: null }))).toBeNull()
  })

  it('headlineTargetYd is the tee→ball distance with geometry, the tee shot without', () => {
    expect(headlineTargetYd(hole({ map: { image: 'x', overlay } }), 215)).toBe(235)
    // no geometry: par 3 → whole hole, else the landing
    expect(headlineTargetYd(hole({ par: 3, blue_yards: 180 }), 0)).toBe(180)
    expect(headlineTargetYd(hole({ par: 4, landing_m: 200, route_len_m: 393 }), 0)).toBe(toYd(200))
  })

  it('toGreenYd is the remaining route with geometry, null once on the green', () => {
    expect(toGreenYd(hole({ map: { image: 'x', overlay } }), 215)).toBe(toYd(178))
    expect(toGreenYd(hole({ map: { image: 'x', overlay } }), 393)).toBeNull()
    expect(toGreenYd(hole({ par: 3 }), 0)).toBeNull()
  })

  it('recosForTarget brackets the target and marks the nearest club recommended', () => {
    const clubs: CoursePrepClub[] = [
      { name: '1D', m: 220, yd: 241 },
      { name: '3W', m: 200, yd: 219 },
      { name: '5I', m: 165, yd: 180 },
      { name: '8I', m: 131, yd: 143 },
    ]
    const recos = recosForTarget(clubs, 232)
    expect(recos.map((club) => club.name)).toEqual(['1D', '3W', '5I'])
    expect(recos.find((club) => club.on)?.name).toBe('1D')
    expect(recosForTarget([], 200)).toEqual([])
  })
})
