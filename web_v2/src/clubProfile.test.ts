import { describe, expect, it } from 'vitest'
import { normalizeMeasuredClubToken, shortClubLabel, tokenRank } from './clubProfile'

describe('shortClubLabel', () => {
  it('maps canonical tokens to compact ladder labels', () => {
    expect(shortClubLabel('driver')).toBe('1W')
    expect(shortClubLabel('wood3')).toBe('3W')
    expect(shortClubLabel('iron5')).toBe('5i')
    expect(shortClubLabel('pw')).toBe('PW')
    expect(shortClubLabel('wedge56')).toBe('56°')
    expect(shortClubLabel('putter')).toBe('PT')
  })

  it('falls back to the upper-cased token for unknown clubs', () => {
    expect(shortClubLabel('mystery')).toBe('MYSTERY')
  })
})

describe('tokenRank', () => {
  it('orders the driver ahead of the irons and wedges', () => {
    expect(tokenRank('driver')).toBeLessThan(tokenRank('iron5'))
    expect(tokenRank('iron5')).toBeLessThan(tokenRank('pw'))
  })

  it('sinks unknown tokens to the bottom', () => {
    expect(tokenRank('mystery')).toBeGreaterThan(tokenRank('putter'))
  })
})

describe('normalizeMeasuredClubToken', () => {
  it('resolves driver codes', () => {
    expect(normalizeMeasuredClubToken('1D')).toBe('driver')
    expect(normalizeMeasuredClubToken('D')).toBe('driver')
    expect(normalizeMeasuredClubToken('Driver')).toBe('driver')
    expect(normalizeMeasuredClubToken('1W')).toBe('driver')
  })

  it('resolves fairway woods that exist in the catalog', () => {
    expect(normalizeMeasuredClubToken('3W')).toBe('wood3')
    expect(normalizeMeasuredClubToken('5W')).toBe('wood5')
    // 2W / 4W have no catalog token → unresolved (no enrichment, never a crash).
    expect(normalizeMeasuredClubToken('4W')).toBeNull()
  })

  it('resolves hybrids and irons', () => {
    expect(normalizeMeasuredClubToken('3H')).toBe('hybrid3')
    expect(normalizeMeasuredClubToken('4HY')).toBe('hybrid4')
    expect(normalizeMeasuredClubToken('5I')).toBe('iron5')
    expect(normalizeMeasuredClubToken('8I')).toBe('iron8')
    expect(normalizeMeasuredClubToken('I7')).toBe('iron7')
  })

  it('resolves wedges by name and by loft', () => {
    expect(normalizeMeasuredClubToken('PW')).toBe('pw')
    expect(normalizeMeasuredClubToken('SW')).toBe('sw')
    expect(normalizeMeasuredClubToken('56°')).toBe('wedge56')
    // 48° has no catalog token.
    expect(normalizeMeasuredClubToken('48°')).toBeNull()
  })

  it('tolerates the retired suffix and whitespace', () => {
    expect(normalizeMeasuredClubToken('5I 退役')).toBe('iron5')
    expect(normalizeMeasuredClubToken('  pw  ')).toBe('pw')
  })

  it('returns null for empty or ambiguous codes', () => {
    expect(normalizeMeasuredClubToken('')).toBeNull()
    expect(normalizeMeasuredClubToken(null)).toBeNull()
    expect(normalizeMeasuredClubToken('P')).toBeNull()
  })
})
