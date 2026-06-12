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
