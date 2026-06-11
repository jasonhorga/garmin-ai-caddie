import { describe, expect, it } from 'vitest'
import { yards, fmtYd, metersFromYards } from './units'

describe('yards', () => {
  it('converts metres to integer yards using 1 m = 1.09361 yd', () => {
    expect(yards(100)).toBe(109)    // 100 × 1.09361 = 109.361 → 109
    expect(yards(360)).toBe(394)    // 360 × 1.09361 = 393.6996 → 394
    expect(yards(393)).toBe(430)    // 393 × 1.09361 = 429.789 → 430
  })

  it('returns 0 for 0 metres', () => {
    expect(yards(0)).toBe(0)
  })

  it('returns null for null input', () => {
    expect(yards(null)).toBeNull()
  })

  it('returns null for undefined input', () => {
    expect(yards(undefined)).toBeNull()
  })
})

describe('fmtYd', () => {
  it('formats metres as integer yards with 码 suffix', () => {
    expect(fmtYd(100)).toBe('109码')
    expect(fmtYd(393)).toBe('430码')
  })

  it('returns the dash placeholder for null', () => {
    expect(fmtYd(null)).toBe('—')
  })

  it('returns the dash placeholder for undefined', () => {
    expect(fmtYd(undefined)).toBe('—')
  })

  it('accepts a custom dash string', () => {
    expect(fmtYd(null, 'N/A')).toBe('N/A')
    expect(fmtYd(undefined, '-')).toBe('-')
  })
})

describe('metersFromYards', () => {
  it('converts yards back to metres with 1 decimal place', () => {
    // 100 / 1.09361 = 91.440...  → 91.4
    expect(metersFromYards(100)).toBe(91.4)
    // 430 / 1.09361 = 393.19... → 393.2
    expect(metersFromYards(430)).toBe(393.2)
  })

  it('returns 0.0 for 0 yards', () => {
    expect(metersFromYards(0)).toBe(0)
  })
})
