import type { CoursePrepClub, CoursePrepHole } from '../types'

// Pure derivation helpers for the 备战 workbench (hole list + canvas + 球童试算
// inspector). All numbers come from the REAL course-prep payload — nothing is
// invented; rows a hole has no data for are omitted by the callers.

const M_TO_YD = 1.09361

export function toYd(metres: number): number {
  return Math.round(metres * M_TO_YD)
}

// Overlay route length (metres) when geometry exists, else the raw route length.
export function holeLen(hole: CoursePrepHole): number {
  return hole.map?.overlay?.ln ?? hole.route_len_m
}

// Initial ball position (cum, metres) along the route: a par 3 sits the ball on
// the green (the shot IS the whole hole), everything else at the tee-shot landing
// (real landing_m when known, else ~55% of the hole).
export function initialCum(hole: CoursePrepHole): number {
  const ln = holeLen(hole)
  if (hole.par === 3) return ln
  const landing = hole.landing_m ?? ln * 0.55
  return Math.max(0, Math.min(ln, landing))
}

const PAR_WORD: Record<number, string> = { 3: '三杆洞', 4: '四杆洞', 5: '五杆洞' }

// Short descriptor for the hole-list row, derived ONLY from par + hazards.
export function holeDescriptor(hole: CoursePrepHole): string {
  const base = PAR_WORD[hole.par] ?? `Par ${hole.par}`
  const water = hole.hazards?.water_carry?.length ? ' · 跨水' : ''
  return `${base}${water}`
}

export interface HazardSummary {
  waterCount: number
  bunkerCount: number
  text: string
}

export function hazardSummary(hole: CoursePrepHole): HazardSummary {
  const waterCount = hole.hazards?.water_carry?.length ?? 0
  const bunkerCount = hole.hazards?.bunkers?.length ?? 0
  const parts: string[] = []
  if (waterCount) parts.push(`水×${waterCount}`)
  if (bunkerCount) parts.push(`沙×${bunkerCount}`)
  return { waterCount, bunkerCount, text: parts.length ? parts.join(' · ') : '无' }
}

// Yards to CLEAR each water carry from the tee (interval end → yards). Capped at 2.
export function waterCarryYards(hole: CoursePrepHole): number[] {
  return (hole.hazards?.water_carry ?? []).map(([, end]) => toYd(end)).slice(0, 2)
}

// Dogleg / tee-shot landing distance in yards, when the payload carries it.
export function landingYd(hole: CoursePrepHole): number | null {
  return hole.landing_m != null ? toYd(hole.landing_m) : null
}

// Elevation plays-like (tee→green), yards; deltaYd>0 = uphill. Null unless the
// geometry produced a non-zero delta (mirrors the phone/watch caddie glance).
export function slopeYd(hole: CoursePrepHole): number | null {
  const pl = hole.playsLike
  if (pl?.available && typeof pl.deltaYd === 'number' && pl.deltaYd !== 0) return pl.deltaYd
  return null
}

// The distance of the shot the caddie is sizing up: with geometry it is the
// tee→ball distance (draggable); without geometry it is the hole's tee shot
// (landing) or, for a par 3, the whole hole.
export function headlineTargetYd(hole: CoursePrepHole, cum: number): number {
  const overlay = hole.map?.overlay
  if (overlay) return toYd(Math.max(0, Math.min(overlay.ln, cum)))
  if (hole.par === 3) return hole.blue_yards
  const ln = hole.route_len_m
  return toYd(hole.landing_m ?? ln * 0.55)
}

// Remaining distance to the (middle of the) green from the ball. Null when the
// ball already sits on the green (nothing to approach).
export function toGreenYd(hole: CoursePrepHole, cum: number): number | null {
  const overlay = hole.map?.overlay
  if (overlay) {
    const clamped = Math.max(0, Math.min(overlay.ln, cum))
    const remaining = toYd(Math.max(0, overlay.ln - clamped))
    return remaining > 0 ? remaining : null
  }
  if (hole.par === 3) return null
  const ln = hole.route_len_m
  const landing = hole.landing_m ?? ln * 0.55
  const remaining = toYd(Math.max(0, ln - landing))
  return remaining > 0 ? remaining : null
}

export interface ClubReco {
  name: string
  yd: number
  on: boolean
}

// Up to 3 bag clubs bracketing the target yardage, nearest one marked
// recommended. Ordered long→short like a real bag.
export function recosForTarget(clubs: CoursePrepClub[], targetYd: number): ClubReco[] {
  const valid = clubs.filter((club) => typeof club.yd === 'number' && Number.isFinite(club.yd))
  if (valid.length === 0) return []
  const sorted = [...valid].sort((a, b) => b.yd - a.yd)
  let nearest = 0
  let bestDelta = Infinity
  sorted.forEach((club, index) => {
    const delta = Math.abs(club.yd - targetYd)
    if (delta < bestDelta) {
      bestDelta = delta
      nearest = index
    }
  })
  let start = nearest - 1
  if (start < 0) start = 0
  if (start > sorted.length - 3) start = Math.max(0, sorted.length - 3)
  const window = sorted.slice(start, start + 3)
  const recommended = sorted[nearest].name
  return window.map((club) => ({ name: club.name, yd: club.yd, on: club.name === recommended }))
}
