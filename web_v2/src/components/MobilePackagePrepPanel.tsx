import { useState, type FormEvent } from 'react'
import type {
  MobileCourseOptionsResponse,
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

export type MobileCourseOptionsState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: MobileCourseOptionsResponse }
  | { status: 'error'; message: string }

interface MobilePackagePrepPanelProps {
  state: MobilePackagePrepState
  courseOptionsState?: MobileCourseOptionsState
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

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function asRecordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.map(asRecord).filter((row) => Object.keys(row).length) : []
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

function weatherCoverageText(data: LiveRoundPackageResponse) {
  const coverage = data.weatherSnapshot.coverage
  if (!coverage) return data.weatherSnapshot.source
  return `${coverage.ready}/${coverage.total} holes`
}

function readinessTitle(label: string) {
  return label.replace(/_/g, ' ')
}

function optionCoverageText(option: Record<string, unknown>) {
  const coverage = asRecord(option.coverage)
  const ready = compactValue(coverage.ready)
  const total = compactValue(coverage.total)
  return ready && total ? `coverage ${ready}/${total}` : null
}

function optionMissingText(option: Record<string, unknown>) {
  const rows = asRecordArray(option.missingData)
  const labels = rows.map(missingLabel).filter(Boolean)
  return labels.length ? `missing ${labels.slice(0, 2).join(', ')}` : null
}

function offlineSeedOptionRows(data: LiveRoundPackageResponse) {
  return asRecordArray(data.caddieContextSeeds)
    .flatMap((seed) => {
      const hole = compactValue(seed.hole) ?? '-'
      const selectedId = compactValue(seed.selectedOfflineOptionId)
      const sourceRef = compactValue(seed.sourceRef)
      return asRecordArray(seed.offlineOptions).map((option) => {
        const optionId = compactValue(option.id) ?? compactValue(option.optionId) ?? ''
        const label = compactValue(option.label) ?? (optionId || 'Option')
        const club = compactValue(option.clubName) ?? '-'
        const carry = compactValue(option.carryM)
        const confidence = compactValue(option.confidence)
        const sampleSize = compactValue(option.sampleSize)
        const sourceRefs = Array.isArray(option.sourceRefs) ? option.sourceRefs.map(compactValue).filter(Boolean) : []
        const sampleRefs = Array.isArray(option.sampleRefs) ? option.sampleRefs.map(compactValue).filter(Boolean) : []
        return {
          key: `${hole}-${optionId || label}`,
          hole,
          label,
          club,
          carry,
          confidence,
          sampleSize,
          coverage: optionCoverageText(option),
          sourceRef: sourceRefs[0] ?? sourceRef,
          sampleRefCount: sampleRefs.length,
          missing: optionMissingText(option),
          selected: selectedId ? selectedId === optionId : false,
        }
      })
    })
    .slice(0, 12)
}

export function MobilePackagePrepPanel({
  state,
  courseOptionsState = { status: 'idle' },
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
  const [selectedCourseOption, setSelectedCourseOption] = useState('')
  const [liveRoundId, setLiveRoundId] = useState('')
  const [teeBox, setTeeBox] = useState('')
  const [capturedAt, setCapturedAt] = useState('')
  const courseOptions = courseOptionsState.status === 'ready' && Array.isArray(courseOptionsState.data.courses)
    ? courseOptionsState.data.courses
    : []

  function handleCourseOptionChange(value: string) {
    setSelectedCourseOption(value)
    const option = courseOptions.find((row) => String(row.globalId) === value)
    if (!option) return
    setMode('course')
    setCourseGlobalId(String(option.globalId))
    setLiveRoundId(option.suggestedLiveRoundId ?? `live-${option.globalId}`)
    setTeeBox(option.teeBox && option.teeBox !== 'unknown' ? option.teeBox : '')
  }

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
            {courseOptions.length ? (
              <label>
                <span>Recent course</span>
                <select
                  value={selectedCourseOption}
                  onChange={(event) => handleCourseOptionChange(event.target.value)}
                >
                  <option value="">Manual course ID</option>
                  {courseOptions.map((option) => (
                    <option key={option.globalId} value={option.globalId}>
                      {option.name} / {option.holes} holes / {option.roundCount} rounds
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
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

      {mode === 'course' && courseOptionsState.status === 'loading' ? (
        <p className="mobile-package-note">Loading recent courses.</p>
      ) : null}

      {mode === 'course' && courseOptionsState.status === 'error' ? (
        <p className="mobile-package-note">Course options unavailable: {courseOptionsState.message}</p>
      ) : null}

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
  const readinessChecks = data.readinessChecks ?? []
  const seedOptions = offlineSeedOptionRows(data)
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
          <em>{weatherCoverageText(data)}</em>
        </article>
      </div>

      <div className="package-chip-row" aria-label="Package facts">
        {packageCoverageFacts(data).map((fact) => (
          <span key={fact}>{fact}</span>
        ))}
      </div>

      {readinessChecks.length ? (
        <div className="package-readiness-list" aria-label="Package readiness checks">
          {readinessChecks.map((row) => (
            <div className="report-row" key={row.label}>
              <strong>{readinessTitle(row.label)}</strong>
              <span className={`semantic-chip package-state-${row.state}`}>{row.state}</span>
              <span>{row.ready}/{row.total}</span>
              <span>{row.reason}</span>
            </div>
          ))}
        </div>
      ) : null}

      {seedOptions.length ? (
        <div className="package-caddie-list" aria-label="Offline caddie seed options">
          {seedOptions.map((row) => (
            <div className="report-row" key={row.key}>
              <strong>H{row.hole} {row.label}</strong>
              {row.selected ? <span className="semantic-chip package-state-ready">selected</span> : null}
              <span>{row.club}{row.carry ? ` / ${row.carry}m` : ''}</span>
              {row.confidence ? <span>{row.confidence} confidence</span> : null}
              {row.sampleSize ? <span>{row.sampleSize} samples</span> : null}
              {row.coverage ? <span>{row.coverage}</span> : null}
              {row.sourceRef ? <span>src {row.sourceRef}</span> : null}
              {row.sampleRefCount ? <span>sample refs {row.sampleRefCount}</span> : null}
              {row.missing ? <span>{row.missing}</span> : null}
            </div>
          ))}
        </div>
      ) : null}

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
