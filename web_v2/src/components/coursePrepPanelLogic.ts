import type { CoursePrepOverlay } from '../types'

const YARD = 1.09361

function toYards(metres: number): number {
  return Math.round(metres * YARD)
}

function clampRouteCum(overlay: CoursePrepOverlay, cum: number): number {
  return Math.max(0, Math.min(overlay.ln, cum))
}

// Route-polyline drag helpers shared by PrepHoleCard and the 实战 LiveSandbox
// map canvas. Overlay route rows are [px, py, cumMetres] in DISPLAY PIXELS
// (post-downsample hole render frame) with a true-metre cumulative stamp.

// Point on the route polyline at cumulative distance `cum` (px coords).
export function atCum(route: CoursePrepOverlay['route'], cum: number): { x: number; y: number } {
  for (let i = 0; i < route.length - 1; i += 1) {
    const a = route[i]
    const b = route[i + 1]
    if (b[2] >= cum) {
      const t = b[2] - a[2] ? (cum - a[2]) / (b[2] - a[2]) : 0
      return { x: a[0] + (b[0] - a[0]) * t, y: a[1] + (b[1] - a[1]) * t }
    }
  }
  const end = route[route.length - 1]
  return { x: end[0], y: end[1] }
}

// Cumulative route distance (metres) of the route point nearest to the
// pointer (px coords) — snaps free drags onto the playing line.
export function nearestCum(route: CoursePrepOverlay['route'], px: number, py: number): number {
  let best = 0
  let bestDist = Infinity
  for (let i = 0; i < route.length - 1; i += 1) {
    const a = route[i]
    const b = route[i + 1]
    const vx = b[0] - a[0]
    const vy = b[1] - a[1]
    const len2 = vx * vx + vy * vy || 1
    let t = ((px - a[0]) * vx + (py - a[1]) * vy) / len2
    t = Math.max(0, Math.min(1, t))
    const qx = a[0] + vx * t
    const qy = a[1] + vy * t
    const d = Math.hypot(px - qx, py - qy)
    if (d < bestDist) {
      bestDist = d
      best = a[2] + (b[2] - a[2]) * t
    }
  }
  return best
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

export interface HazardLabelRow {
  y: number
  text: string
}

export interface HazardLabelPlacement {
  labelY: number
  showLabel: boolean
}

// Greedy vertical de-overlap for the hole-map hazard distance labels. Each row
// carries a label's natural baseline y (the hazard marker's y plus the text
// baseline offset) and its rendered text. Two hazards close together on the
// route would otherwise stack their labels on the same pixels, so this walks
// the labels top-to-bottom and pushes each one down to clear the previous by at
// least `minGap` px; a label that is an EXACT duplicate of the one it would
// collide with (e.g. two adjacent "沙12y" bunkers) is hidden instead of stacked.
// The hazard markers (circles) stay put — only the text moves. Returns one
// placement per input row IN THE ORIGINAL ORDER so callers can zip it back onto
// their markers.
export function layoutHazardLabels(rows: HazardLabelRow[], minGap: number): HazardLabelPlacement[] {
  const placements: HazardLabelPlacement[] = rows.map((row) => ({ labelY: row.y, showLabel: true }))
  const order = rows
    .map((row, index) => ({ index, y: row.y, text: row.text }))
    .sort((a, b) => a.y - b.y || a.index - b.index)
  let lastY = -Infinity
  let lastText: string | null = null
  for (const item of order) {
    const collides = item.y < lastY + minGap
    if (collides && item.text === lastText) {
      placements[item.index].showLabel = false
      continue
    }
    const labelY = collides ? lastY + minGap : item.y
    placements[item.index].labelY = labelY
    lastY = labelY
    lastText = item.text
  }
  return placements
}
