import type { CoursePrepOverlay } from '../types'

const YARD = 1.09361

function toYards(metres: number): number {
  return Math.round(metres * YARD)
}

export function routeYardageReadout(
  overlay: CoursePrepOverlay,
  cum: number,
  hazardCum?: number,
): { distT: number; toGreen: number; hazard?: number } {
  const routeCum = Math.max(0, Math.min(overlay.ln, cum))
  const out: { distT: number; toGreen: number; hazard?: number } = {
    distT: toYards(routeCum),
    toGreen: toYards(Math.max(0, overlay.ln - routeCum)),
  }
  if (hazardCum !== undefined) {
    out.hazard = toYards(Math.abs(hazardCum - routeCum))
  }
  return out
}
