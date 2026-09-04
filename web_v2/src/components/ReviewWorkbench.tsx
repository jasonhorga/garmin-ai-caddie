import { useEffect, useRef, useState } from 'react'
import type { RoundCard, RoundCorrectionRequest, RoundHoleShot, RoundHoleShotMapResponse, ScoreStripCell } from '../types'
import { prefetchTopoImage, topoImageUrl } from '../api'
import { cleanCourseName, shortRoundDate } from '../units'
import { ReviewHoleCanvas, type ReviewShotMapState } from './ReviewHoleCanvas'
import { ReviewInspector } from './ReviewInspector'
import { buildTimeline, chipShape, chipShapeZh, type ChipShape } from './reviewShotMapLogic'
import {
  invalidateReviewShotMapCache,
  isValidRoundHoleShotMapResponse,
  readReviewShotMapCache,
  writeReviewShotMapCache,
} from './reviewShotMapCache'

interface ReviewWorkbenchProps {
  rounds: RoundCard[]
  fetchShotMap: (roundRef: string, hole: number) => Promise<RoundHoleShotMapResponse>
  saveCorrection?: (roundRef: string, correction: RoundCorrectionRequest) => Promise<unknown>
  /** Stable player id used to isolate the optional browser shot-map cache. */
  playerNamespace?: string | null
}

interface ReviewDraft {
  shots: RoundHoleShot[]
  manualPenalty: number
}

