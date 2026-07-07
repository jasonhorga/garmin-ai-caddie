import type { CSSProperties } from 'react'
import type { RoundHoleShotMapResponse } from '../types'
import { topoImageUrl } from '../api'
import { HoleBaseImage } from './HoleBaseImage'
import { buildTrajectory, dodgeLabels, shotLandingLabels } from './reviewShotMapLogic'

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
export function ReviewHoleCanvas({ hole, par, score, state }: ReviewHoleCanvasProps): React.ReactElement {
  const note = statusNote(state)
  const map = state.status === 'ready' ? state.data.map : null
  const shots = state.status === 'ready' ? state.data.shots : []
  // Realistic topo base for this exact (physical gid, localHole) when geometry rendered; else the
  // legacy render (map.image). Both share the overlay frame, so the shot vectors align regardless.
  const topoData = state.status === 'ready' ? state.data : null
  const topoSrc =
    map && topoData?.globalId != null && topoData?.localHole != null
      ? topoImageUrl(topoData.globalId, topoData.localHole)
      : undefined

  let svg: React.ReactElement | null = null
  let chips: React.ReactElement[] = []
  if (map) {
    const { w, h, route } = map.overlay
    const geo = buildTrajectory(shots)
    const routePoints = route.map((p) => `${p[0]},${p[1]}`).join(' ')
    const trajPoints = geo.points.map((p) => `${p[0]},${p[1]}`).join(' ')
    // Spread pills off any near-coincident landings so two close shots stay legible.
    const labels = dodgeLabels(shotLandingLabels(shots), { w, h })

    svg = (
      <svg viewBox={`0 0 ${w} ${h}`} className="review-canvas-svg" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
        {/* Caddie-recommended line — the ideal playing route, faint + dashed. */}
        {route.length > 1 ? (
          <polyline points={routePoints} fill="none" stroke="#fff" strokeOpacity={0.55} strokeWidth={2.4} strokeDasharray="6 5" strokeLinejoin="round" />
        ) : null}
        {/* Actual shots — per-segment so a synthetic (推算) drive can render faded. */}
        {shots.map((shot, index) =>
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
        {geo.landings.map((p, index) => (
          <circle key={`dot-${index}`} cx={p[0]} cy={p[1]} r={7} fill="#ffd447" stroke="#7a5b00" strokeWidth={1.6} />
        ))}
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
      <div className="review-canvas-frame">
        {map ? (
          <HoleBaseImage className="review-canvas-img" topoSrc={topoSrc} fallbackSrc={map.image} alt={`第${hole}洞`} />
        ) : (
          <div className="review-canvas-placeholder" />
        )}
        {svg}
        {chips}
        {note ? <div className={note.tone === 'error' ? 'review-canvas-note error' : 'review-canvas-note'}>{note.text}</div> : null}
      </div>
      <div className="review-canvas-meta">
        <span className="review-canvas-hole">
          第 {hole} 洞 · Par {par ?? '—'}
          {score !== null ? ` → ${score}` : ''}
        </span>
        {map ? (
          <div className="review-canvas-legend">
            <span>
              <b className="review-legend-actual" />
              实际打法
            </span>
            <span>
              <b className="review-legend-plan" />
              球童建议线
            </span>
          </div>
        ) : null}
      </div>
    </div>
  )
}
