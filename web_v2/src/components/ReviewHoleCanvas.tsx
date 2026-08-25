import type { CSSProperties, MouseEvent, PointerEvent } from 'react'
import { useRef } from 'react'
import type { RoundHoleShotMapResponse } from '../types'
import { topoImageUrl } from '../api'
import { HoleBaseImage } from './HoleBaseImage'
import { buildTrajectory, dodgeLabels, isPuttShot, shotLandingLabels } from './reviewShotMapLogic'

// The shot-map fetch state, resolved by the workbench: geometry may be missing
// for a hole (no course mesh) even when the round itself is found.
export type ReviewShotMapState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'nogeo'; message: string }
  | { status: 'ready'; data: RoundHoleShotMapResponse }

interface ReviewHoleCanvasProps {
  hole: number
  par: number | null
  score: number | null
  state: ReviewShotMapState
  editing?: boolean
  onMapClick?: (px: [number, number]) => void
  onShotMove?: (shotId: string, px: [number, number]) => void
}

function statusNote(state: ReviewShotMapState): { text: string; tone: 'muted' | 'error' } | null {
  if (state.status === 'loading') return { text: '正在载入落点图…', tone: 'muted' }
  if (state.status === 'error') return { text: state.message, tone: 'error' }
  if (state.status === 'nogeo') return { text: state.message, tone: 'muted' }
  return null
}

// The big center pane of the 复盘 workbench: the hole render with the round's
// ACTUAL shots (yellow trajectory + landing dots) drawn over the caddie-recommended
// playing line (faint white dashes = overlay.route). Distance chips float over each
// full-shot landing. Geometry may be missing for a hole → a graceful placeholder.
function eventPixel(event: PointerEvent<SVGSVGElement | SVGCircleElement> | MouseEvent<SVGSVGElement>, w: number, h: number): [number, number] {
  const rect = (event.currentTarget.ownerSVGElement ?? event.currentTarget).getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return [0, 0]
  return [
    Math.max(0, Math.min(w, ((event.clientX - rect.left) / rect.width) * w)),
    Math.max(0, Math.min(h, ((event.clientY - rect.top) / rect.height) * h)),
  ]
}

