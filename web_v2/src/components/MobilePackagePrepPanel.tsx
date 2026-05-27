import { useState, type FormEvent } from 'react'
import type {
  LiveRoundPackageResponse,
  MobileCoursePackageParams,
  MobileRoundPackageParams,
} from '../types'

type PackagePrepMode = 'round' | 'course'

export type MobilePackagePrepState =
  | { status: 'idle' }
  | { status: 'loading'; mode: PackagePrepMode; target: string }
  | { status: 'ready'; data: LiveRoundPackageResponse }
  | { status: 'error'; mode: PackagePrepMode; target: string; message: string }

interface MobilePackagePrepPanelProps {
  state: MobilePackagePrepState
  onPrepareRound: (roundId: string, params: MobileRoundPackageParams) => void | Promise<void>
  onPrepareCourse: (globalId: number, params: MobileCoursePackageParams) => void | Promise<void>
  defaultRoundId?: string
  defaultCourseGlobalId?: string
  showAdminTokenInput?: boolean
  adminTokenValue?: string
  onAdminTokenChange?: (value: string) => void
}

function trimmedOrUndefined(value: string) {
  const trimmed = value.trim()
  return trimmed.length ? trimmed : undefined
}

function compactValue(value: unknown) {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return null
}

function missingLabel(row: Record<string, unknown>) {
  return compactValue(row.label) ?? compactValue(row.key) ?? 'missing'
}

function missingReason(row: Record<string, unknown>) {
  return compactValue(row.reason) ?? compactValue(row.detail) ?? ''
}

function recentScoreCount(data: LiveRoundPackageResponse) {
  const recentScores = (data.recentHistory.course as Record<string, unknown> | undefined)?.recentScores
  return Array.isArray(recentScores) ? recentScores.length : 0
}

function packageCoverageFacts(data: LiveRoundPackageResponse) {
  const coverage = data.sourceCoverage
  const facts = [
    `source ${coverage.state}`,
    `${coverage.dataMode} data`,
    `${coverage.availableRoundCount} available rounds`,
    `${coverage.holeCount} holes`,
    `${coverage.clubProfileCount} clubs`,
    `${recentScoreCount(data)} recent scores`,
  ]
  if (coverage.preparationMode === 'course' && coverage.requestedCourseGlobalId) {
    facts.push(`course ${coverage.requestedCourseGlobalId}`)
  }
  if (typeof coverage.courseFound === 'boolean') {
    facts.push(coverage.courseFound ? 'course found' : 'course missing')
  }
  facts.push(coverage.roundFound ? 'round found' : 'round missing')
  facts.push(coverage.selectedRoundId ? `template round ${coverage.selectedRoundId}` : 'no template round')
  facts.push(`expires ${data.offlinePackageStatus.expiresAt}`)
  return facts
}

