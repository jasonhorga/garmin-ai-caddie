import { describe, expect, it } from 'vitest'
import type { RoundHoleShot } from '../types'
import {
  buildTimeline,
  buildTrajectory,
  chipShape,
  dodgeLabels,
  isPuttShot,
  lieZh,
  shotDistanceYd,
  shotLandingLabels,
} from './reviewShotMapLogic'
import type { ShotLandingLabel } from './reviewShotMapLogic'

function shot(overrides: Partial<RoundHoleShot> = {}): RoundHoleShot {
  return {
    start: [0, 0],
    end: [30, 40],
    club: '一号木',
    lie: 'TeeBox',
    endLie: 'Fairway',
    shotType: 'TEE',
    order: 1,
    synthetic: false,
    ...overrides,
  }
}

describe('chipShape', () => {
  it('maps real to-par onto the shape-coded vocabulary', () => {
    expect(chipShape(-3)).toBe('eagle')
    expect(chipShape(-2)).toBe('eagle')
    expect(chipShape(-1)).toBe('birdie')
    expect(chipShape(0)).toBe('par')
    expect(chipShape(1)).toBe('bogey')
    expect(chipShape(2)).toBe('double')
    expect(chipShape(3)).toBe('triple')
    expect(chipShape(5)).toBe('triple')
  })

  it('treats absent to-par as un-scored (no frame)', () => {
    expect(chipShape(null)).toBe('none')
    expect(chipShape(undefined)).toBe('none')
  })
})

describe('shotDistanceYd', () => {
  it('converts pixel length to yards via the overlay ppm scale', () => {
    // 3-4-5 triangle → 50 px; ppm 1 px/m → 50 m → 55 yd.
    expect(shotDistanceYd([0, 0], [30, 40], 1)).toBe(55)
    // Doubling ppm halves the metres.
    expect(shotDistanceYd([0, 0], [30, 40], 2)).toBe(27)
  })

  it('returns null when an endpoint or scale is missing', () => {
    expect(shotDistanceYd(null, [1, 1], 1)).toBeNull()
    expect(shotDistanceYd([0, 0], null, 1)).toBeNull()
    expect(shotDistanceYd([0, 0], [1, 1], 0)).toBeNull()
  })
})

describe('lieZh', () => {
  it('localizes known lies and drops unknown ones', () => {
    expect(lieZh('Fairway')).toBe('球道')
    expect(lieZh('bunker')).toBe('沙坑')
    expect(lieZh('Green')).toBe('果岭')
    expect(lieZh('mystery')).toBe('')
    expect(lieZh(null)).toBe('')
  })
})

describe('isPuttShot', () => {
  it('detects putts by type or club name', () => {
    expect(isPuttShot(shot({ shotType: 'PUTT' }))).toBe(true)
    expect(isPuttShot(shot({ shotType: null, club: '推杆' }))).toBe(true)
    expect(isPuttShot(shot({ shotType: 'APPROACH', club: '七号铁' }))).toBe(false)
  })
})

describe('buildTimeline', () => {
  it('makes one row per full shot and collapses recorded putts into ×N', () => {
    const rows = buildTimeline(
      [
        shot({ club: '一号木', endLie: 'Fairway' }),
        shot({ club: '五号木', endLie: 'Bunker', shotType: 'APPROACH', start: [30, 40], end: [60, 80] }),
        shot({ club: '推杆', shotType: 'PUTT', start: [60, 80], end: [61, 81] }),
        shot({ club: '推杆', shotType: 'PUTT', start: [61, 81], end: [61, 81] }),
      ],
      1,
    )
    expect(rows).toHaveLength(3)
    expect(rows[0]).toMatchObject({ kind: 'shot', seq: 1, club: '一号木', resultZh: '→ 球道' })
    expect(rows[1]).toMatchObject({ kind: 'shot', seq: 2, club: '五号木', resultZh: '→ 沙坑' })
    expect(rows[2]).toEqual({ kind: 'putt', count: 2 })
  })

  it('flags the synthetic drive honestly', () => {
    const rows = buildTimeline([shot({ synthetic: true, club: null })], 1)
    expect(rows[0]).toMatchObject({ kind: 'shot', club: '未知球杆', resultZh: '未记录 · 推算开球' })
  })
})