export function ReviewHoleCanvas({ hole, par, score, state, editing = false, onMapClick, onShotMove }: ReviewHoleCanvasProps): React.ReactElement {
  const activeShotId = useRef<string | null>(null)
  const suppressNextMapClick = useRef(false)
  const note = statusNote(state)
  const map = state.status === 'ready' ? state.data.map : null
  const shots = state.status === 'ready' ? state.data.shots : []
  const manualPenalty = state.status === 'ready' ? state.data.manualPenalty ?? 0 : 0
  // The overlay is authoritative for coordinate space. A fallback bitmap can be a
  // placeholder (or have stale intrinsic dimensions), so allowing the image itself
  // to size this frame stretches every route and landing marker out of alignment.
  const frameStyle: CSSProperties | undefined = map
    ? { aspectRatio: `${map.overlay.w} / ${map.overlay.h}` }
    : undefined
  // Realistic topo base for this exact (physical gid, localHole) when geometry rendered; else the
  // legacy render (map.image). Both share the overlay frame, so the shot vectors align regardless.
  const topoData = state.status === 'ready' ? state.data : null
  const topoSrc =
    map && topoData?.globalId != null && topoData?.localHole != null
      ? topoImageUrl(topoData.globalId, topoData.localHole, topoData.geometryRevision)
      : undefined

  let svg: React.ReactElement | null = null
  let chips: React.ReactElement[] = []
  if (map) {
    const { w, h, route } = map.overlay
    // Garmin Golf keeps putts as one green-side badge rather than drawing several tiny GPS
    // segments. Keep the full-shot route clean, then attach the putt count to the green.
    const fullShots = shots.filter((shot) => !isPuttShot(shot))
    const putts = shots.filter(isPuttShot)
    const geo = buildTrajectory(fullShots)
    const routePoints = route.map((p) => `${p[0]},${p[1]}`).join(' ')
    const trajPoints = geo.points.map((p) => `${p[0]},${p[1]}`).join(' ')
    // Spread pills off any near-coincident landings so two close shots stay legible.
    const labelRows = shotLandingLabels(shots, map.overlay.ppm)
    if (putts.length > 0) {
      const green = [...putts].reverse().find((shot) => shot.end)?.end ?? route[route.length - 1]?.slice(0, 2) ?? null
      if (green && green.length >= 2) labelRows.push({ x: green[0], y: green[1], text: `推杆 ×${putts.length}` })
    }
    const labels = dodgeLabels(labelRows, { w, h })

    svg = (
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className={editing ? 'review-canvas-svg review-canvas-svg--editing' : 'review-canvas-svg'}
        preserveAspectRatio="xMidYMid meet"
        aria-hidden={!editing}
        onPointerDown={(event) => {
          if (!editing || !(event.target instanceof Element)) return
          const marker = event.target.closest('circle[data-shot-id]')
          const shotId = marker?.getAttribute('data-shot-id')
          if (!shotId) return
          event.stopPropagation()
          activeShotId.current = shotId
          event.currentTarget.setPointerCapture?.(event.pointerId)
        }}
        onPointerMove={(event) => {
          const shotId = activeShotId.current
          if (!editing || !shotId) return
          event.stopPropagation()
          onShotMove?.(shotId, eventPixel(event, w, h))
        }}
        onPointerUp={(event) => {
          if (!activeShotId.current) return
          event.stopPropagation()
          activeShotId.current = null
          suppressNextMapClick.current = true
          event.currentTarget.releasePointerCapture?.(event.pointerId)
        }}
        onPointerCancel={(event) => {
          if (!activeShotId.current) return
          event.stopPropagation()
          activeShotId.current = null
          event.currentTarget.releasePointerCapture?.(event.pointerId)
        }}
        onClick={(event) => {
          if (suppressNextMapClick.current) {
            suppressNextMapClick.current = false
            return
          }
          if (editing && event.target === event.currentTarget) onMapClick?.(eventPixel(event, w, h))
        }}
      >
        {/* Caddie-recommended line — the ideal playing route, faint + dashed. */}
        {route.length > 1 ? (
          <polyline points={routePoints} fill="none" stroke="#fff" strokeOpacity={0.55} strokeWidth={2.4} strokeDasharray="6 5" strokeLinejoin="round" />
        ) : null}
        {/* Actual shots — per-segment so a synthetic (推算) drive can render faded. */}
        {fullShots.map((shot, index) =>
          shot.start && shot.end ? (
            <line
              key={`seg-${index}`}
              x1={shot.start[0]}
              y1={shot.start[1]}
              x2={shot.end[0]}
              y2={shot.end[1]}
              stroke="#ffd447"
              strokeWidth={shot.synthetic ? 3 : 4.5}
              strokeLinecap="round"
              strokeDasharray={shot.synthetic ? '5 6' : undefined}
              strokeOpacity={shot.synthetic ? 0.5 : 1}
            />
          ) : null,
        )}
        {trajPoints ? <polyline points={trajPoints} fill="none" stroke="none" /> : null}
        {geo.tee ? <circle cx={geo.tee[0]} cy={geo.tee[1]} r={6} fill="#fff" stroke="#333" strokeWidth={2} /> : null}
        {shots.map((shot, index) => {
          if (!shot.end) return null
          const shotId = shot.id ?? null
          return (
            <circle
              key={`dot-${shotId ?? index}`}
              data-shot-id={shotId ?? undefined}
              cx={shot.end[0]}
              cy={shot.end[1]}
              r={editing ? 9 : 7}
              fill="#ffd447"
              stroke={editing ? '#fff2a6' : '#7a5b00'}
              strokeWidth={editing ? 2.4 : 1.6}
              className={editing ? 'review-shot-marker review-shot-marker--editable' : 'review-shot-marker'}
              role={editing && shotId ? 'button' : undefined}
              tabIndex={editing && shotId ? 0 : undefined}
              aria-label={editing && shotId ? `第${shot.order ?? index + 1}杆落点` : undefined}
              onPointerDown={(event) => {
                if (!editing || !shotId) return
                activeShotId.current = shotId
                event.currentTarget.ownerSVGElement?.setPointerCapture?.(event.pointerId)
              }}
              onPointerMove={(event) => {
                if (!editing || !shotId || activeShotId.current !== shotId) return
                event.stopPropagation()
                onShotMove?.(shotId, eventPixel(event, w, h))
              }}
              onPointerUp={(event) => {
                event.stopPropagation()
                if (activeShotId.current === shotId) {
                  activeShotId.current = null
                  suppressNextMapClick.current = true
                }
              }}
              onPointerCancel={(event) => {
                event.stopPropagation()
                if (activeShotId.current === shotId) {
                  activeShotId.current = null
                }
              }}
              onClick={(event) => event.stopPropagation()}
            />
          )
        })}
        {geo.hole ? <circle cx={geo.hole[0]} cy={geo.hole[1]} r={6} fill="#e43a3a" stroke="#fff" strokeWidth={1.8} /> : null}
      </svg>
    )

    chips = labels.map((label, index) => {
      const style: CSSProperties = { left: `${(label.x / w) * 100}%`, top: `${(label.y / h) * 100}%` }
      return (
        <div key={`chip-${index}`} className="review-canvas-chip" style={style}>
          {label.text}
        </div>
      )
    })
  }

  return (
    <div className="review-canvas" aria-label={`第${hole}洞落点图`}>
      <div className="review-canvas-frame" style={frameStyle}>
        {map ? (
          <HoleBaseImage className="review-canvas-img" topoSrc={topoSrc} fallbackSrc={map.image} alt={`第${hole}洞`} />
        ) : (
          <div className="review-canvas-placeholder" />
        )}
        {svg}
        {chips}
        <div className="review-map-hole-facts">
          <strong>第 {hole} 洞 · Par {par ?? '—'}</strong>
          {score !== null ? <span>本洞 {score} 杆</span> : null}
        </div>
        {manualPenalty > 0 ? <div className="review-map-penalty">罚杆 +{manualPenalty}</div> : null}
        {note ? <div className={note.tone === 'error' ? 'review-canvas-note error' : 'review-canvas-note'}>{note.text}</div> : null}
      </div>
    </div>
  )
}