export function MobilePackagePrepPanel({
  state,
  onPrepareRound,
  onPrepareCourse,
  defaultRoundId = '900001',
  defaultCourseGlobalId = '31795',
  showAdminTokenInput = false,
  adminTokenValue = '',
  onAdminTokenChange,
}: MobilePackagePrepPanelProps) {
  const [mode, setMode] = useState<PackagePrepMode>('round')
  const [roundId, setRoundId] = useState(defaultRoundId)
  const [courseGlobalId, setCourseGlobalId] = useState(defaultCourseGlobalId)
  const [liveRoundId, setLiveRoundId] = useState('')
  const [teeBox, setTeeBox] = useState('')
  const [capturedAt, setCapturedAt] = useState('')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const captured = trimmedOrUndefined(capturedAt)
    if (mode === 'round') {
      const nextRoundId = roundId.trim()
      if (!nextRoundId) return
      void onPrepareRound(nextRoundId, { capturedAt: captured })
      return
    }

    const parsedGlobalId = Number(courseGlobalId.trim())
    if (!Number.isInteger(parsedGlobalId) || parsedGlobalId <= 0) return
    void onPrepareCourse(parsedGlobalId, {
      roundId: trimmedOrUndefined(liveRoundId),
      teeBox: trimmedOrUndefined(teeBox),
      capturedAt: captured,
    })
  }

  const isLoading = state.status === 'loading'
  const readyData = state.status === 'ready' ? state.data : null
  const courseIdValue = Number(courseGlobalId.trim())
  const canPrepare = mode === 'round' ? Boolean(roundId.trim()) : Number.isInteger(courseIdValue) && courseIdValue > 0

  return (
    <section className="mobile-package-panel" aria-label="Mobile package preparation">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Offline Round</p>
          <h2>Mobile Package Prep</h2>
        </div>
        {readyData ? <span className={`semantic-chip package-state-${readyData.offlinePackageStatus.state}`}>{readyData.offlinePackageStatus.state}</span> : null}
      </div>

      <form className="mobile-package-form" aria-label="Mobile package lookup" onSubmit={handleSubmit}>
        <div className="package-mode-toggle" role="radiogroup" aria-label="Package mode">
          <label>
            <input
              type="radio"
              name="package-mode"
              checked={mode === 'round'}
              onChange={() => setMode('round')}
            />
            <span>Round</span>
          </label>
          <label>
            <input
              type="radio"
              name="package-mode"
              checked={mode === 'course'}
              onChange={() => setMode('course')}
            />
            <span>Course</span>
          </label>
        </div>

        {mode === 'round' ? (
          <label>
            <span>Round ID</span>
            <input value={roundId} onChange={(event) => setRoundId(event.target.value)} spellCheck={false} />
          </label>
        ) : (
          <>
            <label>
              <span>Course global ID</span>
              <input inputMode="numeric" value={courseGlobalId} onChange={(event) => setCourseGlobalId(event.target.value)} spellCheck={false} />
            </label>
            <label>
              <span>Live round ID</span>
              <input value={liveRoundId} onChange={(event) => setLiveRoundId(event.target.value)} spellCheck={false} />
            </label>
            <label>
              <span>Tee box</span>
              <input value={teeBox} onChange={(event) => setTeeBox(event.target.value)} spellCheck={false} />
            </label>
          </>
        )}

        <label>
          <span>Captured time</span>
          <input value={capturedAt} onChange={(event) => setCapturedAt(event.target.value)} spellCheck={false} placeholder="2026-05-25T08:00:00Z" />
        </label>

        {showAdminTokenInput ? (
          <label>
            <span>Admin token</span>
            <input
              type="password"
              value={adminTokenValue}
              onChange={(event) => onAdminTokenChange?.(event.target.value)}
              spellCheck={false}
              autoComplete="off"
            />
          </label>
        ) : null}

        <button type="submit" disabled={!canPrepare || isLoading}>
          {isLoading ? 'Preparing package' : 'Prepare package'}
        </button>
      </form>

      {state.status === 'idle' ? (
        <article className="stats-empty">
          <h2>No package prepared</h2>
          <p>Choose a round or course before starting live play.</p>
        </article>
      ) : null}

      {state.status === 'loading' ? (
        <article className="stats-empty">
          <h2>Preparing package</h2>
          <p>{state.target}</p>
        </article>
      ) : null}

      {state.status === 'error' ? (
        <article className="stats-empty">
          <h2>Package unavailable</h2>
          <p>{state.message}</p>
        </article>
      ) : null}

      {readyData ? <PackageSummary data={readyData} /> : null}
    </section>
  )
}

function PackageSummary({ data }: { data: LiveRoundPackageResponse }) {
  const missingRows = data.missingData ?? []
  return (
    <div className="mobile-package-body">
      <div className="package-summary-grid" aria-label="Package summary">
        <article>
          <span>Course</span>
          <strong>{data.course.name}</strong>
          <em>{data.course.globalId} / {data.course.teeBox}</em>
        </article>
        <article>
          <span>Round</span>
          <strong>{data.roundId}</strong>
          <em>{data.sourceCoverage.preparationMode ?? 'round'} package</em>
        </article>
        <article>
          <span>Geometry</span>
          <strong>{data.geometryCoverage.state}</strong>
          <em>{data.geometryCoverage.readyHoles}/{data.geometryCoverage.totalHoles} holes</em>
        </article>
        <article>
          <span>Weather</span>
          <strong>weather {data.weatherSnapshot.state}</strong>
          <em>{data.weatherSnapshot.source}</em>
        </article>
      </div>

      <div className="package-chip-row" aria-label="Package facts">
        {packageCoverageFacts(data).map((fact) => (
          <span key={fact}>{fact}</span>
        ))}
      </div>

      <div className="package-missing-list" aria-label="Package missing data">
        {missingRows.length ? (
          missingRows.map((row, index) => (
            <div className="report-row" key={`${missingLabel(row)}-${index}`}>
              <strong>{missingLabel(row)}</strong>
              <span>{missingReason(row)}</span>
            </div>
          ))
        ) : (
          <div className="report-row">
            <strong>coverage</strong>
            <span>ready</span>
          </div>
        )}
      </div>
    </div>
  )
}
