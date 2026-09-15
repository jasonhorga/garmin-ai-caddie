/**
 * Presentation helpers for names already supplied by Garmin.
 *
 * The web client must never translate a provider name or infer one from a
 * global id. The backend `name` field is the cross-client physical-venue
 * authority; `segmentLabel` is independent layout metadata. Venue/segment
 * fields remain compatibility fallbacks for older payloads.
 */

export interface CourseNameFields {
  name?: unknown
  venueName?: unknown
  venueNameSource?: unknown
  segmentLabel?: unknown
}

export type CourseNameInput = CourseNameFields | string | null | undefined

export const GARMIN_SNAPSHOT_NAME_SOURCE = 'garmin_scorecard_snapshot'

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export function normalizeCourseName(value: unknown): string {
  return text(value)
    .split(/\s+/)
    .filter(Boolean)
    .join(' ')
    .split('~')
    .map((part) => part.trim())
    .filter(Boolean)
    .join(' ~ ')
}

export function splitCourseName(value: unknown): { venue: string; suffix: string | null } {
  const normalized = normalizeCourseName(value)
  if (!normalized) return { venue: '', suffix: null }
  const [firstVenue, ...rest] = normalized.split(' ~ ')
  let venue = firstVenue.trim()
  let suffix = rest.join(' ~ ').trim() || null
  const tokens = venue.split(/\s+/).filter(Boolean)
  const trailing = tokens[tokens.length - 1]
  if (tokens.length > 1 && trailing && isCompositeSegment(trailing)) {
    venue = tokens.slice(0, -1).join(' ')
    if (!suffix) suffix = trailing
  }
  return { venue, suffix }
}

export function containsCjk(value: unknown): boolean {
  return /[\u3400-\u4dbf\u4e00-\u9fff\u{20000}-\u{2fa1f}]/u.test(text(value))
}

export function isCompositeSegment(value: unknown): boolean {
  const normalized = text(value)
  if (!normalized) return false
  if (normalized.includes('/') || normalized.includes('+')) return true
  return /^[A-H]{2,4}$/i.test(normalized.replace(/\s+/g, ''))
}

function fieldsFor(input: CourseNameInput): CourseNameFields {
  return typeof input === 'string' ? { name: input } : input ?? {}
}

function safeSegment(value: unknown): string | null {
  const segment = text(value)
  return segment && !isCompositeSegment(segment) ? segment : null
}

/** Return the venue part of the backend-owned display name. */
export function courseVenueName(input: CourseNameInput, fallback = '未知球场'): string {
  return canonicalCourseVenueName(input, fallback)
}

/** Physical venue title for round/history surfaces; layout labels belong beside it. */
export function physicalCourseName(input: CourseNameInput, fallback = '未知球场'): string {
  return canonicalCourseVenueName(input, fallback)
}

/** Return a single factual layout label; composite played routes are not selectable labels. */
export function courseSegmentName(input: CourseNameInput): string | null {
  const fields = fieldsFor(input)
  const providerSegment = safeSegment(splitCourseName(selectableCourseName(text(fields.name), '')).suffix)
  return providerSegment ?? safeSegment(fields.segmentLabel)
}

/** Return the backend-owned selectable-course name without inventing a translation. */
export function displayCourseName(input: CourseNameInput, fallback = '未知球场'): string {
  return canonicalCourseName(input, fallback)
}

export function selectableCourseName(value: unknown, fallback = '未知球场'): string {
  const normalized = normalizeCourseName(value)
  if (!normalized) return fallback
  const split = splitCourseName(normalized)
  return split.suffix && isCompositeSegment(split.suffix) ? split.venue : normalized
}

/**
 * Resolve the same backend-owned name contract used by iPhone and Watch.
 * Only an explicitly marked Garmin snapshot may replace the provider venue;
 * route/loop labels remain separate facts and composite routes are removed.
 */
export function canonicalCourseName(input: CourseNameInput, fallback = '未知球场'): string {
  const fields = fieldsFor(input)
  const provider = selectableCourseName(text(fields.name), fallback)
  const providerParts = splitCourseName(provider)
  const trustedVenue = text(fields.venueNameSource).toLowerCase() === GARMIN_SNAPSHOT_NAME_SOURCE
    ? splitCourseName(fields.venueName).venue
    : ''
  // An unmarked venueName may be a stale/manual cache alias. It is never a
  // fallback authority when the provider name is absent; only the explicit
  // Garmin snapshot marker can replace the provider venue.
  const venue = trustedVenue || providerParts.venue
  return venue || provider
}

export function canonicalCourseVenueName(input: CourseNameInput, fallback = '未知球场'): string {
  return splitCourseName(canonicalCourseName(input, fallback)).venue || fallback
}
