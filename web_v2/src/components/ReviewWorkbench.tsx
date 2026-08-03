import { useEffect, useRef, useState } from 'react'
import type { RoundCard, RoundHoleShotMapResponse, ScoreStripCell } from '../types'
import { prefetchTopoImage, topoImageUrl } from '../api'
import { cleanCourseName, shortRoundDate } from '../units'
import { ReviewHoleCanvas, type ReviewShotMapState } from './ReviewHoleCanvas'
import { ReviewInspector } from './ReviewInspector'
import { buildTimeline, chipShape, chipShapeZh, type ChipShape } from './reviewShotMapLogic'

interface ReviewWorkbenchProps {
  rounds: RoundCard[]
  fetchShotMap: (roundRef: string, hole: number) => Promise<RoundHoleShotMapResponse>
}

function formatToPar(value: number | null): string {
  if (value === null) return ''
  if (value === 0) return 'E'
  return value > 0 ? `+${value}` : String(value)
}

function toParTone(value: number | null): string {
  if (value === null || value === 0) return 'score-even'
  return value < 0 ? 'score-under' : 'score-over'
}

// The shape-coded score chip (design system §一): the SVG frame encodes the
// outcome family (circle=under, square=over, triangle=triple+) and the number is
// the strokes. Colour comes from CSS per shape.
function ShapeFrame({ shape }: { shape: ChipShape }): React.ReactElement | null {
  switch (shape) {
    case 'birdie':
      return (
        <svg className="review-chip-frame" viewBox="0 0 30 30" aria-hidden="true">
          <circle cx="15" cy="15" r="12" />
        </svg>
      )
    case 'eagle':
      return (
        <svg className="review-chip-frame" viewBox="0 0 30 30" aria-hidden="true">
          <circle cx="15" cy="15" r="13" />
          <circle cx="15" cy="15" r="9.5" />
        </svg>
      )
    case 'bogey':
      return (
        <svg className="review-chip-frame" viewBox="0 0 30 30" aria-hidden="true">
          <rect x="3.5" y="3.5" width="23" height="23" />
        </svg>
      )
    case 'double':
      return (
        <svg className="review-chip-frame" viewBox="0 0 30 30" aria-hidden="true">
          <rect x="2" y="2" width="26" height="26" />
          <rect x="6" y="6" width="18" height="18" />
        </svg>
      )
    case 'triple':
      return (
        <svg className="review-chip-frame" viewBox="0 0 30 30" aria-hidden="true">
          <polygon points="15,2 28,27 2,27" />
        </svg>
      )
    default:
      return null
  }
}

function ScoreShapeChip({ cell }: { cell: ScoreStripCell }): React.ReactElement {
  const shape = chipShape(cell.toPar)
  const label = cell.score ?? '—'
  return (
    <span className={`review-chip review-chip--${shape}`} aria-label={`${chipShapeZh(shape)} ${label}`}>
      <ShapeFrame shape={shape} />
      <span className="review-chip-num">{label}</span>
    </span>
  )
}

function deriveShotMapState(
  done: { key: string; result: { data: RoundHoleShotMapResponse } | { error: string } } | null,
  key: string | null,
): ReviewShotMapState {
  const current = done !== null && done.key === key ? done.result : null
  if (current === null) return { status: 'loading' }
  if ('error' in current) return { status: 'error', message: current.error }
  const data = current.data
  if (data.found && data.map) return { status: 'ready', data }
  const missing = Array.isArray(data.missingData) ? data.missingData : []
  const reason = missing.find((row) => typeof row?.reason === 'string')?.reason
  return { status: 'nogeo', message: typeof reason === 'string' ? reason : '这一洞暂无球场几何,画不了落点图。' }
}

type ShotMapDone = { key: string; result: { data: RoundHoleShotMapResponse } | { error: string } }

