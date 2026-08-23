import { useEffect, useState } from 'react'
import type { CoursePrepHole, CoursePrepResponse, PrepTip } from '../types'
import { prefetchTopoImage, topoImageUrl } from '../api'
import { PrepHoleCanvas } from './PrepHoleCanvas'
import { PrepInspector } from './PrepInspector'
import { initialCum } from './prepWorkbenchLogic'
import { asNumber, type StatRow } from './statsValues'

// Signed to-par with at most one decimal: 1.25 → '+1.3', 0 → '0', -0.5 → '-0.5'.
function formatToParValue(value: number): string {
  const rounded = Number(value.toFixed(1))
  return rounded > 0 ? `+${rounded}` : String(rounded)
}

// First averageToPar per hole from this course's stats rows.
function holeAverages(rows: StatRow[]): Map<number, number> {
  const averages = new Map<number, number>()
  for (const row of rows) {
    const hole = asNumber(row.hole)
    const average = asNumber(row.averageToPar)
    if (hole !== null && average !== null && !averages.has(hole)) averages.set(hole, average)
  }
  return averages
}

type QuickBucket = 'under' | 'over' | 'bigover' | 'none'

// ≤0 under par, ≥+1 (bogey pace) big-over, between over; no history → neutral.
function quickBucket(average: number | null): QuickBucket {
  if (average === null) return 'none'
  if (average <= 0) return 'under'
  if (average >= 1) return 'bigover'
  return 'over'
}

// Played course: the holes you lose the most on — averageToPar desc, sampleCount≥2
// so one blow-up round can't define a key hole, joined to the loaded holes only.
function playedKeyHoleSet(rows: StatRow[], holes: CoursePrepHole[]): Set<number> {
  const known = new Set(holes.map((hole) => hole.hole))
  const qualified: Array<{ hole: number; average: number; worst: number }> = []
  for (const row of rows) {
    const hole = asNumber(row.hole)
    const average = asNumber(row.averageToPar)
    const samples = asNumber(row.sampleCount) ?? 0
    if (hole === null || average === null || samples < 2 || !known.has(hole)) continue
    qualified.push({ hole, average, worst: asNumber(row.worstToPar) ?? Number.NEGATIVE_INFINITY })
  }
  qualified.sort((a, b) => b.average - a.average || b.worst - a.worst || a.hole - b.hole)
  return new Set(qualified.slice(0, 3).map((row) => row.hole))
}

// Unplayed degradation: the 3 longest par-4/5 holes by blue-tee yardage.
function longKeyHoleSet(holes: CoursePrepHole[]): Set<number> {
  return new Set(
    holes
      .filter((hole) => (hole.par === 4 || hole.par === 5) && asNumber(hole.blue_yards) !== null)
      .sort((a, b) => b.blue_yards - a.blue_yards || a.hole - b.hole)
      .slice(0, 3)
      .map((hole) => hole.hole),
  )
}

export interface PrepWorkbenchProps {
  prepData: CoursePrepResponse
  holeRows: StatRow[]
  tips: PrepTip[] | null
  tipsError: string | null
  onRetryTips: () => void
  totals: { par: number; yards: number } | null
  record: { roundCount: number; average18: number } | null
}

