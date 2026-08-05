import { useRef, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'
import type { CoursePrepHole } from '../types'
import { topoImageUrl } from '../api'
import { atCum, layoutHazardLabels, nearestCum, resolveCoursePrepOverlay, routeIntervalReadout } from './coursePrepPanelLogic'
import { HoleBaseImage } from './HoleBaseImage'
import { toYd } from './prepWorkbenchLogic'

// Minimum vertical gap (overlay px) between two stacked hazard distance labels.
const HAZARD_LABEL_MIN_GAP = 14

// TEE green, APPROACH deep blue — both must stay distinct on water/fairway fills.
function shotDotFill(shotType: string): string {
  return shotType === 'TEE' ? 'var(--green)' : 'var(--eagle)'
}

export interface PrepHoleCanvasProps {
  hole: CoursePrepHole
  cum: number
  onCum: (cum: number) => void
  // The course's globalId (prep is single-gid; localHole == hole.hole). When set AND the hole has
  // geometry (overlay present), the base image is the realistic server topo; otherwise it falls
  // back to the legacy render / placeholder.
  globalId?: number
}

// The big center canvas of the 备战 workbench: a hole render (real per-hole
// image when the payload carries geometry, else the shared placeholder) with the
// playing line, tee/green markers, your shot scatter, hazards and a draggable
// ball drawn on top. Distance chips + a fill legend float over the frame.
export function PrepHoleCanvas({ hole, cum, onCum, globalId }: PrepHoleCanvasProps): React.ReactElement {
  const svgRef = useRef<SVGSVGElement>(null)
  const map = hole.map
  const overlay = resolveCoursePrepOverlay(hole)
  const isLightweightMap = hole.geometryCoverage === 'partial' && !map?.overlay
  // Base layer: realistic topo when this hole has geometry (overlay present) and we know the gid;
  // else the legacy flat render, else the shared placeholder. Overlays draw on top either way.
  // A CourseView-only map deliberately has no fake bitmap under its factual vectors.
  const fallbackImage = map?.image ?? (overlay ? undefined : '/hole-sample.png')
  const topoSrc = hole.geometryCoverage === 'ready' && overlay && globalId != null
    ? topoImageUrl(globalId, hole.hole)
    : undefined
  const yourShots = hole.yourShots ?? []
  // All distance markers use overlay coordinates, so the overlay dimensions—not
  // a placeholder bitmap's intrinsic ratio—must own the visible frame.
  const frameStyle: CSSProperties | undefined = overlay
    ? { aspectRatio: `${overlay.w} / ${overlay.h}` }
    : undefined

  const onPointer = (event: ReactPointerEvent<SVGSVGElement>): void => {
    if (!overlay || !svgRef.current) return
    if (event.buttons === 0 && event.type === 'pointermove') return
    const rect = svgRef.current.getBoundingClientRect()
    const px = ((event.clientX - rect.left) / rect.width) * overlay.w
    const py = ((event.clientY - rect.top) / rect.height) * overlay.h
    onCum(nearestCum(overlay.route, px, py))
  }

  let svg: React.ReactElement | null = null
  let greenChip: React.ReactElement | null = null
  let ballChip: React.ReactElement | null = null
  if (overlay) {
    const route = overlay.route
    const ln = overlay.ln
    const clamped = Math.max(0, Math.min(ln, cum))
    const tee = atCum(route, 0)
    const green = atCum(route, ln)
    const ball = atCum(route, clamped)
    const distT = toYd(clamped)
    const toGreen = toYd(Math.max(0, ln - clamped))

    const haz: Array<{ start: number; end: number; cum: number; color: string; kind: 'water' | 'bunker' }> = [
      ...hole.hazards.water_carry.map((w) => ({ start: w[0], end: w[1], cum: w[1], color: '#2f7fb0', kind: 'water' as const })),
      ...hole.hazards.bunkers
        .filter((b) => b[1] <= 20)
        .slice(0, 3)
        .map((b) => ({ start: b[0], end: b[0], cum: b[0], color: '#caa14a', kind: 'bunker' as const })),
    ]
    const markers = haz.map((h) => {
      const p = atCum(route, h.cum)
      const readout = routeIntervalReadout(overlay, clamped, h.start, h.end)
      const text =
        h.kind === 'water'
          ? readout.isCleared
            ? '水已过'
            : readout.isInside
              ? `水中过${readout.toClear}y`
              : `过水${readout.toClear}y`
          : readout.isCleared
            ? '沙已过'
            : `沙${readout.toStart}y`
      return { color: h.color, x: p.x, y: p.y, text }
    })
    const hazardLabels = layoutHazardLabels(
      markers.map((m) => ({ y: m.y + 4, text: m.text })),
      HAZARD_LABEL_MIN_GAP,
    )
    const lightweightHazards = isLightweightMap
      ? (hole.hazards.details ?? []).filter(
          (detail) =>
            (detail.kind === 'water' || detail.kind === 'bunker') &&
            detail.frontPx.length >= 2 &&
            detail.backPx.length >= 2 &&
            [...detail.frontPx.slice(0, 2), ...detail.backPx.slice(0, 2)].every(Number.isFinite),
        )
      : []
    const greenOutline = isLightweightMap && hole.greenOutline?.available
      ? hole.greenOutline.pointsPx.filter(
          (point) => point.length >= 2 && Number.isFinite(point[0]) && Number.isFinite(point[1]),
        )
      : []

    svg = (
      <svg
        ref={svgRef}
        viewBox={`0 0 ${overlay.w} ${overlay.h}`}
        className="prep-canvas-svg"
        onPointerDown={onPointer}
        onPointerMove={onPointer}
      >
        {isLightweightMap ? (
          <polyline
            data-map-fact="course-data-route"
            points={route.map((p) => `${p[0]},${p[1]}`).join(' ')}
            fill="none"
            stroke="#397d49"
            strokeOpacity={0.9}
            strokeWidth={26}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ) : null}
        {lightweightHazards.map((detail, index) => (
          <line
            key={`fact-${detail.kind}-${index}`}
            data-map-fact={`course-data-${detail.kind}`}
            x1={detail.frontPx[0]}
            y1={detail.frontPx[1]}
            x2={detail.backPx[0]}
            y2={detail.backPx[1]}
            stroke={detail.kind === 'water' ? '#2e94e0' : '#e0c27a'}
            strokeOpacity={0.95}
            strokeWidth={detail.kind === 'water' ? 14 : 12}
            strokeLinecap="round"
          />
        ))}
        {greenOutline.length >= 3 ? (
          <polygon
            data-map-fact="course-data-green"
            points={greenOutline.map((point) => `${point[0]},${point[1]}`).join(' ')}
            fill="#5cb759"
            fillOpacity={0.95}
            stroke="#fff"
            strokeOpacity={0.35}
            strokeWidth={1}
          />
        ) : null}
        <polyline
          points={route.map((p) => `${p[0]},${p[1]}`).join(' ')}
          fill="none"
          stroke="#fff"
          strokeOpacity={0.85}
          strokeWidth={3}
          strokeDasharray="6 5"
        />
        <circle cx={tee.x} cy={tee.y} r={9} fill="#4aa3d6" stroke="#fff" strokeWidth={3} />
        <circle cx={green.x} cy={green.y} r={7} fill="#fff" stroke="#333" strokeWidth={2} />
        {yourShots.map((shot, i) => (
          <circle key={i} cx={shot.x} cy={shot.y} r={4.5} fill={shotDotFill(shot.shotType)} fillOpacity={0.7} stroke="#fff" strokeWidth={1.5}>
            <title>{`${shot.club ?? '未知杆'} · ${shot.roundId}`}</title>
          </circle>
        ))}
        {markers.map((m, i) => (
          <g key={i}>
            <circle cx={m.x} cy={m.y} r={5} fill={m.color} stroke="#fff" strokeWidth={2} />
            {hazardLabels[i].showLabel ? (
              <text x={m.x + 7} y={hazardLabels[i].labelY} fontSize={12} fontWeight={700} fill="#fff" stroke="#000" strokeWidth={2.4} paintOrder="stroke">
                {m.text}
              </text>
            ) : null}
          </g>
        ))}
        <circle cx={ball.x} cy={ball.y} r={12} fill="#e8963a" stroke="#fff" strokeWidth={3} />
      </svg>
    )

    const chipStyle = (x: number, y: number): CSSProperties => ({ left: `${(x / overlay.w) * 100}%`, top: `${(y / overlay.h) * 100}%` })
    if (toGreen > 0) {
      greenChip = (
        <div className="prep-canvas-chip" style={chipStyle(green.x, green.y)}>
          {toGreen} <span className="prep-canvas-chip-unit">码到中</span>
        </div>
      )
    }
    ballChip = (
      <div className="prep-canvas-chip prep-canvas-chip--ball" style={chipStyle(ball.x, ball.y)}>
        {distT}
      </div>
    )
  }

  return (
    <div className="prep-canvas" aria-label={`第${hole.hole}洞球道图`}>
      <div className="prep-canvas-frame" style={frameStyle}>
        <HoleBaseImage className="prep-canvas-img" topoSrc={topoSrc} fallbackSrc={fallbackImage} alt={`第${hole.hole}洞`} />
        {svg}
        {greenChip}
        {ballChip}
        {overlay ? null : <div className="prep-canvas-noviz">此洞暂无实景航图(示意图)</div>}
        <div className="prep-canvas-legend">
          <span>
            <b style={{ background: '#7fbf5a' }} />
            果岭
          </span>
          <span>
            <b style={{ background: '#8cda55' }} />
            球道
          </span>
          <span>
            <b style={{ background: '#e8d9a8' }} />沙
          </span>
          <span>
            <b style={{ background: '#3e9bff' }} />水
          </span>
        </div>
      </div>
      {yourShots.length > 0 ? (
        <div className="prep-canvas-shots">
          <span>你的落点:</span>
          <span aria-hidden="true" className="prep-canvas-shots-dot tee" />
          <span>开球(落点)</span>
          <span aria-hidden="true" className="prep-canvas-shots-dot appr" />
          <span>攻果岭</span>
        </div>
      ) : null}
      {overlay ? <p className="prep-canvas-hint">拖动橙点试算任意落点</p> : null}
    </div>
  )
}
