import type { RoundHoleShot } from '../types'

const M_TO_YD = 1.09361

// Shape-coded score chip vocabulary (design system §一): under-par is a circle
// (birdie ○, eagle ◎ double ring), over-par is a square (bogey □, double ⊡ double
// ring), triple-or-worse is a triangle △, par has no frame. Derived from the real
// to-par so the shape always reflects the score actually played.
export type ChipShape = 'eagle' | 'birdie' | 'par' | 'bogey' | 'double' | 'triple' | 'none'

export function chipShape(toPar: number | null | undefined): ChipShape {
  if (toPar === null || toPar === undefined || Number.isNaN(toPar)) return 'none'
  const rounded = Math.round(toPar)
  if (rounded <= -2) return 'eagle'
  if (rounded === -1) return 'birdie'
  if (rounded === 0) return 'par'
  if (rounded === 1) return 'bogey'
  if (rounded === 2) return 'double'
  return 'triple'
}

const SHAPE_ZH: Record<ChipShape, string> = {
  eagle: '老鹰以上',
  birdie: '小鸟',
  par: '标准杆',
  bogey: '柏忌',
  double: '双柏忌',
  triple: '三柏忌以上',
  none: '未记分',
}

export function chipShapeZh(shape: ChipShape): string {
  return SHAPE_ZH[shape]
}

// Straight-line shot distance in yards from the two display-pixel endpoints and
// the overlay's pixels-per-metre scale (`ppm`). Lateral misses read honestly —
// this is the true ball-flight length, not a projection onto the playing line.
export function shotDistanceYd(
  start: [number, number] | null,
  end: [number, number] | null,
  ppm: number | null | undefined,
): number | null {
  if (!start || !end || !ppm || ppm <= 0) return null
  const metres = Math.hypot(end[0] - start[0], end[1] - start[1]) / ppm
  return Math.round(metres * M_TO_YD)
}

const LIE_ZH: Record<string, string> = {
  teebox: '发球台',
  tee: '发球台',
  fairway: '球道',
  green: '果岭',
  fringe: '果岭边',
  rough: '长草',
  bunker: '沙坑',
  sand: '沙坑',
  water: '水',
  hazard: '障碍',
  penalty: '罚杆区',
  recovery: '障碍区',
  ob: '界外',
  outofbounds: '界外',
}

export function lieZh(lie: string | null | undefined): string {
  if (!lie) return ''
  return LIE_ZH[String(lie).trim().toLowerCase()] ?? ''
}

// Recorded putts arrive with a PUTT shot type; Garmin sometimes files them with a
// blank clubId but a putter name, so fall back to the club label.
export function isPuttShot(shot: RoundHoleShot): boolean {
  if (typeof shot.shotType === 'string' && shot.shotType.trim().toUpperCase() === 'PUTT') return true
  const club = (shot.club ?? '').toLowerCase()
  return club.includes('推') || club.includes('putt')
}

export function seqLabel(seq: number): string {
  return seq <= 1 ? '开球' : `${seq}杆`
}

export function clubDisplay(shot: RoundHoleShot): string {
  if (isPuttShot(shot)) return '推杆'
  const club = shot.club?.trim()
  return club && club.length > 0 ? club : '未知球杆'
}

export interface TimelineShotRow {
  kind: 'shot'
  seq: number
  club: string
  distanceYd: number | null
  resultZh: string
  synthetic: boolean
}

export interface TimelinePuttRow {
  kind: 'putt'
  count: number
}

export type TimelineRow = TimelineShotRow | TimelinePuttRow

// The right-column 杆序 timeline: full shots become one row each (club · distance ·
// where it finished); recorded putts collapse into a single "推杆 ×N" row, the way
// the mockup groups the two-putt finish. Distances need the overlay `ppm` scale.
export function buildTimeline(shots: RoundHoleShot[], ppm: number | null | undefined): TimelineRow[] {
  const rows: TimelineRow[] = []
  let seq = 0
  let putts = 0
  for (const shot of shots) {
    if (isPuttShot(shot)) {
      putts += 1
      continue
    }
    seq += 1
    const endLie = lieZh(shot.endLie)
    const resultZh = shot.synthetic ? '未记录 · 推算开球' : endLie ? `→ ${endLie}` : ''
    rows.push({
      kind: 'shot',
      seq,
      club: clubDisplay(shot),
      distanceYd: shotDistanceYd(shot.start, shot.end, ppm),
      resultZh,
      synthetic: shot.synthetic,
    })
  }
  if (putts > 0) rows.push({ kind: 'putt', count: putts })
  return rows
}

export interface ShotLandingLabel {
  x: number
  y: number
  text: string
}

// On-map labels at each full-shot landing: the CLUB ONLY (Garmin's review style —
// "用什么杆打的", no distance/lie text; that detail lives in the right-column 杆序
// timeline). Putts, shots missing an endpoint, and the synthetic (推算) drive whose
// club we don't actually know are skipped so the map stays sparse and every label is
// a real, known club.
export function shotLandingLabels(shots: RoundHoleShot[]): ShotLandingLabel[] {
  const labels: ShotLandingLabel[] = []
  for (const shot of shots) {
    if (isPuttShot(shot) || shot.synthetic || !shot.end) continue
    const club = shot.club?.trim()
    if (!club) continue
    labels.push({ x: shot.end[0], y: shot.end[1], text: clubDisplay(shot) })
  }
  return labels
}

export interface TrajectoryGeometry {
  points: Array<[number, number]>
  landings: Array<[number, number]>
  tee: [number, number] | null
  hole: [number, number] | null
}

// The yellow actual-trajectory polyline + its dots. Points thread tee → each
// landing → hole; `landings` are the intermediate yellow dots, `hole` the final
// (red) resting point. Consecutive duplicate pixels are collapsed so a recorded
// shot that starts exactly where the previous ended doesn't double a vertex.
export function buildTrajectory(shots: RoundHoleShot[]): TrajectoryGeometry {
  const points: Array<[number, number]> = []
  const push = (p: [number, number] | null) => {
    if (!p) return
    const last = points[points.length - 1]
    if (last && last[0] === p[0] && last[1] === p[1]) return
    points.push(p)
  }
  for (const shot of shots) {
    push(shot.start)
    push(shot.end)
  }
  const tee = points.length > 0 ? points[0] : null
  const hole = points.length > 1 ? points[points.length - 1] : null
  const landings = points.slice(1, Math.max(1, points.length - 1))
  return { points, landings, tee, hole }
}
