export type StatRow = Record<string, unknown>

export function asRows(value: unknown): StatRow[] {
  return Array.isArray(value) ? value.filter((row): row is StatRow => row !== null && typeof row === 'object') : []
}

export function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

export function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function formatNumber(value: unknown): string {
  const number = asNumber(value)
  return number === null ? '-' : String(number)
}

export function formatSigned(value: unknown): string {
  const number = asNumber(value)
  if (number === null) return '-'
  return number > 0 ? `+${number}` : String(number)
}

export function formatRefs(value: unknown): string {
  if (!Array.isArray(value)) return '-'
  const refs = value.map((item) => String(item)).filter(Boolean)
  return refs.length ? refs.join(', ') : '-'
}
