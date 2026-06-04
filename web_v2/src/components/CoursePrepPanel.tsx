import { useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import type { CoursePrepClub, CoursePrepHole, CoursePrepOverlay, CoursePrepResponse } from '../types'
import { fetchCoursePrep } from '../api'
import { routeIntervalReadout, routeYardageReadout } from './coursePrepPanelLogic'

type LoadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: CoursePrepResponse }
  | { status: 'error'; message: string }

const PAR_CLASS: Record<number, string> = { 3: '#4aa3d6', 4: '#3fae6b', 5: '#caa14a' }
const SOURCE_LABEL: Record<string, string> = { played: '记分卡', courseview: 'CourseView', estimate: '推算' }

type HazardMarker =
  | { kind: 'water'; start: number; end: number; cum: number; color: string }
  | { kind: 'bunker'; cum: number; color: string; label: string }

function waterCarryLabel(overlay: CoursePrepOverlay, cum: number, start: number, end: number): string {
  const readout = routeIntervalReadout(overlay, cum, start, end)
  if (readout.isCleared) return '水已过'
  if (readout.isInside) return `水中过${readout.toClear}y`
  return `水 进${readout.toStart}y / 过${readout.toClear}y`
}

function pointHazardLabel(overlay: CoursePrepOverlay, cum: number, hazardCum: number, label: string): string {
  const readout = routeIntervalReadout(overlay, cum, hazardCum, hazardCum)
  if (readout.isCleared) return `${label}已过`
  return `${label}${readout.toStart}y`
}

function atCum(route: CoursePrepOverlay['route'], cum: number): { x: number; y: number } {
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

function nearestCum(route: CoursePrepOverlay['route'], px: number, py: number): number {
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

function HoleCard({ hole, clubs }: { hole: CoursePrepHole; clubs: CoursePrepClub[] }): React.ReactElement {
  const map = hole.map
  const overlay = map?.overlay
  const ln = overlay?.ln ?? hole.route_len_m
  const initial = hole.par === 3 ? ln : hole.landing_m ?? ln * 0.55
  const [cum, setCum] = useState<number>(initial)
  const svgRef = useRef<SVGSVGElement>(null)

  const parColor = PAR_CLASS[hole.par] ?? '#3fae6b'
  const header = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
      <strong style={{ fontSize: 15 }}>{hole.hole} 洞</strong>
      <span style={{ background: parColor, color: '#fff', borderRadius: 12, padding: '1px 9px', fontSize: 12, fontWeight: 700 }}>
        Par {hole.par}
      </span>
      <span style={{ fontSize: 12, color: '#667' }}>{hole.blue_yards}y 蓝T</span>
      <span style={{ fontSize: 10, color: '#8a8f98', border: '1px dotted #aab', borderRadius: 8, padding: '0 5px' }}>
        Par 来源：{SOURCE_LABEL[hole.par_source] ?? hole.par_source}
      </span>
    </div>
  )

  const onPointer = (event: ReactPointerEvent<SVGSVGElement>): void => {
    if (!overlay || !svgRef.current) return
    if (event.buttons === 0 && event.type === 'pointermove') return
    const rect = svgRef.current.getBoundingClientRect()
    const px = ((event.clientX - rect.left) / rect.width) * overlay.w
    const py = ((event.clientY - rect.top) / rect.height) * overlay.h
    setCum(nearestCum(overlay.route, px, py))
  }

  let readout = ''
  let overlaySvg: React.ReactElement | null = null
  if (overlay) {
    const route = overlay.route
    const tee = atCum(route, 0)
    const green = atCum(route, ln)
    const ball = atCum(route, cum)
    const distances = routeYardageReadout(overlay, cum)
    readout = hole.par === 3 ? `开球 ${distances.distT}y 一杆上果岭` : `距T ${distances.distT}y · 到果岭 ${distances.toGreen}y`
    const haz: HazardMarker[] = [
      ...hole.hazards.water_carry.map((w) => ({ kind: 'water' as const, start: w[0], end: w[1], cum: w[1], color: '#2f7fb0' })),
      ...hole.hazards.bunkers.filter((b) => b[1] <= 20).slice(0, 3).map((b) => ({ kind: 'bunker' as const, cum: b[0], color: '#caa14a', label: '沙' })),
    ]
    overlaySvg = (
      <svg
        ref={svgRef}
        viewBox={`0 0 ${overlay.w} ${overlay.h}`}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', touchAction: 'none', cursor: 'grab' }}
        onPointerDown={onPointer}
        onPointerMove={onPointer}
      >
        <polyline points={route.map((p) => `${p[0]},${p[1]}`).join(' ')} fill="none" stroke="#fff" strokeOpacity={0.85} strokeWidth={3} strokeDasharray="6 5" />
        <circle cx={tee.x} cy={tee.y} r={9} fill="#4aa3d6" stroke="#fff" strokeWidth={3} />
        <circle cx={green.x} cy={green.y} r={7} fill="#fff" stroke="#333" strokeWidth={2} />
        {haz.map((h, i) => {
          const p = atCum(route, h.cum)
          return (
            <g key={i}>
              <circle cx={p.x} cy={p.y} r={5} fill={h.color} stroke="#fff" strokeWidth={2} />
              <text x={p.x + 7} y={p.y + 4} fontSize={12} fontWeight={700} fill="#fff" stroke="#000" strokeWidth={2.4} paintOrder="stroke">
                {h.kind === 'water'
                  ? waterCarryLabel(overlay, cum, h.start, h.end)
                  : pointHazardLabel(overlay, cum, h.cum, h.label)}
              </text>
            </g>
          )
        })}
        <circle cx={ball.x} cy={ball.y} r={12} fill="#e8963a" stroke="#fff" strokeWidth={3} />
      </svg>
    )
  }

  return (
    <div style={{ border: '1px solid #e3e6ea', borderRadius: 8, padding: 12, marginBottom: 12, background: '#fff' }}>
      {header}
      {map ? (
        <div style={{ position: 'relative', maxWidth: 360, margin: '0 auto' }}>
          <img src={map.image} alt={`${hole.hole} 洞`} style={{ width: '100%', display: 'block', borderRadius: 6 }} />
          {overlaySvg}
        </div>
      ) : (
        <div style={{ color: '#8a8f98', fontSize: 13 }}>（此洞暂无几何图）</div>
      )}
      {map ? <div style={{ textAlign: 'center', fontSize: 13, color: '#445', margin: '6px 0' }}>{readout} · 拖动橙点查看码数</div> : null}
      {clubs.length > 0 && hole.par !== 3 ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, justifyContent: 'center', marginBottom: 6 }}>
          {clubs.map((club) => (
            <button
              key={club.name}
              type="button"
              onClick={() => setCum(Math.min(club.m, ln))}
              style={{ fontSize: 11, padding: '2px 7px', borderRadius: 10, border: '1px solid #cdd2d8', background: '#f5f7f9', cursor: 'pointer' }}
            >
              {club.name} {club.yd}y
            </button>
          ))}
        </div>
      ) : null}
      <ol style={{ margin: '4px 0', paddingLeft: 18, fontSize: 13 }}>
        {hole.steps.map((step, i) => (
          <li key={i}>{step.club ? <><b>{step.club}</b> {step.note}</> : step.note}</li>
        ))}
      </ol>
      {hole.cautions.length > 0 ? (
        <ul style={{ margin: '4px 0', paddingLeft: 18, fontSize: 12, color: '#b4533a' }}>
          {hole.cautions.map((caution, i) => <li key={i}>{caution}</li>)}
        </ul>
      ) : null}
    </div>
  )
}

