import type { CoursePrepOverlay } from '../types'

const YARD = 1.09361

function toYards(metres: number): number {
  return Math.round(metres * YARD)
}

function clampRouteCum(overlay: CoursePrepOverlay, cum: number): number {
  return Math.max(0, Math.min(overlay.ln, cum))
}

export interface HazardIntervalReadout {
  toStart: number
  toClear: number
  isBehind: boolean
  isInside: boolean
  isCleared: boolean
}

export function routeYardageReadout(
  overlay: CoursePrepOverlay,
  cum: number,
  hazardCum?: number,
): { distT: number; toGreen: number; hazard?: number } {
  const routeCum = clampRouteCum(overlay, cum)
  const out: { distT: number; toGreen: number; hazard?: number } = {
    distT: toYards(routeCum),
    toGreen: toYards(Math.max(0, overlay.ln - routeCum)),
  }
  if (hazardCum !== undefined) {
    out.hazard = toYards(Math.abs(hazardCum - routeCum))
  }
  return out
}

export function routeIntervalReadout(
  overlay: CoursePrepOverlay,
  cum: number,
  startCum: number,
  endCum: number,
): HazardIntervalReadout {
  const routeCum = clampRouteCum(overlay, cum)
  const start = Math.max(0, Math.min(overlay.ln, Math.min(startCum, endCum)))
  const end = Math.max(0, Math.min(overlay.ln, Math.max(startCum, endCum)))

  return {
    toStart: toYards(Math.max(0, start - routeCum)),
    toClear: toYards(Math.max(0, end - routeCum)),
    isBehind: routeCum < start,
    isInside: routeCum >= start && routeCum <= end,
    isCleared: routeCum > end,
  }
}
