/**
 * Presentation helpers for names already supplied by Garmin.
 *
 * The web client must never translate a provider name or infer one from a
 * global id. It may only choose a localized venue field returned by the API,
 * retain a factual single-layout suffix, and hide a composite played route
 * (A/C, A+B, AB, ... ) from selectable-course labels.
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
  const [venue, ...rest] = normalized.split(' ~ ')
  const suffix = rest.join(' ~ ').trim()
  return { venue: venue.trim(), suffix: suffix || null }
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

/** Return the venue spelling Garmin already supplied, preferring an existing CJK value. */
export function courseVenueName(input: CourseNameInput, fallback = '未知球场'): string {
  const fields = fieldsFor(input)
  const nameParts = splitCourseName(fields.name)
  const trustedVenue = text(fields.venueNameSource).toLowerCase() === GARMIN_SNAPSHOT_NAME_SOURCE
    ? text(fields.venueName)
    : ''
  const venues = [trustedVenue, nameParts.venue].filter(Boolean)
  return venues.find(containsCjk) ?? venues[0] ?? fallback
}

/** Return a single factual layout label; composite played routes are not selectable labels. */
export function courseSegmentName(input: CourseNameInput): string | null {
  const fields = fieldsFor(input)
  const providerSegment = safeSegment(splitCourseName(fields.name).suffix)
  return providerSegment ?? safeSegment(fields.segmentLabel)
}

/** Build the user-visible selectable-course name without translating or inventing text. */
export function displayCourseName(input: CourseNameInput, fallback = '未知球场'): string {
  const fields = fieldsFor(input)
  const venue = courseVenueName(fields, fallback)
  if (!venue || venue === fallback && !text(fields.name) && !text(fields.venueName)) return fallback
  const segment = courseSegmentName(fields)
  return segment ? `${venue} ~ ${segment}` : venue
}

export function selectableCourseName(value: unknown, fallback = '未知球场'): string {
  const normalized = normalizeCourseName(value)
  if (!normalized) return fallback
  const split = splitCourseName(normalized)
  return split.suffix && isCompositeSegment(split.suffix) ? split.venue : normalized
}