// The map-first 备战 workbench: compact hole navigation + one large planning map.
// Full strategy/personal evidence is progressive disclosure over that same map,
// rather than a permanently visible report column that repeats its distances.
export function PrepWorkbench({
  prepData,
  holeRows,
  tips,
  tipsError,
  onRetryTips,
  totals,
  record,
}: PrepWorkbenchProps): React.ReactElement {
  const holes = prepData.holes
  const clubs = Array.isArray(prepData.clubs) ? prepData.clubs : []

  const [selected, setSelected] = useState<number | null>(() => holes[0]?.hole ?? null)
  // A course switch swaps the hole set — if the current pick is gone, snap to the
  // first hole (React "adjust state during render", runs once until it matches).
  const validSelected = selected !== null && holes.some((hole) => hole.hole === selected) ? selected : holes[0]?.hole ?? null
  if (validSelected !== selected) setSelected(validSelected)

  // Ball position (cum, metres) for the active hole; re-seeded whenever the
  // selected hole changes so every hole opens on its natural try-a-shot spot.
  const [ball, setBall] = useState<{ hole: number | null; cum: number }>(() => {
    const first = holes[0]
    return { hole: first?.hole ?? null, cum: first ? initialCum(first) : 0 }
  })
  if (ball.hole !== validSelected) {
    const next = holes.find((hole) => hole.hole === validSelected)
    setBall({ hole: validSelected, cum: next ? initialCum(next) : 0 })
  }

  const active = holes.find((hole) => hole.hole === validSelected) ?? holes[0] ?? null
  const averages = holeAverages(holeRows)
  const played = playedKeyHoleSet(holeRows, holes)
  const keyHoles = played.size > 0 ? played : longKeyHoleSet(holes)

  // Warm each factual topo exactly once. The previous implementation ran both an all-hole pass and
  // a neighbour pass, so changing holes repeatedly requested the same images. The server already
  // prewarms the course; this pass only fills the browser cache for instant hole switching.
  const globalId = prepData.globalId
  useEffect(() => {
    for (const hole of holes) {
      if (hole.map?.overlay) {
        prefetchTopoImage(topoImageUrl(globalId, hole.hole, hole.geometryRevision))
      }
    }
  }, [holes, globalId])

  return (
    <div className="prep-work prep-work--map-first">
      <div className="prep-holes">
        <div className="prep-holes-head">
          <span>球洞</span>
          {totals ? (
            <span className="prep-holes-total">
              PAR {totals.par} · {totals.yards} 码
            </span>
          ) : null}
        </div>
        {record ? (
          <p className="prep-holes-record">
            你的战绩:打过 {record.roundCount} 次 · 均杆 {Number(record.average18.toFixed(1))}
          </p>
        ) : null}
        <div className="prep-hole-nav" aria-label="选择球洞">
          <button
            type="button"
            className="prep-hole-nav-arrow"
            aria-label="上一洞"
            disabled={holes.findIndex((hole) => hole.hole === validSelected) <= 0}
            onClick={() => {
              const index = holes.findIndex((hole) => hole.hole === validSelected)
              if (index > 0) setSelected(holes[index - 1].hole)
            }}
          >
            ‹
          </button>
          <label className="prep-hole-picker">
            <span>当前球洞</span>
            <select
              aria-label="选择球洞"
              value={validSelected ?? ''}
              onChange={(event) => setSelected(Number(event.target.value))}
            >
              {holes.map((hole) => {
                const average = averages.get(hole.hole) ?? null
                return (
                  <option key={hole.hole} value={hole.hole}>
                    第 {hole.hole} 洞 · Par {hole.par} · {hole.blue_yards}码
                    {average !== null ? ` · 平均${formatToParValue(average)}` : ''}
                    {keyHoles.has(hole.hole) ? ' · 关键' : ''}
                  </option>
                )
              })}
            </select>
          </label>
          <button
            type="button"
            className="prep-hole-nav-arrow"
            aria-label="下一洞"
            disabled={holes.findIndex((hole) => hole.hole === validSelected) >= holes.length - 1}
            onClick={() => {
              const index = holes.findIndex((hole) => hole.hole === validSelected)
              if (index >= 0 && index < holes.length - 1) setSelected(holes[index + 1].hole)
            }}
          >
            ›
          </button>
        </div>
        {/* Hole/par/yardage are already on the map and in the picker. Keep only personal context here. */}
        {active ? (
          <div className="prep-active-hole-summary">
            {averages.get(active.hole) != null ? (
              <span className={`prep-hole-avg ${quickBucket(averages.get(active.hole) ?? null)}`}>
                平均{formatToParValue(averages.get(active.hole) as number)}
              </span>
            ) : null}
            {keyHoles.has(active.hole) ? <span className="prep-hole-key">关键</span> : null}
          </div>
        ) : null}
      </div>

      {active ? (
        <>
          <PrepHoleCanvas hole={active} cum={ball.cum} onCum={(cum) => setBall({ hole: validSelected, cum })} globalId={prepData.globalId} clubs={clubs} />
          <PrepInspector hole={active} tips={tips} tipsError={tipsError} onRetryTips={onRetryTips} />
        </>
      ) : (
        <p className="prep-inspector-placeholder">此球场暂无球洞数据</p>
      )}
    </div>
  )
}