// The 复盘 round-review workbench: a round selector across the top, the round's
// holes (shape-coded score chips) down the left, the per-hole落点图 in the middle,
// and the 杆序 timeline on the right. Selection lives here so the three panes stay
// in sync; the shot map is fetched lazily per hole and re-fetched on switch.
export function ReviewWorkbench({ rounds, fetchShotMap }: ReviewWorkbenchProps): React.ReactElement {
  const [selectedRoundId, setSelectedRoundId] = useState<string | null>(() => rounds[0]?.id ?? null)
  const [selectedHole, setSelectedHole] = useState<number | null>(null)
  const [shotMapDone, setShotMapDone] = useState<ShotMapDone | null>(null)
  // Keep the fetcher in a ref so the shot-map effect keys only off round+hole and
  // never refetches just because the parent handed a fresh closure identity.
  const fetchRef = useRef(fetchShotMap)
  const shotMapSeq = useRef(0)
  useEffect(() => {
    fetchRef.current = fetchShotMap
  })

  // Adjust-state-during-render (PrepWorkbench idiom): a rounds change that drops the
  // current pick snaps to the newest round; a round change reseeds the hole to the
  // first scored hole. Cascades until stable, all before commit.
  const validRoundId = selectedRoundId !== null && rounds.some((round) => round.id === selectedRoundId) ? selectedRoundId : rounds[0]?.id ?? null
  if (validRoundId !== selectedRoundId) setSelectedRoundId(validRoundId)

  const selectedRound = rounds.find((round) => round.id === validRoundId) ?? null
  const holes: ScoreStripCell[] = Array.isArray(selectedRound?.scoreStrip) ? selectedRound.scoreStrip : []
  const validHole = selectedHole !== null && holes.some((cell) => cell.hole === selectedHole) ? selectedHole : holes[0]?.hole ?? null
  if (validHole !== selectedHole) setSelectedHole(validHole)

  useEffect(() => {
    if (validRoundId === null || validHole === null) return
    const key = `${validRoundId}:${validHole}`
    const seq = ++shotMapSeq.current
    fetchRef
      .current(validRoundId, validHole)
      .then((data) => {
        if (shotMapSeq.current !== seq) return
        setShotMapDone({ key, result: { data } })
        // Prefetch the adjacent holes' topo bitmap so stepping the strip is instant. A single-course
        // round has localHole tracking the hole number, so localHole±1 warms the neighbours' realistic
        // base image; a wrong guess (multi-course round) just warms a nearby cached hole, never errors.
        if (data.found && data.map && data.globalId != null && data.localHole != null) {
          for (const local of [data.localHole - 1, data.localHole + 1]) {
            if (local >= 1) prefetchTopoImage(topoImageUrl(data.globalId, local))
          }
        }
      })
      .catch((error: unknown) => {
        if (shotMapSeq.current !== seq) return
        setShotMapDone({ key, result: { error: error instanceof Error ? error.message : '落点图加载失败' } })
      })
  }, [validRoundId, validHole])

  if (rounds.length === 0 || selectedRound === null) {
    return (
      <section className="review-page" aria-label="复盘">
        <section className="panel review-empty" aria-label="暂无可复盘的球局">
          <h2>还没有可复盘的球局</h2>
          <p>同步 Garmin 数据后，这里会按洞展示你每一杆的落点和杆序。</p>
        </section>
      </section>
    )
  }

  const shotMapKey = validHole === null ? null : `${validRoundId}:${validHole}`
  // A round with no per-hole scorecard (e.g. a bare manual entry) has no hole to
  // draw — say so instead of spinning forever on a shot map that never loads.
  const shotMapState: ReviewShotMapState =
    validHole === null ? { status: 'nogeo', message: '这局暂无逐洞成绩，无法展示落点图。' } : deriveShotMapState(shotMapDone, shotMapKey)
  const activeCell = holes.find((cell) => cell.hole === validHole) ?? null
  const ppm = shotMapState.status === 'ready' ? shotMapState.data.map?.overlay.ppm ?? null : null
  const timeline = shotMapState.status === 'ready' ? buildTimeline(shotMapState.data.shots, ppm) : []
  const manualPenalty = shotMapState.status === 'ready' ? shotMapState.data.manualPenalty ?? 0 : 0
  const roundScore = selectedRound.score ?? null
  const roundToPar = selectedRound.toPar ?? null
  const workClass = timeline.length <= 1 && manualPenalty === 0
    ? 'review-work review-work--quiet-inspector'
    : 'review-work'

  return (
    <section className="review-page review-workbench-page" aria-label="复盘">
      <div className="review-topbar">
        <div className="review-crumb">
          <h2 className="review-crumb-name">逐洞复盘</h2>
          <span className="review-crumb-date">真实落点与杆序</span>
        </div>
        <label className="review-round-picker">
          <span className="review-round-picker-label">球局</span>
          <select
            aria-label="选择球局"
            value={validRoundId ?? ''}
            onChange={(event) => {
              setSelectedRoundId(event.target.value)
              setSelectedHole(null)
            }}
          >
            {rounds.map((round) => (
              <option key={round.id} value={round.id}>
                {cleanCourseName(round.courseName)} · {shortRoundDate(round.date)}
                {round.score !== null ? `（${round.score}）` : ''}
              </option>
            ))}
          </select>
        </label>
        <div className="review-total">
          总杆 <b>{roundScore ?? '—'}</b>
          {roundToPar !== null ? (
            <span className={`review-total-topar ${toParTone(roundToPar)}`}> · {formatToPar(roundToPar)}</span>
          ) : null}
        </div>
      </div>

      <div className={workClass}>
        <div className="review-holes">
          <div className="review-holes-head">
            <span>球洞 · 成绩</span>
            {roundScore !== null ? (
              <span className="review-holes-total">
                {roundScore}
                {roundToPar !== null ? ` (${formatToPar(roundToPar)})` : ''}
              </span>
            ) : null}
          </div>
          <ul className="review-holes-list">
            {holes.map((cell) => (
              <li key={cell.hole}>
                <button
                  type="button"
                  className={cell.hole === validHole ? 'review-hole on' : 'review-hole'}
                  aria-current={cell.hole === validHole ? 'true' : undefined}
                  aria-label={`第${cell.hole}洞 标准杆${cell.par ?? '-'} 成绩${cell.score ?? '-'}`}
                  onClick={() => setSelectedHole(cell.hole)}
                >
                  <span className="review-hole-n">{cell.hole}</span>
                  <span className="review-hole-par">P{cell.par ?? '-'}</span>
                  <ScoreShapeChip cell={cell} />
                </button>
              </li>
            ))}
          </ul>
        </div>

        <ReviewHoleCanvas hole={validHole ?? 0} par={activeCell?.par ?? null} score={activeCell?.score ?? null} state={shotMapState} />

        <ReviewInspector
          hole={validHole ?? 0}
          par={activeCell?.par ?? null}
          score={activeCell?.score ?? null}
          toPar={activeCell?.toPar ?? null}
          timeline={timeline}
          decision={null}
          shotsLoading={shotMapState.status === 'loading'}
          manualPenalty={manualPenalty}
        />
      </div>
    </section>
  )
}
