import { useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import type { CoursePrepClub, CoursePrepHole, CoursePrepOverlay } from '../types'
import { atCum, layoutHazardLabels, nearestCum, routeIntervalReadout, routeYardageReadout } from './coursePrepPanelLogic'
import { useDiagnostics } from '../diagnosticsContext'

const PAR_CLASS: Record<number, string> = { 3: '#4aa3d6', 4: '#3fae6b', 5: '#caa14a' }
const SOURCE_LABEL: Record<string, string> = { played: '记分卡', courseview: 'CourseView', estimate: '推算' }
const YARD = 1.09361
// Minimum vertical gap (overlay px) between two stacked hazard distance labels;
// ~font size (12) + the outline stroke, so de-overlapped labels never touch.
const HAZARD_LABEL_MIN_GAP = 14

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

function routeOptionLabel(route: { id: string; carryM?: number }): string {
  return route.carryM ? `${route.id} ${Math.round(route.carryM * YARD)}码` : route.id
}

const MISSING_LABEL_ZH: Record<string, string> = { geometry: '几何' }

function missingLabel(row: { label?: string }): string {
  const label = row.label ?? '数据'
  return `${MISSING_LABEL_ZH[label] ?? label}缺失`
}

// TEE green, APPROACH deep blue (--eagle): both must stay distinguishable on
// water/fairway fills, hence also the white dot outline below.
function shotDotFill(shotType: string): string {
  return shotType === 'TEE' ? 'var(--green)' : 'var(--eagle)'
}

export interface PrepHoleCardProps {
  hole: CoursePrepHole
  clubs: CoursePrepClub[]
}

export function PrepHoleCard({ hole, clubs }: PrepHoleCardProps): React.ReactElement {
  const diagnostics = useDiagnostics()
  const map = hole.map
  const overlay = map?.overlay
  const ln = overlay?.ln ?? hole.route_len_m
  const initial = hole.par === 3 ? ln : hole.landing_m ?? ln * 0.55
  const [cum, setCum] = useState<number>(initial)
  const svgRef = useRef<SVGSVGElement>(null)
  const candidateRoutes = hole.candidateRoutes ?? []
  const missingData = hole.missingData ?? []
  const sourceRefs = hole.sourceRefs ?? []
  const yourShots = hole.yourShots ?? []
  // round-13: slope (playsLike) — show only when geometry produced a non-zero delta.
  // deltaYd>0 = uphill (plays longer). Mirrors the phone/watch caddie glance (B7).
  const playsLike = hole.playsLike
  const slopeYd =
    playsLike?.available && typeof playsLike.deltaYd === 'number' && playsLike.deltaYd !== 0 ? playsLike.deltaYd : null

  const parColor = PAR_CLASS[hole.par] ?? '#3fae6b'
  const header = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
      <strong style={{ fontSize: 15 }}>{hole.hole} 洞</strong>
      <span style={{ background: parColor, color: '#fff', borderRadius: 12, padding: '1px 9px', fontSize: 12, fontWeight: 700 }}>
        Par {hole.par}
      </span>
      <span style={{ fontSize: 12, color: '#667' }}>{hole.blue_yards}码 蓝T</span>
      {diagnostics ? (
        <span style={{ fontSize: 10, color: '#8a8f98', border: '1px dotted #aab', borderRadius: 8, padding: '0 5px' }}>
          Par 来源：{SOURCE_LABEL[hole.par_source] ?? hole.par_source}
        </span>
      ) : null}
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
    readout = hole.par === 3 ? `开球 ${distances.distT}码 一杆上果岭` : `距T ${distances.distT}码 · 到果岭 ${distances.toGreen}码`
    const haz: HazardMarker[] = [
      ...hole.hazards.water_carry.map((w) => ({ kind: 'water' as const, start: w[0], end: w[1], cum: w[1], color: '#2f7fb0' })),
      ...hole.hazards.bunkers.filter((b) => b[1] <= 20).slice(0, 3).map((b) => ({ kind: 'bunker' as const, cum: b[0], color: '#caa14a', label: '沙' })),
    ]
    // Project each hazard onto the route, resolve its distance label, then run a
    // greedy de-overlap so two nearby hazards don't print their labels on top of
    // each other. Markers stay on the route; only the text is nudged/deduped.
    const hazardMarkers = haz.map((h) => {
      const p = atCum(route, h.cum)
      const text =
        h.kind === 'water'
          ? waterCarryLabel(overlay, cum, h.start, h.end)
          : pointHazardLabel(overlay, cum, h.cum, h.label)
      return { color: h.color, x: p.x, y: p.y, text }
    })
    const hazardLabels = layoutHazardLabels(
      hazardMarkers.map((m) => ({ y: m.y + 4, text: m.text })),
      HAZARD_LABEL_MIN_GAP,
    )
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
        {yourShots.map((shot, i) => (
          <circle key={i} cx={shot.x} cy={shot.y} r={4.5} fill={shotDotFill(shot.shotType)} fillOpacity={0.7} stroke="#fff" strokeWidth={1.5}>
            <title>{`${shot.club ?? '未知杆'} · ${shot.roundId}`}</title>
          </circle>
        ))}
        {hazardMarkers.map((m, i) => (
          <g key={i}>
            <circle cx={m.x} cy={m.y} r={5} fill={m.color} stroke="#fff" strokeWidth={2} />
            {hazardLabels[i].showLabel ? (
              <text
                x={m.x + 7}
                y={hazardLabels[i].labelY}
                fontSize={12}
                fontWeight={700}
                fill="#fff"
                stroke="#000"
                strokeWidth={2.4}
                paintOrder="stroke"
              >
                {m.text}
              </text>
            ) : null}
          </g>
        ))}
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
      {slopeYd != null ? (
        <div aria-label={`第${hole.hole}洞坡度`} style={{ textAlign: 'center', fontSize: 12, color: '#445', margin: '0 0 6px' }}>
          坡度 {slopeYd > 0 ? '+' : ''}{slopeYd}码 · {slopeYd > 0 ? '上坡' : '下坡'}
        </div>
      ) : null}
      {overlay && yourShots.length > 0 ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, fontSize: 12, color: '#445', margin: '2px 0 6px' }}>
          <span>你的落点:</span>
          <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 8, background: 'var(--green)', display: 'inline-block', border: '1px solid #445' }} />
          <span>开球(落点)</span>
          <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 8, background: 'var(--eagle)', display: 'inline-block', border: '1px solid #445' }} />
          <span>攻果岭</span>
        </div>
      ) : null}
      {candidateRoutes.length > 0 ? (
        <div aria-label={`第${hole.hole}洞路线选项`} style={{ display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'center', margin: '6px 0' }}>
          {candidateRoutes.map((route) => (
            <span key={route.id} style={{ fontSize: 11, border: '1px solid #d6dbe1', borderRadius: 8, padding: '2px 7px', color: '#344054', background: '#f8fafc' }}>
              {routeOptionLabel(route)}
            </span>
          ))}
        </div>
      ) : null}
      {diagnostics && missingData.length > 0 ? (
        <div aria-label={`第${hole.hole}洞缺失数据`} style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '6px 0' }}>
          {missingData.map((row, index) => (
            <span key={`${row.label ?? 'missing'}-${index}`} style={{ fontSize: 11, color: '#9f4a35', border: '1px solid #efd0c8', borderRadius: 8, padding: '2px 7px', background: '#fff7f4' }}>
              {missingLabel(row)}
            </span>
          ))}
        </div>
      ) : null}
      {diagnostics && sourceRefs.length > 0 ? (
        <div aria-label={`第${hole.hole}洞数据来源`} style={{ display: 'flex', flexWrap: 'wrap', gap: 4, margin: '6px 0' }}>
          {sourceRefs.map((ref) => (
            <span key={ref} style={{ fontSize: 10, color: '#667', border: '1px solid #e3e6ea', borderRadius: 8, padding: '1px 6px' }}>
              {ref}
            </span>
          ))}
        </div>
      ) : null}
      {map && clubs.length > 0 && hole.par !== 3 ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, justifyContent: 'center', marginBottom: 6 }}>
          {clubs.map((club) => (
            <button
              key={club.name}
              type="button"
              onClick={() => setCum(Math.min(club.m, ln))}
              style={{ fontSize: 11, padding: '2px 7px', borderRadius: 10, border: '1px solid #cdd2d8', background: '#f5f7f9', cursor: 'pointer' }}
            >
              {club.name} {club.yd}码
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
