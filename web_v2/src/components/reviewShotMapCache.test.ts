import { beforeEach, describe, expect, it } from 'vitest'
import type { RoundHoleShotMapResponse } from '../types'
import {
  invalidateReviewShotMapCache,
  readReviewShotMapCache,
  REVIEW_SHOT_MAP_CACHE_MAX_ENTRIES,
  REVIEW_SHOT_MAP_CACHE_STORAGE_KEY,
  REVIEW_SHOT_MAP_CACHE_TTL_MS,
  writeReviewShotMapCache,
} from './reviewShotMapCache'

function response(roundRef: string, hole: number, geometryRevision = `geometry-${roundRef}-${hole}`): RoundHoleShotMapResponse {
  return {
    schema: 'ai-caddie-round-hole-shotmap-v1',
    found: true,
    roundRef,
    hole,
    geometryRevision,
    mapKind: 'prodgeometry',
    map: { image: 'data:image/png;base64,AAAA', overlay: { w: 1, h: 1, ppm: 1, ln: 1, route: [] } },
    shots: [],
    missingData: [],
  }
}

describe('review shot-map persistence', () => {
  beforeEach(() => window.localStorage.removeItem(REVIEW_SHOT_MAP_CACHE_STORAGE_KEY))

  it('isolates entries by player, round and hole', () => {
    const first = response('round-a', 1)
    const otherHole = response('round-a', 2)
    const otherRound = response('round-b', 1)
    const otherPlayer = response('round-a', 1, 'other-player-geometry')
    writeReviewShotMapCache('player-a', first, 1_000)
    writeReviewShotMapCache('player-a', otherHole, 1_001)
    writeReviewShotMapCache('player-b', otherPlayer, 1_002)
    writeReviewShotMapCache('player-a', otherRound, 1_003)

    expect(readReviewShotMapCache('player-a', 'round-a', 1, 1_004)).toEqual(first)
    expect(readReviewShotMapCache('player-a', 'round-a', 2, 1_004)).toEqual(otherHole)
    expect(readReviewShotMapCache('player-a', 'round-b', 1, 1_004)).toEqual(otherRound)
    expect(readReviewShotMapCache('player-b', 'round-a', 1, 1_004)).toEqual(otherPlayer)
    expect(readReviewShotMapCache('player-c', 'round-a', 1, 1_004)).toBeUndefined()
  })

  it('expires entries and evicts the oldest entries at the deterministic capacity limit', () => {
    const now = 50_000
    writeReviewShotMapCache('player-a', response('expired', 1), now - REVIEW_SHOT_MAP_CACHE_TTL_MS)
    expect(readReviewShotMapCache('player-a', 'expired', 1, now)).toBeUndefined()

    for (let index = 0; index < REVIEW_SHOT_MAP_CACHE_MAX_ENTRIES + 2; index += 1) {
      writeReviewShotMapCache('player-a', response(`round-${index}`, 1), now + index)
    }
    expect(readReviewShotMapCache('player-a', 'round-0', 1, now + 100)).toBeUndefined()
    expect(readReviewShotMapCache('player-a', 'round-1', 1, now + 100)).toBeUndefined()
    expect(readReviewShotMapCache('player-a', `round-${REVIEW_SHOT_MAP_CACHE_MAX_ENTRIES + 1}`, 1, now + 100)).toBeDefined()
  })

  it('ignores malformed entries and geometry-revision mismatches without throwing', () => {
    window.localStorage.setItem(
      REVIEW_SHOT_MAP_CACHE_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        entries: [
          { key: '["player-a","round-a",1]', playerNamespace: 'player-a', roundRef: 'round-a', hole: 1, geometryRevision: 'wrong', cachedAt: 1, response: response('round-a', 1) },
          { key: 'garbage' },
        ],
      }),
    )
    expect(readReviewShotMapCache('player-a', 'round-a', 1, 2_000)).toBeUndefined()
    expect(window.localStorage.getItem(REVIEW_SHOT_MAP_CACHE_STORAGE_KEY)).toBeNull()
  })

  it('tolerates unavailable storage and invalid responses', () => {
    const original = window.localStorage.getItem
    Object.defineProperty(window.localStorage, 'getItem', { configurable: true, value: () => { throw new Error('storage blocked') } })
    expect(() => writeReviewShotMapCache('player-a', { nope: true }, 1)).not.toThrow()
    expect(readReviewShotMapCache('player-a', 'round-a', 1, 1)).toBeUndefined()
    Object.defineProperty(window.localStorage, 'getItem', { configurable: true, value: original })
  })

  it('invalidates only the corrected round and hole', () => {
    const first = response('round-a', 1)
    const second = response('round-a', 2)
    writeReviewShotMapCache('player-a', first, 1_000)
    writeReviewShotMapCache('player-a', second, 1_000)
    invalidateReviewShotMapCache('player-a', 'round-a', 1)
    expect(readReviewShotMapCache('player-a', 'round-a', 1, 1_001)).toBeUndefined()
    expect(readReviewShotMapCache('player-a', 'round-a', 2, 1_001)).toEqual(second)
  })
})
