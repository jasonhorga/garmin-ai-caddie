import type { RoundHoleShotMapResponse } from '../types'

// Shot maps are immutable for a short visit window, but corrections and geometry
// updates must become visible without requiring a manual storage reset.
export const REVIEW_SHOT_MAP_CACHE_STORAGE_KEY = 'ai-caddie.review-shotmap-cache.v1'
export const REVIEW_SHOT_MAP_CACHE_TTL_MS = 5 * 60 * 1000
export const REVIEW_SHOT_MAP_CACHE_MAX_ENTRIES = 24
// Embedded map PNGs can be large. Keep the whole cache comfortably below the
// usual ~5 MB localStorage quota; oversized responses remain in memory only.
export const REVIEW_SHOT_MAP_CACHE_MAX_BYTES = 1_500_000

const RESPONSE_SCHEMA = 'ai-caddie-round-hole-shotmap-v1'

interface StoredShotMapEntry {
  key: string
  playerNamespace: string
  roundRef: string
  hole: number
  geometryRevision: string | null
  cachedAt: number
  response: RoundHoleShotMapResponse
}

interface StoredShotMapStore {
  version: 1
  entries: StoredShotMapEntry[]
}

function normalizedNamespace(playerNamespace: string | undefined | null): string | null {
  const value = playerNamespace?.trim()
  return value ? value : null
}

function entryKey(playerNamespace: string, roundRef: string, hole: number): string {
  // JSON encoding keeps namespaces/round refs containing ':' isolated too.
  return JSON.stringify([playerNamespace, roundRef, hole])
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** Runtime guard for data crossing the fetch/localStorage boundary. */
export function isValidRoundHoleShotMapResponse(value: unknown, roundRef: string, hole: number): value is RoundHoleShotMapResponse {
  if (!isRecord(value)) return false
  if (value.schema !== RESPONSE_SCHEMA || value.roundRef !== roundRef || value.hole !== hole) return false
  if (typeof value.found !== 'boolean' || !Array.isArray(value.shots) || !Array.isArray(value.missingData)) return false
  if (value.geometryRevision !== undefined && value.geometryRevision !== null && typeof value.geometryRevision !== 'string') return false
  if (value.map === null) return true
  if (!isRecord(value.map) || typeof value.map.image !== 'string' || !isRecord(value.map.overlay)) return false
  return true
}

function isValidStoredEntry(value: unknown): value is StoredShotMapEntry {
  if (!isRecord(value)) return false
  if (typeof value.key !== 'string' || typeof value.playerNamespace !== 'string' || typeof value.roundRef !== 'string') return false
  if (typeof value.hole !== 'number' || !Number.isInteger(value.hole) || typeof value.cachedAt !== 'number' || !Number.isFinite(value.cachedAt)) return false
  if (value.geometryRevision !== null && typeof value.geometryRevision !== 'string') return false
  if (!isValidRoundHoleShotMapResponse(value.response, value.roundRef, value.hole)) return false
  if ((value.response.geometryRevision ?? null) !== value.geometryRevision) return false
  return value.key === entryKey(value.playerNamespace, value.roundRef, value.hole)
}

function readStore(): StoredShotMapStore | null {
  try {
    const raw = window.localStorage.getItem(REVIEW_SHOT_MAP_CACHE_STORAGE_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!isRecord(parsed) || parsed.version !== 1 || !Array.isArray(parsed.entries)) return null
    return { version: 1, entries: parsed.entries as StoredShotMapEntry[] }
  } catch {
    return null
  }
}

function writeStore(store: StoredShotMapStore): void {
  try {
    window.localStorage.setItem(REVIEW_SHOT_MAP_CACHE_STORAGE_KEY, JSON.stringify(store))
  } catch {
    // Quota/security errors are expected in private browsing and must not affect review.
  }
}

function removeStore(): void {
  try {
    window.localStorage.removeItem(REVIEW_SHOT_MAP_CACHE_STORAGE_KEY)
  } catch {
    // Ignore unavailable storage.
  }
}

function pruneEntries(entries: unknown[], now: number): { entries: StoredShotMapEntry[]; changed: boolean } {
  const valid = entries.filter(isValidStoredEntry)
  const live = valid.filter((entry) => now - entry.cachedAt >= 0 && now - entry.cachedAt < REVIEW_SHOT_MAP_CACHE_TTL_MS)
  let changed = valid.length !== entries.length || live.length !== valid.length
  if (live.length > REVIEW_SHOT_MAP_CACHE_MAX_ENTRIES) {
    // Stable oldest-first eviction; key breaks equal timestamps deterministically.
    live.sort((left, right) => left.cachedAt - right.cachedAt || left.key.localeCompare(right.key))
    live.splice(0, live.length - REVIEW_SHOT_MAP_CACHE_MAX_ENTRIES)
    changed = true
  }
  return { entries: live, changed }
}

function boundedEntries(entries: StoredShotMapEntry[]): StoredShotMapEntry[] {
  const bounded = [...entries]
  bounded.sort((left, right) => left.cachedAt - right.cachedAt || left.key.localeCompare(right.key))
  while (bounded.length && JSON.stringify({ version: 1, entries: bounded }).length > REVIEW_SHOT_MAP_CACHE_MAX_BYTES) bounded.shift()
  return bounded
}

function availableNamespace(playerNamespace: string | undefined | null): string | null {
  return normalizedNamespace(playerNamespace)
}

export function readReviewShotMapCache(
  playerNamespace: string | undefined | null,
  roundRef: string,
  hole: number,
  now = Date.now(),
): RoundHoleShotMapResponse | undefined {
  const namespace = availableNamespace(playerNamespace)
  if (!namespace) return undefined
  const store = readStore()
  if (!store) return undefined
  const pruned = pruneEntries(store.entries, now)
  if (pruned.changed) {
    if (pruned.entries.length) writeStore({ version: 1, entries: pruned.entries })
    else removeStore()
  }
  return pruned.entries.find((entry) => entry.key === entryKey(namespace, roundRef, hole))?.response
}

export function writeReviewShotMapCache(
  playerNamespace: string | undefined | null,
  response: unknown,
  now = Date.now(),
): void {
  const namespace = availableNamespace(playerNamespace)
  if (!namespace || !isRecord(response) || typeof response.roundRef !== 'string' || typeof response.hole !== 'number') return
  if (!isValidRoundHoleShotMapResponse(response, response.roundRef, response.hole)) return
  if (!response.found || response.map === null) return
  const store = readStore() ?? { version: 1 as const, entries: [] }
  const pruned = pruneEntries(store.entries, now)
  const key = entryKey(namespace, response.roundRef, response.hole)
  const next: StoredShotMapEntry = {
    key,
    playerNamespace: namespace,
    roundRef: response.roundRef,
    hole: response.hole,
    geometryRevision: response.geometryRevision ?? null,
    cachedAt: now,
    response,
  }
  const entries = [...pruned.entries.filter((entry) => entry.key !== key), next]
  const bounded = boundedEntries(pruneEntries(entries, now).entries)
  if (bounded.length) writeStore({ version: 1, entries: bounded })
  else removeStore()
}

export function invalidateReviewShotMapCache(
  playerNamespace: string | undefined | null,
  roundRef: string,
  hole: number,
): void {
  const namespace = availableNamespace(playerNamespace)
  if (!namespace) return
  const store = readStore()
  if (!store) return
  const key = entryKey(namespace, roundRef, hole)
  const entries = store.entries.filter((entry) => entry && typeof entry === 'object' && entry.key !== key)
  if (entries.length) writeStore({ version: 1, entries })
  else removeStore()
}