function draftId(index: number): string {
  const uuid = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${index}`
  return `web-draft-${uuid}`
}

function editableShots(shots: RoundHoleShot[]): RoundHoleShot[] {
  return shots.map((shot, index) => ({ ...shot, id: shot.id ?? (shot.synthetic ? null : `web-source-${index + 1}`) }))
}

function reconnectShots(shots: RoundHoleShot[]): RoundHoleShot[] {
  return shots.map((shot, index) => ({
    ...shot,
    order: index + 1,
    start: index > 0 && shots[index - 1].end ? shots[index - 1].end : shot.start,
  }))
}

function canEditPositions(data: RoundHoleShotMapResponse): boolean {
  return data.mapKind === 'prodgeometry' && Boolean(data.geometryRevision) && data.map !== null
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
  cached: RoundHoleShotMapResponse | undefined,
  failure: ShotMapFailure | null,
  key: string | null,
): ReviewShotMapState {
  if (cached === undefined) {
    if (failure !== null && key !== null && failure.key === key) return { status: 'error', message: failure.message }
    return { status: 'loading' }
  }
  const data = cached
  if (data.found && data.map) return { status: 'ready', data }
  const missing = Array.isArray(data.missingData) ? data.missingData : []
  const reason = missing.find((row) => typeof row?.reason === 'string')?.reason
  return { status: 'nogeo', message: typeof reason === 'string' ? reason : '这一洞暂无球场几何,画不了落点图。' }
}

type ShotMapFailure = { key: string; message: string }

// The 复盘 round-review workbench: a round selector across the top, the round's
// holes (shape-coded score chips) down the left, the per-hole落点图 in the middle,
// and the 杆序 timeline on the right. Selection lives here so the three panes stay
// in sync; the shot map is fetched lazily per hole and kept per round+hole so
// stepping back to a visited hole paints its first frame without a refetch.
export function ReviewWorkbench({ rounds, fetchShotMap, saveCorrection, playerNamespace }: ReviewWorkbenchProps): React.ReactElement {
  const cacheNamespace = playerNamespace?.trim() || null
  const [selectedRoundId, setSelectedRoundId] = useState<string | null>(() => rounds[0]?.id ?? null)
  const [selectedHole, setSelectedHole] = useState<number | null>(null)
  // Session cache of shot-map RESPONSES keyed `${roundRef}:${hole}`. Only resolved responses land
  // here; a rejected fetch is held separately in `shotMapFailure` so returning to a hole that failed
  // retries instead of pinning a stale error. A response is per (round, hole) immutable evidence, so
  // reusing it is what makes the hole strip feel instant on the second visit.
  const [shotMaps, setShotMaps] = useState<Record<string, RoundHoleShotMapResponse>>(() => {
    const firstRound = rounds[0]
    const firstHole = firstRound?.scoreStrip?.[0]?.hole
    const cached = firstRound && firstHole !== undefined ? readReviewShotMapCache(cacheNamespace, firstRound.id, firstHole) : undefined
    return cached ? { [`${firstRound.id}:${firstHole}`]: cached } : {}
  })
  const [shotMapFailure, setShotMapFailure] = useState<ShotMapFailure | null>(null)
  const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({})
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'error'>('idle')
  // Keep the fetcher in a ref so the shot-map effect keys only off round+hole+cache and
  // never refetches just because the parent handed a fresh closure identity.
  const fetchRef = useRef(fetchShotMap)
  // Keys with a request in the air. The effect re-runs whenever the cache grows (a neighbouring
  // hole resolved), and this stops that re-run from launching a second request for the hole that
  // is still loading.
  const inFlight = useRef<Set<string>>(new Set())
  const namespaceRef = useRef(cacheNamespace)
  const [hydratedNamespace, setHydratedNamespace] = useState<string | null>(cacheNamespace)
  useEffect(() => {
    fetchRef.current = fetchShotMap
  })

  // A player switch must discard the previous player's in-memory responses before
  // the fetch effect is allowed to consult the new namespace's persistent cache.
  useEffect(() => {
    if (hydratedNamespace === cacheNamespace) return
    Promise.resolve().then(() => {
      namespaceRef.current = cacheNamespace
      inFlight.current.clear()
      setShotMaps({})
      setShotMapFailure(null)
      setDrafts({})
      setEditingKey(null)
      setSaveState('idle')
      setHydratedNamespace(cacheNamespace)
    })
  }, [cacheNamespace, hydratedNamespace])

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
    if (hydratedNamespace !== cacheNamespace || validRoundId === null || validHole === null) return
    const key = `${validRoundId}:${validHole}`
    const requestKey = `${cacheNamespace ?? 'no-player-cache'}:${key}`
    if (shotMaps[key] !== undefined || inFlight.current.has(requestKey)) return
    const persisted = readReviewShotMapCache(cacheNamespace, validRoundId, validHole)
    if (persisted !== undefined) {
      // Publish outside the effect body so React's hook lint rule does not treat
      // storage hydration as a cascading synchronous effect update.
      Promise.resolve().then(() => {
        setShotMaps((previous) => (previous[key] === undefined ? { ...previous, [key]: persisted } : previous))
      })
      return
    }
    const requestNamespace = cacheNamespace
    inFlight.current.add(requestKey)
    fetchRef
      .current(validRoundId, validHole)
      .then((data) => {
        if (!isValidRoundHoleShotMapResponse(data, validRoundId, validHole)) throw new Error('落点图响应无效')
        inFlight.current.delete(requestKey)
        if (namespaceRef.current !== requestNamespace) return
        setShotMaps((previous) => ({ ...previous, [key]: data }))
        writeReviewShotMapCache(requestNamespace, data)
        // Prefetch the adjacent holes' topo bitmap so stepping the strip is instant. Revisions are
        // hole-specific: this response only proves the CURRENT hole's revision, so neighbour warm-up
        // must use the revision-free URL. The selected neighbour will use its own revision after its
        // shot-map response arrives. Multi-course guesses remain best-effort cache warm-ups.
        if (data.found && data.map && data.globalId != null && data.localHole != null) {
          for (const local of [data.localHole - 1, data.localHole + 1]) {
            if (local >= 1) {
              prefetchTopoImage(topoImageUrl(data.globalId, local))
            }
          }
        }
      })
      .catch((error: unknown) => {
        // Failures are never cached: leaving the key out of `shotMaps` means the next visit to this
        // hole fetches again.
        inFlight.current.delete(requestKey)
        if (namespaceRef.current !== requestNamespace) return
        setShotMapFailure({ key, message: error instanceof Error ? error.message : '落点图加载失败' })
      })
  }, [cacheNamespace, hydratedNamespace, validRoundId, validHole, shotMaps])

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
    validHole === null
      ? { status: 'nogeo', message: '这局暂无逐洞成绩，无法展示落点图。' }
      : deriveShotMapState(shotMapKey === null ? undefined : shotMaps[shotMapKey], shotMapFailure, shotMapKey)
  const activeCell = holes.find((cell) => cell.hole === validHole) ?? null
  const editableMap = shotMapState.status === 'ready' && canEditPositions(shotMapState.data)
  const currentDraft = shotMapKey !== null ? drafts[shotMapKey] : undefined
  const isEditing = editingKey === shotMapKey && currentDraft !== undefined && shotMapState.status === 'ready'
  const displayedShotMapState: ReviewShotMapState =
    isEditing && shotMapState.status === 'ready' && currentDraft
      ? { ...shotMapState, data: { ...shotMapState.data, shots: currentDraft.shots, manualPenalty: currentDraft.manualPenalty } }
      : shotMapState
  const ppm = shotMapState.status === 'ready' ? shotMapState.data.map?.overlay.ppm ?? null : null
  const timeline = displayedShotMapState.status === 'ready' ? buildTimeline(displayedShotMapState.data.shots, ppm) : []
  const manualPenalty = displayedShotMapState.status === 'ready' ? displayedShotMapState.data.manualPenalty ?? 0 : 0
  const roundScore = selectedRound.score ?? null
  const roundToPar = selectedRound.toPar ?? null

  function beginEditing(): void {
    if (!saveCorrection || shotMapKey === null || shotMapState.status !== 'ready' || !canEditPositions(shotMapState.data)) return
    setDrafts((previous) => ({
      ...previous,
      [shotMapKey]: previous[shotMapKey] ?? {
        shots: editableShots(shotMapState.data.shots),
        manualPenalty: shotMapState.data.manualPenalty ?? 0,
      },
    }))
    setEditingKey(shotMapKey)
    setSaveState('idle')
  }

  function updateDraft(transform: (draft: ReviewDraft) => ReviewDraft): void {
    if (shotMapKey === null) return
    setDrafts((previous) => {
      const draft = previous[shotMapKey]
      return draft ? { ...previous, [shotMapKey]: transform(draft) } : previous
    })
  }

  function addDraftShot(px: [number, number]): void {
    if (!isEditing || !currentDraft) return
    const previous = currentDraft.shots[currentDraft.shots.length - 1]
    const start = previous?.end ?? (shotMapState.status === 'ready' ? shotMapState.data.map?.overlay.route[0]?.slice(0, 2) as [number, number] | undefined : undefined) ?? px
    const shot: RoundHoleShot = {
      id: draftId(currentDraft.shots.length),
      start,
      end: px,
      club: null,
      lie: previous?.endLie ?? previous?.lie ?? null,
      endLie: null,
      shotType: 'MANUAL',
      order: currentDraft.shots.length + 1,
      synthetic: false,
    }
    updateDraft((draft) => ({ ...draft, shots: reconnectShots([...draft.shots, shot]) }))
  }

  function addNextDraftShot(): void {
    if (!currentDraft || shotMapState.status !== 'ready') return
    const overlay = shotMapState.data.map?.overlay
    const last = currentDraft.shots[currentDraft.shots.length - 1]?.end
    const fallback = overlay?.route[overlay.route.length - 1]?.slice(0, 2) as [number, number] | undefined
    const base = last ?? fallback ?? [0, 0]
    const px: [number, number] = overlay
      ? [Math.max(0, Math.min(overlay.w, base[0] + 12)), Math.max(0, Math.min(overlay.h, base[1] - 28))]
      : [base[0] + 1, base[1] + 1]
    addDraftShot(px)
  }

  function moveDraftShot(shotId: string, px: [number, number]): void {
    if (!isEditing) return
    updateDraft((draft) => {
      const index = draft.shots.findIndex((shot) => shot.id === shotId)
      if (index < 0) return draft
      const shots = draft.shots.map((shot, shotIndex) => (shotIndex === index ? { ...shot, end: px } : shot))
      return { ...draft, shots: reconnectShots(shots) }
    })
  }

  function deleteDraftShot(shotId: string): void {
    if (!isEditing) return
    updateDraft((draft) => ({ ...draft, shots: reconnectShots(draft.shots.filter((shot) => shot.id !== shotId)) }))
  }

  function reorderDraftShot(index: number, direction: -1 | 1): void {
    if (!isEditing || !currentDraft) return
    const target = index + direction
    if (target < 0 || target >= currentDraft.shots.length) return
    const shots = [...currentDraft.shots]
    const [moved] = shots.splice(index, 1)
    shots.splice(target, 0, moved)
    updateDraft((draft) => ({ ...draft, shots: reconnectShots(shots) }))
  }

  async function saveDraft(): Promise<void> {
    if (!saveCorrection || !isEditing || !currentDraft || shotMapKey === null || shotMapState.status !== 'ready' || !canEditPositions(shotMapState.data)) return
    setSaveState('saving')
    const roundRef = validRoundId ?? shotMapState.data.roundRef
    const correction: RoundCorrectionRequest = {
      op: 'replaceHoleShots',
      hole: validHole ?? shotMapState.data.hole,
      // Synthetic route anchors are inferred display aids, not recorded strokes. Keep them in the
      // draft for context, but never promote them into an approved whole-hole snapshot.
      shots: currentDraft.shots.filter((shot) => !shot.synthetic).map((shot, index) => ({
        id: shot.id ?? `web-source-${index + 1}`,
        start: shot.start,
        end: shot.end,
        club: shot.club,
        lie: shot.lie,
        endLie: shot.endLie,
        shotType: shot.shotType,
        order: index + 1,
        synthetic: shot.synthetic,
      })),
      manualPenalty: currentDraft.manualPenalty,
      geometryRevision: shotMapState.data.geometryRevision ?? undefined,
      clientMutationId: draftId(0),
    }
    try {
      await saveCorrection(roundRef, correction)
      // A correction changes the canonical response. Evict both layers so the next
      // visit performs a fresh read instead of showing stale geometry/shots.
      const correctedHole = validHole ?? shotMapState.data.hole
      invalidateReviewShotMapCache(cacheNamespace, roundRef, correctedHole)
      setShotMaps((previous) => {
        const next = { ...previous }
        delete next[shotMapKey]
        return next
      })
      setDrafts((previous) => {
        const next = { ...previous }
        delete next[shotMapKey]
        return next
      })
      setEditingKey(null)
      setSaveState('idle')
    } catch {
      setSaveState('error')
    }
  }

  function cancelDraft(): void {
    if (shotMapKey === null) return
    setDrafts((previous) => {
      const next = { ...previous }
      delete next[shotMapKey]
      return next
    })
    setEditingKey(null)
    setSaveState('idle')
  }

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

      <div className="review-work review-work--map-first">
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

        <ReviewHoleCanvas
          hole={validHole ?? 0}
          par={activeCell?.par ?? null}
          score={activeCell?.score ?? null}
          state={displayedShotMapState}
          editing={isEditing}
          onMapClick={addDraftShot}
          onShotMove={moveDraftShot}
        />

        <ReviewInspector
          hole={validHole ?? 0}
          par={activeCell?.par ?? null}
          score={activeCell?.score ?? null}
          toPar={activeCell?.toPar ?? null}
          timeline={timeline}
          decision={null}
          shotsLoading={displayedShotMapState.status === 'loading'}
          manualPenalty={manualPenalty}
        />

        {saveCorrection && editableMap ? <div className="review-editor" aria-label="复盘编辑">
          {!isEditing ? (
            <button type="button" className="review-editor-button" onClick={beginEditing} disabled={shotMapState.status !== 'ready'}>
              编辑落点
            </button>
          ) : (
            <>
              <div className="review-editor-actions">
                <button type="button" className="review-editor-button review-editor-button--primary" onClick={addNextDraftShot}>
                  添加下一杆
                </button>
                <button type="button" className="review-editor-button review-editor-button--primary" onClick={() => void saveDraft()} disabled={saveState === 'saving'}>
                  {saveState === 'saving' ? '保存中…' : '保存全部修改'}
                </button>
                <button type="button" className="review-editor-button" onClick={cancelDraft} disabled={saveState === 'saving'}>
                  取消
                </button>
              </div>
              <p className="review-editor-hint">点击地图添加落点，拖动黄色落点调整位置。</p>
              {saveState === 'error' ? <p className="review-editor-error" role="alert">保存失败，修改仍保留在草稿中。</p> : null}
              <ol className="review-editor-shots" aria-label="编辑杆序">
                {(currentDraft?.shots ?? []).map((shot, index) => (
                  <li key={shot.id ?? `shot-${index}`} className="review-editor-shot">
                    <span className="review-editor-shot-label">第 {index + 1} 杆</span>
                    <span className="review-editor-shot-club">{shot.club || '未选球杆'}</span>
                    <button type="button" aria-label={`第${index + 1}杆上移`} onClick={() => reorderDraftShot(index, -1)} disabled={index === 0}>上移</button>
                    <button type="button" aria-label={`第${index + 1}杆下移`} onClick={() => reorderDraftShot(index, 1)} disabled={index === (currentDraft?.shots.length ?? 1) - 1}>下移</button>
                    <button type="button" aria-label={`删除第${index + 1}杆`} onClick={() => shot.id && deleteDraftShot(shot.id)}>删除</button>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div> : null}

      </div>
    </section>
  )
}
