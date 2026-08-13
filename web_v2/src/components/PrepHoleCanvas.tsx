import { useRef, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'
import type { CoursePrepHole } from '../types'
import { topoImageUrl } from '../api'
import { atCum, layoutHazardLabels, nearestCum, resolveCoursePrepOverlay, routeIntervalReadout } from './coursePrepPanelLogic'
import { HoleBaseImage } from './HoleBaseImage'
import { headlineTargetYd, recosForTarget, slopeYd, toYd } from './prepWorkbenchLogic'

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
  clubs?: Array<{ name: string; m: number; yd: number }>
}

// The big center canvas of the 备战 workbench: a hole render (real per-hole
// image when the payload carries geometry, else the shared placeholder) with the
// playing line, tee/green markers, your shot scatter, hazards and a draggable
// ball drawn on top. Distance chips + a fill legend float over the frame.
export function PrepHoleCanvas({ hole, cum, onCum, globalId, clubs = [] }: PrepHoleCanvasProps): React.ReactElement {
  const svgRef = useRef<SVGSVGElement>(null)
  const map = hole.map
  const overlay = resolveCoursePrepOverlay(hole)
  const isLightweightMap = hole.geometryCoverage === 'partial' && !map?.overlay
  // Base layer: realistic topo when this hole has geometry (overlay present) and we know the gid;
  // else the legacy flat render, else the shared placeholder. Overlays draw on top either way.
  // A CourseView-only map deliberately has no fake bitmap under its factual vectors.
  const fallbackImage = map?.image ?? (overlay ? undefined : '/hole-sample.png')
  const topoSrc = hole.geometryCoverage === 'ready' && overlay && globalId != null
    ? topoImageUrl(globalId, hole.hole, hole.geometryRevision)
    : undefined
  const yourShots = hole.yourShots ?? []
  const headline = headlineTargetYd(hole, cum)
  const recommendedClub = recosForTarget(clubs, headline).find((club) => club.on) ?? null
  const slope = slopeYd(hole)
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
    const greenPoint = atCum(route, ln)
    const ball = atCum(route, clamped)
    const distT = toYd(clamped)
    const toGreen = toYd(Math.max(0, ln - clamped))

    const preciseHazards = hole.geometryCoverage === 'ready'
      ? (hole.hazards.details ?? [])
          .filter((detail) =>
            (detail.kind === 'water' || detail.kind === 'bunker') &&
            detail.frontPx.length >= 2 &&
            detail.backPx.length >= 2 &&
            [...detail.frontPx.slice(0, 2), ...detail.backPx.slice(0, 2)].every(Number.isFinite),
          )
          .sort((a, b) => a.frontRouteM - b.frontRouteM)
          .slice(0, 2)
      : []
    const haz = preciseHazards.map((detail) => ({
      start: detail.frontRouteM,
      end: detail.backRouteM,
      cum: detail.frontRouteM,
      color: detail.kind === 'water' ? '#2e94e0' : '#f2c447',
      kind: detail.kind === 'water' ? 'water' as const : 'bunker' as const,
      frontPx: detail.frontPx,
      backPx: detail.backPx,
    }))
    const markers = haz.map((h) => {
      const p = { x: (h.frontPx[0] + h.backPx[0]) / 2, y: (h.frontPx[1] + h.backPx[1]) / 2 }
      const readout = routeIntervalReadout(overlay, clamped, h.start, h.end)
      // Once the planning point moves off the tee, use its true straight carry to each measured
      // edge. Route distance remains the honest fallback for old overlays without a usable scale.
      const directYards = (edge: number[]): number | null => {
        if (!overlay.ppm || overlay.ppm <= 0 || edge.length < 2) return null
        return toYd(Math.hypot(edge[0] - ball.x, edge[1] - ball.y) / overlay.ppm)
      }
      const toStart = directYards(h.frontPx) ?? readout.toStart
      const toClear = directYards(h.backPx) ?? readout.toClear
      const kind = h.kind === 'water' ? '水' : '沙'
      const text = readout.isCleared
        ? `${kind}已过`
        : `${kind} · 到 ${toStart} / 过 ${toClear}`
      return { ...h, color: h.color, x: p.x, y: p.y, text }
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
          strokeOpacity={0.94}
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Preparation has no live player GPS. A white T marks the selected tee without pretending
            to be the blue "you are here" marker used in live play. */}
        <circle cx={tee.x} cy={tee.y} r={10} fill="#fff" stroke="#17212b" strokeWidth={2} />
        <text x={tee.x} y={tee.y + 4} textAnchor="middle" fontSize={10} fontWeight={900} fill="#17212b">T</text>
        <circle cx={greenPoint.x} cy={greenPoint.y} r={7} fill="#fff" stroke="#333" strokeWidth={2} />
        {yourShots.map((shot, i) => (
          <circle key={i} cx={shot.x} cy={shot.y} r={4.5} fill={shotDotFill(shot.shotType)} fillOpacity={0.7} stroke="#fff" strokeWidth={1.5}>
            <title>{`${shot.club ?? '未知杆'} · ${shot.roundId}`}</title>
          </circle>
        ))}
        {markers.map((m, i) => (
          <g key={i}>
            <line x1={m.frontPx[0]} y1={m.frontPx[1]} x2={m.backPx[0]} y2={m.backPx[1]} stroke={m.color} strokeWidth={4} strokeLinecap="round" />
            <circle cx={m.frontPx[0]} cy={m.frontPx[1]} r={5} fill={m.color} stroke="#111" strokeWidth={1.5} />
            <circle cx={m.backPx[0]} cy={m.backPx[1]} r={5} fill={m.color} stroke="#111" strokeWidth={1.5} />
            {hazardLabels[i].showLabel ? (
              <text x={m.x + 7} y={hazardLabels[i].labelY} fontSize={12} fontWeight={700} fill="#fff" stroke="#000" strokeWidth={2.4} paintOrder="stroke">
                {m.text}
              </text>
            ) : null}
          </g>
        ))}
        <circle cx={ball.x} cy={ball.y} r={12} fill="#4ddb78" stroke="#fff" strokeWidth={3} />
        {recommendedClub ? (
          <text x={ball.x + 15} y={ball.y - 8} fontSize={13} fontWeight={800} fill="#4ddb78" stroke="#071018" strokeWidth={3} paintOrder="stroke">
            {recommendedClub.name}
          </text>
        ) : null}
      </svg>
    )

    const chipStyle = (x: number, y: number): CSSProperties => ({ left: `${(x / overlay.w) * 100}%`, top: `${(y / overlay.h) * 100}%` })
    const greenDistances = hole.greenDistances?.available === true ? hole.greenDistances : null
    if (greenDistances && (greenDistances.frontM != null || greenDistances.middleM != null || greenDistances.backM != null)) {
      greenChip = (
        <div className="prep-map-green-range" style={chipStyle(greenPoint.x, greenPoint.y)} aria-label="果岭前中后距离">
          <small>蓝T→果岭</small>
          <span>后 <b>{greenDistances.backM == null ? '—' : toYd(greenDistances.backM)}</b></span>
          <span className="middle">中 <b>{greenDistances.middleM == null ? '—' : toYd(greenDistances.middleM)}</b></span>
          <span>前 <b>{greenDistances.frontM == null ? '—' : toYd(greenDistances.frontM)}</b></span>
        </div>
      )
    } else if (toGreen > 0) {
      greenChip = (
        <div className="prep-canvas-chip" style={chipStyle(greenPoint.x, greenPoint.y)}>
          {toGreen} <span className="prep-canvas-chip-unit">码到中</span>
        </div>
      )
    }
    ballChip = (
      <div
        className="prep-canvas-chip prep-canvas-chip--ball"
        style={chipStyle(ball.x, ball.y)}
        aria-label="地图推荐球杆"
      >
        {recommendedClub ? `${recommendedClub.name} · ` : ''}{distT}码落点
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
        <div className="prep-map-hole-facts">
          <strong>第 {hole.hole} 洞 · Par {hole.par}</strong>
          <span>{hole.blue_yards} 码</span>
          {slope !== null ? <span>坡度 {slope > 0 ? '+' : ''}{slope} 码</span> : null}
        </div>
        {overlay ? null : <div className="prep-canvas-noviz">此洞暂无实景航图(示意图)</div>}
      </div>
    </div>
  )
}