describe('shotLandingLabels', () => {
  it('labels each full-shot landing with the CLUB ONLY (no distance/lie)', () => {
    const labels = shotLandingLabels([
      shot({ club: '一号木', endLie: 'Fairway', end: [30, 40] }),
      shot({ club: '推杆', shotType: 'PUTT' }),
    ])
    expect(labels).toHaveLength(1)
    expect(labels[0]).toMatchObject({ x: 30, y: 40, text: '一号木' })
  })

  it('skips the synthetic drive and shots with no known club', () => {
    const labels = shotLandingLabels([
      shot({ club: null, synthetic: true, end: [10, 10] }),
      shot({ club: '  ', end: [20, 20] }),
      shot({ club: '7I', end: [30, 30] }),
    ])
    expect(labels).toHaveLength(1)
    expect(labels[0]).toMatchObject({ x: 30, y: 30, text: '7I' })
  })
})

describe('dodgeLabels', () => {
  // overlay 200×400 → gapX = 28, gapY = 28.
  const overlay = { w: 200, h: 400 }
  const label = (x: number, y: number, text: string): ShotLandingLabel => ({ x, y, text })

  it('anchors the first label and pushes coincident later ones down one gap each', () => {
    const out = dodgeLabels(
      [label(100, 200, 'A'), label(100, 200, 'B'), label(100, 200, 'C')],
      overlay,
    )
    // x + text preserved, original order preserved, first landing never moves.
    expect(out.map((l) => l.text)).toEqual(['A', 'B', 'C'])
    expect(out.map((l) => l.x)).toEqual([100, 100, 100])
    expect(out.map((l) => l.y)).toEqual([200, 228, 256])
  })

  it('separates a near-coincident pair so the pills no longer overlap', () => {
    const [a, b] = dodgeLabels([label(100, 200, 'A'), label(105, 205, 'B')], overlay)
    expect(a).toEqual(label(100, 200, 'A'))
    expect(b.x).toBe(105) // x stays on the true landing
    expect(Math.abs(b.y - a.y)).toBeGreaterThanOrEqual(overlay.h * 0.07)
  })

  it('leaves well-separated labels untouched (vertical or horizontal room)', () => {
    const input = [label(50, 50, 'A'), label(150, 350, 'B'), label(120, 50, 'C')]
    expect(dodgeLabels(input, overlay)).toEqual(input)
  })

  it('dodges upward when nudging down would leave the frame bottom', () => {
    const [a, b] = dodgeLabels([label(100, 395, 'A'), label(100, 395, 'B')], overlay)
    expect(a.y).toBe(395)
    expect(b.y).toBe(367) // 395 − 28: pushed up into open space instead of off-frame
  })

  it('returns labels unchanged for a degenerate (zero-size) overlay', () => {
    const input = [label(10, 10, 'A'), label(10, 10, 'B')]
    expect(dodgeLabels(input, { w: 0, h: 400 })).toEqual(input)
    expect(dodgeLabels([], overlay)).toEqual([])
  })
})

describe('buildTrajectory', () => {
  it('threads tee → landings → hole and dedupes shared vertices', () => {
    const geo = buildTrajectory([
      shot({ start: [10, 10], end: [20, 20] }),
      shot({ start: [20, 20], end: [30, 30] }),
    ])
    expect(geo.points).toEqual([
      [10, 10],
      [20, 20],
      [30, 30],
    ])
    expect(geo.tee).toEqual([10, 10])
    expect(geo.hole).toEqual([30, 30])
    expect(geo.landings).toEqual([[20, 20]])
  })
})