export function CoursePrepPanel({ adminToken, defaultGlobalId = 31870 }: { adminToken?: string; defaultGlobalId?: number }): React.ReactElement {
  const [globalId, setGlobalId] = useState<string>(String(defaultGlobalId))
  const [state, setState] = useState<LoadState>({ status: 'idle' })

  const load = async (): Promise<void> => {
    const id = Number(globalId)
    if (!Number.isFinite(id)) {
      setState({ status: 'error', message: '请输入有效的球场 globalId' })
      return
    }
    setState({ status: 'loading' })
    try {
      const data = await fetchCoursePrep(id, undefined, adminToken)
      setState({ status: 'ready', data })
    } catch (error) {
      setState({ status: 'error', message: error instanceof Error ? error.message : String(error) })
    }
  }

  return (
    <section style={{ marginTop: 16 }}>
      <h2 style={{ fontSize: 16 }}>赛前球场攻略</h2>
      <p style={{ fontSize: 12, color: '#667', margin: '2px 0 8px' }}>
        默认蓝T；每洞显示 Par 来源、球洞图、路线码数和水障碍/沙坑距离，并结合你的真实杆距生成打法。
      </p>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 10 }}>
        <label style={{ fontSize: 13 }}>球场 globalId</label>
        <input value={globalId} onChange={(e) => setGlobalId(e.target.value)} style={{ width: 100, padding: '3px 6px' }} />
        <button type="button" onClick={() => void load()} disabled={state.status === 'loading'}>
          {state.status === 'loading' ? '加载中…' : '加载'}
        </button>
        {state.status === 'ready' ? <span style={{ fontSize: 12, color: '#667' }}>{state.data.holeCount} 洞</span> : null}
      </div>
      {state.status === 'error' ? <div style={{ color: '#b4533a', fontSize: 13 }}>加载失败：{state.message}</div> : null}
      {state.status === 'ready'
        ? state.data.holes.map((hole) => <HoleCard key={hole.hole} hole={hole} clubs={state.data.clubs} />)
        : null}
    </section>
  )
}
