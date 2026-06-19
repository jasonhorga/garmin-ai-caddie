const M_TO_YD = 1.09361

export function yards(m: number | null | undefined): number | null {
  if (m === null || m === undefined) return null
  return Math.round(m * M_TO_YD)
}

export function fmtYd(m: number | null | undefined, dash = '—'): string {
  const yd = yards(m)
  if (yd === null) return dash
  return `${yd}码`
}

export function metersFromYards(yd: number): number {
  return Number((yd / M_TO_YD).toFixed(1))
}

/**
 * Normalize a course name's nine-loop separator so the whole app reads the same.
 * Garmin emits "Kawana Hotel Golf Course ~ Oshima Left" while the rounds filter
 * used " - " — collapse both "~" and " - " to " · " (course · nine).
 */
export function cleanCourseName(name: string | null | undefined): string {
  if (!name) return '未知球场'
  return name
    .replace(/\s*~\s*/g, ' · ')
    .replace(/\s+-\s+/g, ' · ')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

/**
 * Friendly day from a raw date/ISO string for product copy — strips the time +
 * timezone that Garmin emits ("2025-09-03T08:53:02+09:00" → "2025-09-03"). Raw
 * fallback if it doesn't look like a date.
 */
export function shortRoundDate(raw: string | null | undefined): string {
  if (!raw) return '未知日期'
  const match = raw.match(/^(\d{4}-\d{2}-\d{2})/)
  if (match) return match[1]
  const parsed = new Date(raw)
  return Number.isNaN(parsed.getTime()) ? raw : parsed.toISOString().slice(0, 10)
}
