import { useEffect, useRef, useState } from 'react'
import type {
  CaddieDecisionAuditRecord,
  CaddieContextParams,
  CaddieContextResponse,
  CaddieDecisionRequest,
  CaddieDecisionResponse,
  CaddieShotType,
  MediaCreateRequest,
  MediaKind,
  MediaRecord,
  MediaTargetType,
  WeatherSnapshotResponse,
  VisionConfirmationState,
  VisionFindingRecord,
} from '../types'
import { SourceRefs } from './SourceRefs'

type AuditState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: CaddieDecisionAuditRecord | null }

type WeatherLoadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: WeatherSnapshotResponse }

type CaddieContextLoadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: CaddieContextResponse }

export type MediaContextState =
  | { status: 'idle' }
  | { status: 'loading'; targetType: MediaTargetType; targetId: string }
  | { status: 'error'; targetType: MediaTargetType; targetId: string; message: string }
  | {
      status: 'ready'
      targetType: MediaTargetType
      targetId: string
      media: MediaRecord[]
      findings: VisionFindingRecord[]
    }

interface CaddiePageProps {
  decisionState: { status: 'idle' } | { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: CaddieDecisionResponse }
  auditState?: AuditState
  weatherState?: WeatherLoadState
  contextState?: CaddieContextLoadState
  mediaState?: MediaContextState
  onRequestDecision: (request: CaddieDecisionRequest) => void
  onCreateAudit?: (decision: CaddieDecisionResponse, actualShot: Record<string, unknown>) => void
  onLoadWeather?: () => void
  onLoadCaddieContext?: (params: CaddieContextParams) => void
  onLoadMediaContext?: (target: { targetType: MediaTargetType; targetId: string }) => void
  onAttachMedia?: (request: MediaCreateRequest) => void | Promise<void>
  onAnalyzeMedia?: (mediaId: string) => void
  onRedactMedia?: (mediaId: string) => void
  onConfirmVisionFinding?: (findingId: string, confirmationState: Extract<VisionConfirmationState, 'manual_confirmed' | 'rejected'>) => void
  onSelectRef?: (sourceRef: string) => void
  selectedSourceRef?: string
}

export function CaddiePage({
  decisionState,
  auditState = { status: 'idle' },
  weatherState = { status: 'idle' },
  contextState = { status: 'idle' },
  mediaState = { status: 'idle' },
  onRequestDecision,
  onCreateAudit,
  onLoadWeather,
  onLoadCaddieContext,
  onLoadMediaContext,
  onAttachMedia,
  onAnalyzeMedia,
  onRedactMedia,
  onConfirmVisionFinding,
  onSelectRef = () => undefined,
  selectedSourceRef,
}: CaddiePageProps) {
  const [shotType, setShotType] = useState<CaddieShotType>('approach')
  const initialSelectedSourceRef = selectedSourceRef?.trim() || '900001:7'
  const previousSelectedSourceRef = useRef(selectedSourceRef?.trim() || '')
  const [contextSourceRef, setContextSourceRef] = useState(initialSelectedSourceRef)
  const [contextDistance, setContextDistance] = useState('142')
  const [contextLie, setContextLie] = useState('fairway')
  const [currentLatitude, setCurrentLatitude] = useState('')
  const [currentLongitude, setCurrentLongitude] = useState('')
  const [targetLatitude, setTargetLatitude] = useState('')
  const [targetLongitude, setTargetLongitude] = useState('')
  const [strategyMode, setStrategyMode] = useState('')
  const [routeStartX, setRouteStartX] = useState('')
  const [routeStartY, setRouteStartY] = useState('')
  const [routeTargetX, setRouteTargetX] = useState('')
  const [routeTargetY, setRouteTargetY] = useState('')
  const [landingRadius, setLandingRadius] = useState('18')
  const weatherSnapshot = weatherState.status === 'ready' ? weatherState.data : null
  const visionFindings = mediaState.status === 'ready' ? mediaState.findings : []
  const hasSourceContext = contextStateMatchesSourceRef(contextState, contextSourceRef)

  useEffect(() => {
    const nextSourceRef = selectedSourceRef?.trim()
    if (nextSourceRef && nextSourceRef !== previousSelectedSourceRef.current) {
      setContextSourceRef(nextSourceRef)
    }
    previousSelectedSourceRef.current = nextSourceRef || ''
  }, [selectedSourceRef])

  return (
    <section className="caddie-workspace">
      <div className="section-head">
        <div>
          <p className="eyebrow">Decision layer</p>
          <h1>Caddie</h1>
          <p>Compare safe, stock, and attack plans with evidence, missing data, and audit criteria.</p>
        </div>
      </div>

      <section className="caddie-control-bar" aria-label="Caddie controls">
        <label htmlFor="shot-type">Shot type</label>
        <select id="shot-type" value={shotType} onChange={(event) => setShotType(event.target.value as CaddieShotType)}>
          <option value="approach">Approach</option>
          <option value="tee">Tee</option>
          <option value="recovery">Recovery</option>
        </select>
        {onLoadWeather ? (
          <button type="button" onClick={onLoadWeather}>
            Load weather
          </button>
        ) : null}
        <button
          type="button"
          disabled={!hasSourceContext}
          onClick={() => onRequestDecision(buildDecisionRequest(shotType, contextState, weatherSnapshot, visionFindings))}
        >
          Request caddie plan
        </button>
        {!hasSourceContext ? <span className="caddie-context-required">Load caddie context before requesting a source-bound plan.</span> : null}
      </section>

      {onLoadWeather ? <WeatherContextPanel state={weatherState} /> : null}
      <CaddieContextPanel
        state={contextState}
        sourceRef={contextSourceRef}
        distance={contextDistance}
        lie={contextLie}
        currentLatitude={currentLatitude}
        currentLongitude={currentLongitude}
        targetLatitude={targetLatitude}
        targetLongitude={targetLongitude}
        strategyMode={strategyMode}
        routeStartX={routeStartX}
        routeStartY={routeStartY}
        routeTargetX={routeTargetX}
        routeTargetY={routeTargetY}
        landingRadius={landingRadius}
        shotType={shotType}
        onSourceRefChange={setContextSourceRef}
        onDistanceChange={setContextDistance}
        onLieChange={setContextLie}
        onCurrentLatitudeChange={setCurrentLatitude}
        onCurrentLongitudeChange={setCurrentLongitude}
        onTargetLatitudeChange={setTargetLatitude}
        onTargetLongitudeChange={setTargetLongitude}
        onStrategyModeChange={setStrategyMode}
        onRouteStartXChange={setRouteStartX}
        onRouteStartYChange={setRouteStartY}
        onRouteTargetXChange={setRouteTargetX}
        onRouteTargetYChange={setRouteTargetY}
        onLandingRadiusChange={setLandingRadius}
        onLoadCaddieContext={onLoadCaddieContext}
      />
      <MediaContextPanel
        state={mediaState}
        onLoadMediaContext={onLoadMediaContext}
        onAttachMedia={onAttachMedia}
        onAnalyzeMedia={onAnalyzeMedia}
        onRedactMedia={onRedactMedia}
        onConfirmVisionFinding={onConfirmVisionFinding}
      />
      <DecisionDetail state={decisionState} auditState={auditState} onCreateAudit={onCreateAudit} onSelectRef={onSelectRef} />
    </section>
  )
}

function CaddieContextPanel({
  state,
  sourceRef,
  distance,
  lie,
  currentLatitude,
  currentLongitude,
  targetLatitude,
  targetLongitude,
  strategyMode,
  routeStartX,
  routeStartY,
  routeTargetX,
  routeTargetY,
  landingRadius,
  shotType,
  onSourceRefChange,
  onDistanceChange,
  onLieChange,
  onCurrentLatitudeChange,
  onCurrentLongitudeChange,
  onTargetLatitudeChange,
  onTargetLongitudeChange,
  onStrategyModeChange,
  onRouteStartXChange,
  onRouteStartYChange,
  onRouteTargetXChange,
  onRouteTargetYChange,
  onLandingRadiusChange,
  onLoadCaddieContext,
}: {
  state: CaddieContextLoadState
  sourceRef: string
  distance: string
  lie: string
  currentLatitude: string
  currentLongitude: string
  targetLatitude: string
  targetLongitude: string
  strategyMode: string
  routeStartX: string
  routeStartY: string
  routeTargetX: string
  routeTargetY: string
  landingRadius: string
  shotType: CaddieShotType
  onSourceRefChange: (value: string) => void
  onDistanceChange: (value: string) => void
  onLieChange: (value: string) => void
  onCurrentLatitudeChange: (value: string) => void
  onCurrentLongitudeChange: (value: string) => void
  onTargetLatitudeChange: (value: string) => void
  onTargetLongitudeChange: (value: string) => void
  onStrategyModeChange: (value: string) => void
  onRouteStartXChange: (value: string) => void
  onRouteStartYChange: (value: string) => void
  onRouteTargetXChange: (value: string) => void
  onRouteTargetYChange: (value: string) => void
  onLandingRadiusChange: (value: string) => void
  onLoadCaddieContext?: (params: CaddieContextParams) => void
}) {
  const loadedContext = state.status === 'ready' ? state.data.context : null
  const globalId = loadedContext && typeof loadedContext.globalId === 'number' ? loadedContext.globalId : null
  const localHole = loadedContext && typeof loadedContext.localHole === 'number' ? loadedContext.localHole : null
  const historicalIssues = recordRows(loadedContext?.historicalHoleIssues)
  const manualNotes = recordRows(loadedContext?.manualNotes)
  return (
    <section className="caddie-context-panel" aria-label="Caddie context">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">History / geometry context</p>
          <h2>Caddie Context</h2>
          <p>Load a source-bound context before requesting a caddie plan.</p>
        </div>
        {state.status === 'loading' ? <span className="confidence-pill medium">loading</span> : null}
        {state.status === 'error' ? <span className="confidence-pill low">error</span> : null}
      </div>
      <div className="caddie-context-controls">
        <label htmlFor="caddie-source-ref">Source ref</label>
        <input id="caddie-source-ref" value={sourceRef} onChange={(event) => onSourceRefChange(event.target.value)} />
        <label htmlFor="caddie-distance">Distance</label>
        <input id="caddie-distance" inputMode="decimal" value={distance} onChange={(event) => onDistanceChange(event.target.value)} />
        <label htmlFor="caddie-lie">Lie</label>
        <input id="caddie-lie" value={lie} onChange={(event) => onLieChange(event.target.value)} />
        <label htmlFor="caddie-current-latitude">Current latitude</label>
        <input
          id="caddie-current-latitude"
          inputMode="decimal"
          value={currentLatitude}
          onChange={(event) => onCurrentLatitudeChange(event.target.value)}
        />
        <label htmlFor="caddie-current-longitude">Current longitude</label>
        <input
          id="caddie-current-longitude"
          inputMode="decimal"
          value={currentLongitude}
          onChange={(event) => onCurrentLongitudeChange(event.target.value)}
        />
        <label htmlFor="caddie-target-latitude">Target latitude</label>
        <input
          id="caddie-target-latitude"
          inputMode="decimal"
          value={targetLatitude}
          onChange={(event) => onTargetLatitudeChange(event.target.value)}
        />
        <label htmlFor="caddie-target-longitude">Target longitude</label>
        <input
          id="caddie-target-longitude"
          inputMode="decimal"
          value={targetLongitude}
          onChange={(event) => onTargetLongitudeChange(event.target.value)}
        />
        <label htmlFor="caddie-strategy-mode">Strategy mode</label>
        <select id="caddie-strategy-mode" value={strategyMode} onChange={(event) => onStrategyModeChange(event.target.value)}>
          <option value="">Stock mode</option>
          <option value="protect_score">Protect score</option>
          <option value="attack">Attack</option>
        </select>
        <label htmlFor="caddie-route-start-x">Route start X</label>
        <input
          id="caddie-route-start-x"
          inputMode="decimal"
          value={routeStartX}
          onChange={(event) => onRouteStartXChange(event.target.value)}
        />
        <label htmlFor="caddie-route-start-y">Route start Y</label>
        <input
          id="caddie-route-start-y"
          inputMode="decimal"
          value={routeStartY}
          onChange={(event) => onRouteStartYChange(event.target.value)}
        />
        <label htmlFor="caddie-route-target-x">Route target X</label>
        <input
          id="caddie-route-target-x"
          inputMode="decimal"
          value={routeTargetX}
          onChange={(event) => onRouteTargetXChange(event.target.value)}
        />
        <label htmlFor="caddie-route-target-y">Route target Y</label>
        <input
          id="caddie-route-target-y"
          inputMode="decimal"
          value={routeTargetY}
          onChange={(event) => onRouteTargetYChange(event.target.value)}
        />
        <label htmlFor="caddie-landing-radius">Landing radius</label>
        <input
          id="caddie-landing-radius"
          inputMode="decimal"
          value={landingRadius}
          onChange={(event) => onLandingRadiusChange(event.target.value)}
        />
        <button
          type="button"
          onClick={() =>
            onLoadCaddieContext?.(buildContextLoadParams({
              sourceRef,
              shotType,
              distance,
              lie,
              currentLatitude,
              currentLongitude,
              targetLatitude,
              targetLongitude,
              strategyMode,
              routeStartX,
              routeStartY,
              routeTargetX,
              routeTargetY,
              landingRadius,
            }))
          }
        >
          Load caddie context
        </button>
      </div>
      {state.status === 'error' ? <p className="media-context-error">{state.message}</p> : null}
      {state.status === 'ready' ? (
        <div className="caddie-context-grid">
          <section aria-label="Loaded caddie facts">
            <h3>Loaded Facts</h3>
            <div className="report-row">
              <strong>source</strong>
              <span>{String(loadedContext?.source ?? '-')}</span>
            </div>
            <div className="report-row">
              <strong>hole</strong>
              <span>{globalId !== null && localHole !== null ? `${globalId} H${localHole}` : '-'}</span>
            </div>
            <div className="report-row">
              <strong>clubs</strong>
              <span>{Object.keys((loadedContext?.clubProfiles as Record<string, unknown> | undefined) ?? {}).length}</span>
            </div>
          </section>
          {historicalIssues.length ? <ContextRows title="Historical Hole Issues" rows={historicalIssues} /> : null}
          {manualNotes.length ? <ContextRows title="Manual Notes" rows={manualNotes} /> : null}
          <ContextRows title="Context Evidence" rows={state.data.evidence} />
          <ContextRows title="Context Missing Data" rows={state.data.missingData} />
        </div>
      ) : null}
    </section>
  )
}

function buildContextLoadParams({
  sourceRef,
  shotType,
  distance,
  lie,
  currentLatitude,
  currentLongitude,
  targetLatitude,
  targetLongitude,
  strategyMode,
  routeStartX,
  routeStartY,
  routeTargetX,
  routeTargetY,
  landingRadius,
}: {
  sourceRef: string
  shotType: CaddieShotType
  distance: string
  lie: string
  currentLatitude: string
  currentLongitude: string
  targetLatitude: string
  targetLongitude: string
  strategyMode: string
  routeStartX: string
  routeStartY: string
  routeTargetX: string
  routeTargetY: string
  landingRadius: string
}): CaddieContextParams {
  const params: CaddieContextParams = { sourceRef, shotType, capturedAt: new Date().toISOString() }
  const distanceToPinM = numericInput(distance)
  const liveCurrentLatitude = numericInput(currentLatitude)
  const liveCurrentLongitude = numericInput(currentLongitude)
  const liveTargetLatitude = numericInput(targetLatitude)
  const liveTargetLongitude = numericInput(targetLongitude)
  const startX = numericInput(routeStartX)
  const startY = numericInput(routeStartY)
  const targetX = numericInput(routeTargetX)
  const targetY = numericInput(routeTargetY)
  const landingRadiusM = numericInput(landingRadius)
  if (distanceToPinM !== undefined) params.distanceToPinM = distanceToPinM
  if (lie.trim()) params.lie = lie
  if (liveCurrentLatitude !== undefined) params.currentLatitude = liveCurrentLatitude
  if (liveCurrentLongitude !== undefined) params.currentLongitude = liveCurrentLongitude
  if (liveTargetLatitude !== undefined) params.targetLatitude = liveTargetLatitude
  if (liveTargetLongitude !== undefined) params.targetLongitude = liveTargetLongitude
  if (strategyMode.trim()) params.strategyMode = strategyMode
  if (startX !== undefined && startY !== undefined && targetX !== undefined && targetY !== undefined) {
    params.startX = startX
    params.startY = startY
    params.targetX = targetX
    params.targetY = targetY
    if (landingRadiusM !== undefined) params.landingRadiusM = landingRadiusM
  }
  return params
}

function WeatherContextPanel({ state }: { state: WeatherLoadState }) {
  if (state.status === 'loading') {
    return (
      <section className="weather-context-panel" aria-label="Weather context">
        <h2>Loading weather</h2>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="weather-context-panel" aria-label="Weather context">
        <h2>Weather unavailable</h2>
        <p>{state.message}</p>
      </section>
    )
  }

  if (state.status === 'idle') {
    return (
      <section className="weather-context-panel" aria-label="Weather context">
        <h2>Weather Context</h2>
        <p>No weather snapshot loaded.</p>
      </section>
    )
  }

  return (
    <section className="weather-context-panel" aria-label="Weather context">
      <div>
        <p className="eyebrow">{state.data.source}</p>
        <h2>Weather Context</h2>
      </div>
      <div className="weather-context-facts">
        <span>{state.data.windSpeedMps ?? '-'} m/s</span>
        <span>{state.data.windDirectionDeg ?? '-'} deg</span>
        <span>{state.data.temperatureC ?? '-'} C</span>
        <span>{state.data.confidence} confidence</span>
      </div>
    </section>
  )
}

function DecisionDetail({
  state,
  auditState,
  onCreateAudit,
  onSelectRef,
}: {
  state: CaddiePageProps['decisionState']
  auditState: AuditState
  onCreateAudit?: (decision: CaddieDecisionResponse, actualShot: Record<string, unknown>) => void
  onSelectRef: (sourceRef: string) => void
}) {
  if (state.status === 'loading') {
    return (
      <section className="decision-detail" aria-label="Caddie decision">
        <h2>Loading caddie plan</h2>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="decision-detail" aria-label="Caddie decision">
        <h2>Caddie unavailable</h2>
        <p>{state.message}</p>
      </section>
    )
  }

  if (state.status === 'idle') {
    return (
      <section className="decision-detail" aria-label="Caddie decision">
        <h2>No caddie plan loaded</h2>
        <p>Request a plan to inspect options and evidence.</p>
      </section>
    )
  }

  const decision = state.data
  const confidence = String(decision.confidence.level ?? decision.confidence.state ?? 'unknown')
  return (
    <section className="decision-detail" aria-label="Caddie decision">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">{decision.phase}</p>
          <h2>{decision.selectedOptionId ?? 'No selected plan'}</h2>
        </div>
        <span className={`confidence-pill ${confidence}`}>{confidence} confidence</span>
      </div>

      <div className="decision-options">
        {decision.options.map((option) => {
          const id = String(option.id ?? option.label ?? 'option')
          return (
            <article className="decision-option" key={id}>
              <div>
                <h3>{String(option.label ?? id)}</h3>
                {decision.selectedOptionId === id ? <span className="selected-pill">selected</span> : null}
              </div>
              <strong>{optionClubLabel(option)}</strong>
              <p>{formatOptionMeta(option)}</p>
              <OptionQualityChips option={option} onSelectRef={onSelectRef} />
            </article>
          )
        })}
      </div>

      <DecisionAcceptableMiss decision={decision} onSelectRef={onSelectRef} />
      <DecisionSequences sequences={decision.sequences ?? []} selectedSequence={decision.selectedSequence ?? null} onSelectRef={onSelectRef} />
      <DecisionExplanation explanation={decision.explanation} onSelectRef={onSelectRef} />

      <div className="report-evidence-grid">
        <EvidenceList title="Evidence" rows={decision.evidence} />
        <EvidenceList title="Missing Data" rows={decision.missingData} />
        <EvidenceList title="Avoid Zones" rows={decision.avoidZones} />
        <EvidenceList title="Audit" rows={decision.auditCriteria} />
      </div>
      {onCreateAudit ? (
        <DecisionAuditPanel
          decision={decision}
          state={auditState}
          onCreateAudit={(actualShot) => onCreateAudit(decision, actualShot)}
          onSelectRef={onSelectRef}
        />
      ) : null}
    </section>
  )
}

function DecisionExplanation({
  explanation,
  onSelectRef,
}: {
  explanation: unknown
  onSelectRef: (sourceRef: string) => void
}) {
  const row = recordFrom(explanation)
  if (!Object.keys(row).length) return null

  const provider = [stringValue(row.provider), stringValue(row.model)].filter(Boolean).join(' / ') || 'unknown provider'
  const confidence = stringValue(row.confidence) || 'unknown'
  const factBinding = recordFrom(row.factBinding)
  const bindingState = stringValue(factBinding.state) || 'bound'
  const facts = recordRows(row.factsUsed)
  const missingData = recordRows(row.missingData)
  const unsupportedClaims = recordRows(row.unsupportedClaims)
  const sourceRefs = explanationSourceRefs(row)
  const narrative = stringValue(row.narrative)

  return (
    <section className="decision-explanation" aria-label="Decision explanation">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">Fact-bound AI</p>
          <h3>Decision Explanation</h3>
        </div>
        <span className={`confidence-pill ${confidence}`}>{confidence} explanation confidence</span>
      </div>
      <div className="decision-explanation-identity">
        <span className="fact-chip muted">provider</span>
        <span className="fact-chip">{provider}</span>
        <span className="fact-chip muted">{`${bindingState} binding`}</span>
        <SourceRefs refs={sourceRefs} onSelectRef={onSelectRef} />
      </div>
      <div className="decision-explanation-grid">
        <ExplanationRows title="Facts" rows={facts} onSelectRef={onSelectRef} />
        <ExplanationRows title="Missing Data" rows={missingData} onSelectRef={onSelectRef} />
        <ExplanationRows title="Unsupported Claims" rows={unsupportedClaims} onSelectRef={onSelectRef} />
      </div>
      {narrative ? <p className="decision-explanation-narrative">{narrative}</p> : null}
    </section>
  )
}

function ExplanationRows({
  title,
  rows,
  onSelectRef,
}: {
  title: string
  rows: Array<Record<string, unknown>>
  onSelectRef: (sourceRef: string) => void
}) {
  return (
    <section aria-label={`Decision explanation ${title.toLowerCase()}`}>
      <h4>{title}</h4>
      {rows.length ? (
        rows.map((row, index) => (
          <div className="report-row" key={`${String(row.label ?? row.category ?? title)}-${index}`}>
            <div className="report-row-main">
              <strong>{String(row.label ?? row.category ?? 'item')}</strong>
              <span>{explanationRowText(row)}</span>
            </div>
            <SourceRefs refs={rowSourceRefs(row)} onSelectRef={onSelectRef} />
          </div>
        ))
      ) : (
        <p>None</p>
      )}
    </section>
  )
}

function DecisionSequences({
  sequences,
  selectedSequence,
  onSelectRef,
}: {
  sequences: Array<Record<string, unknown>>
  selectedSequence: Record<string, unknown> | null
  onSelectRef: (sourceRef: string) => void
}) {
  if (!sequences.length) return null
  const selectedId = selectedSequence ? String(selectedSequence.id ?? '') : ''
  return (
    <section className="decision-sequences" aria-label="Decision club sequences">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">Route sequencing</p>
          <h3>Club Sequences</h3>
        </div>
      </div>
      <div className="decision-sequence-grid">
        {sequences.map((sequence) => {
          const id = String(sequence.id ?? sequence.label ?? 'sequence')
          const isSelected = id === selectedId
          return (
            <article className={`decision-sequence ${isSelected ? 'is-selected' : ''}`} key={id}>
              <div>
                <strong>{String(sequence.label ?? '-')}</strong>
                {isSelected ? <span className="selected-pill">selected</span> : null}
              </div>
              <p>{formatSequenceMeta(sequence)}</p>
              <SequenceQualityChips sequence={sequence} onSelectRef={onSelectRef} />
              <SequenceStepList steps={recordRows(sequence.clubs)} onSelectRef={onSelectRef} />
            </article>
          )
        })}
      </div>
    </section>
  )
}

function SequenceQualityChips({
  sequence,
  onSelectRef,
}: {
  sequence: Record<string, unknown>
  onSelectRef: (sourceRef: string) => void
}) {
  const coverage = recordFrom(sequence.coverage)
  const ready = coverage.ready
  const total = coverage.total
  const confidence = stringValue(sequence.confidence)
  const refs = stringRows(sequence.sourceRefs)
  if (ready === undefined && total === undefined && !confidence && refs.length === 0) return null

  return (
    <div className="decision-option-chips">
      {ready !== undefined || total !== undefined ? (
        <span className="fact-chip muted">
          coverage {String(ready ?? '-')}/{String(total ?? '-')}
        </span>
      ) : null}
      {confidence ? <span className={`fact-chip confidence-${confidence}`}>{confidence} sequence confidence</span> : null}
      <SourceRefs refs={refs} maxVisible={3} onSelectRef={onSelectRef} />
    </div>
  )
}

function SequenceStepList({
  steps,
  onSelectRef,
}: {
  steps: Array<Record<string, unknown>>
  onSelectRef: (sourceRef: string) => void
}) {
  if (!steps.length) return null

  return (
    <div className="decision-sequence-steps" aria-label="Sequence shot steps">
      {steps.map((step, index) => {
        const club = stringValue(step.clubName) || '-'
        const role = stringValue(step.role) || `shot ${index + 1}`
        const confidence = stringValue(step.confidence)
        const refs = stringRows(step.sourceRefs)
        return (
          <div className="decision-sequence-step" key={`${role}-${club}-${index}`}>
            <div>
              <strong>{`${role} ${club}`}</strong>
              <span>{sequenceStepLabel(step)}</span>
            </div>
            <div className="decision-option-chips">
              {step.sampleSize !== undefined ? <span className="fact-chip muted">{String(step.sampleSize)} samples</span> : null}
              {confidence ? <span className={`fact-chip confidence-${confidence}`}>{confidence}</span> : null}
              <SourceRefs refs={refs} maxVisible={1} onSelectRef={onSelectRef} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function DecisionAcceptableMiss({
  decision,
  onSelectRef,
}: {
  decision: CaddieDecisionResponse
  onSelectRef: (sourceRef: string) => void
}) {
  const miss = recordFrom(decision.acceptableMiss)
  if (!Object.keys(miss).length) return null

  const direction = stringValue(miss.direction) || stringValue(miss.side) || 'unknown'
  const selectedOptionId = stringValue(miss.selectedOptionId) || stringValue(decision.selectedOptionId) || 'unknown option'
  const avoidRiskKinds = stringRows(miss.avoidRiskKinds)
  const rationale = stringValue(miss.rationale) || stringValue(miss.reason)
  const refs = uniqueStrings([...rowSourceRefs(miss), ...stringRows(decision.evidenceRefs), ...(decision.sourceRef ? [decision.sourceRef] : [])])

  return (
    <section className="decision-acceptable-miss" aria-label="Decision acceptable miss">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">Target discipline</p>
          <h3>Acceptable Miss</h3>
        </div>
        <span className="fact-chip muted">{selectedOptionId}</span>
      </div>
      <div className="decision-miss-summary">
        <strong>{formatMissDirection(direction)}</strong>
        <span>{rationale || 'No rationale supplied.'}</span>
      </div>
      <div className="decision-option-chips">
        {avoidRiskKinds.length ? <span className="fact-chip muted">avoid {avoidRiskKinds.join(', ')}</span> : null}
        <SourceRefs refs={refs} maxVisible={3} onSelectRef={onSelectRef} />
      </div>
    </section>
  )
}

function OptionQualityChips({
  option,
  onSelectRef,
}: {
  option: Record<string, unknown>
  onSelectRef: (sourceRef: string) => void
}) {
  const sampleSize = optionClubSampleSize(option)
  const coverage = recordFrom(option.coverage)
  const ready = coverage.ready
  const total = coverage.total
  const confidence = stringValue(option.confidence)
  const missingCount = recordRows(option.missingData).length
  const historyAdjustment = recordFrom(option.historyAdjustment)
  const historyDeltaRaw = historyAdjustment.riskScoreDelta
  const historyDelta =
    typeof historyDeltaRaw === 'number' && Number.isFinite(historyDeltaRaw)
      ? historyDeltaRaw
      : typeof historyDeltaRaw === 'string' && Number.isFinite(Number(historyDeltaRaw))
        ? Number(historyDeltaRaw)
        : null
  const historyText = historyDelta && historyDelta !== 0 ? `history ${historyDelta > 0 ? '+' : ''}${historyDelta} risk` : null
  const refs = uniqueStrings([...stringRows(option.sourceRefs), ...stringRows(historyAdjustment.sourceRefs)])
  if (sampleSize === null && ready === undefined && !confidence && missingCount === 0 && !historyText && refs.length === 0) return null

  return (
    <div className="decision-option-chips">
      {sampleSize !== null ? <span className="fact-chip muted">sample {sampleSize}</span> : null}
      {ready !== undefined || total !== undefined ? (
        <span className="fact-chip muted">
          coverage {String(ready ?? '-')}/{String(total ?? '-')}
        </span>
      ) : null}
      {confidence ? <span className={`fact-chip confidence-${confidence}`}>{confidence} option confidence</span> : null}
      {historyText ? <span className="fact-chip muted">{historyText}</span> : null}
      {missingCount ? <span className="fact-chip muted">missing {missingCount}</span> : null}
      <SourceRefs refs={refs} maxVisible={3} onSelectRef={onSelectRef} />
    </div>
  )
}

function DecisionAuditPanel({
  decision,
  state,
  onCreateAudit,
  onSelectRef,
}: {
  decision: CaddieDecisionResponse
  state: AuditState
  onCreateAudit: (actualShot: Record<string, unknown>) => void
  onSelectRef: (sourceRef: string) => void
}) {
  const selected = decision.selectedOption ?? decision.selected ?? {}
  const defaultClub = optionClubLabel(selected)
  const defaultCarry = selected.carry_m ?? selected.carryM ?? decision.context.distanceToPin_m ?? ''
  const [actualClub, setActualClub] = useState(defaultClub)
  const [actualCarry, setActualCarry] = useState(String(defaultCarry))
  const [resultLie, setResultLie] = useState('green')
  const actualCarryMeters = numericInput(actualCarry)
  const canAudit = actualClub.trim().length > 0 && actualCarryMeters !== undefined
  const auditControls = (
    <div className="decision-audit-controls">
      <label htmlFor="actual-club">Actual club</label>
      <input id="actual-club" value={actualClub} onChange={(event) => setActualClub(event.target.value)} />
      <label htmlFor="actual-carry">Actual carry (m)</label>
      <input id="actual-carry" inputMode="decimal" value={actualCarry} onChange={(event) => setActualCarry(event.target.value)} />
      <label htmlFor="result-lie">Result lie</label>
      <select id="result-lie" value={resultLie} onChange={(event) => setResultLie(event.target.value)}>
        <option value="green">Green</option>
        <option value="fringe">Fringe</option>
        <option value="fairway">Fairway</option>
        <option value="rough">Rough</option>
        <option value="bunker">Bunker</option>
        <option value="water">Water</option>
        <option value="penalty">Penalty</option>
      </select>
      <button type="button" disabled={!canAudit} onClick={() => onCreateAudit(buildActualShot(actualClub, actualCarryMeters ?? 0, resultLie))}>
        Audit outcome
      </button>
    </div>
  )

  if (state.status === 'loading') {
    return (
      <section className="decision-outcome-audit" aria-label="Decision outcome audit">
        <div className="report-title-row">
          <div>
            <p className="eyebrow">Outcome audit</p>
            <h3>Auditing outcome</h3>
          </div>
        </div>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="decision-outcome-audit" aria-label="Decision outcome audit">
        <div className="report-title-row">
          <div>
            <p className="eyebrow">Outcome audit</p>
            <h3>Audit unavailable</h3>
            <p>{state.message}</p>
          </div>
        </div>
        {auditControls}
      </section>
    )
  }

  const record = state.status === 'ready' ? state.data : null
  const audit = record?.audit ?? null
  const classification = audit ? String(audit.classification ?? 'unknown') : null
  const planned = audit ? String(audit.plannedOptionId ?? '-') : '-'
  const actual = audit ? String(audit.actualOptionId ?? '-') : '-'
  const executionMatch = recordFrom(audit?.executionMatch)
  const result = recordFrom(audit?.result)
  const actualShotRefs = stringRows(record?.actualShotRefs ?? audit?.actualShotRefs)
  const evidenceRefs = stringRows(record?.evidenceRefs ?? audit?.evidenceRefs)
  const suggestion = auditSuggestion(audit?.modelUpdateSuggestion)

  return (
    <section className="decision-outcome-audit" aria-label="Decision outcome audit">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">Outcome audit</p>
          <h3>{audit ? 'Latest decision audit' : 'No outcome audit yet'}</h3>
          <p>{audit ? `planned ${planned} -> actual ${actual}` : 'Compare the selected plan with the first actual shot.'}</p>
        </div>
      </div>
      {auditControls}
      {classification ? <span className={`audit-classification audit-${classification}`}>{classification}</span> : null}
      {audit ? (
        <div className="decision-audit-summary">
          <div className="report-row">
            <strong>actual shot</strong>
            <SourceRefs refs={actualShotRefs} onSelectRef={onSelectRef} />
          </div>
          <div className="report-row">
            <strong>evidence</strong>
            <SourceRefs refs={evidenceRefs} onSelectRef={onSelectRef} />
          </div>
          <div className="decision-audit-facts" aria-label="Decision audit execution facts">
            <span className="fact-chip">club match {booleanLabel(executionMatch.clubMatch)}</span>
            <span className="fact-chip">distance {metersLabel(executionMatch.distanceDelta_m)}</span>
            <span className="fact-chip">risk {booleanLabel(executionMatch.riskTriggered)}</span>
          </div>
          {Object.keys(result).length ? (
            <p className="decision-audit-result">
              {[
                result.clubName ? String(result.clubName) : null,
                result.meters !== undefined && result.meters !== null ? `${String(result.meters)}m` : null,
                result.surface ? String(result.surface) : null,
              ]
                .filter(Boolean)
                .join(' - ')}
            </p>
          ) : null}
          {suggestion ? <p className="decision-audit-suggestion">{suggestion}</p> : null}
        </div>
      ) : null}
    </section>
  )
}

function buildActualShot(clubName: string, meters: number, resultLie: string): Record<string, unknown> {
  return {
    shotOrder: 1,
    clubName: clubName.trim(),
    meters,
    end: { lie: resultLie, feature: { surface: { kind: resultLie }, nearRisks: [] } },
  }
}

function EvidenceList({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  return (
    <section aria-label={`Decision ${title.toLowerCase()}`}>
      <h3>{title}</h3>
      {rows.length ? (
        rows.map((row, index) => (
          <div className="report-row" key={`${String(row.label ?? row.id ?? row.kind ?? title)}-${index}`}>
            <strong>{String(row.label ?? row.id ?? row.kind ?? 'item')}</strong>
            <span>{String(row.value ?? row.reason ?? row.text ?? row.distance_m ?? row.carryToClear_m ?? '')}</span>
          </div>
        ))
      ) : (
        <p>None</p>
      )}
    </section>
  )
}

function ContextRows({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  return (
    <section aria-label={title}>
      <h3>{title}</h3>
      {rows.length ? (
        rows.map((row, index) => (
          <div className="report-row" key={`${title}-${index}`}>
            <strong>{String(row.label ?? row.issue ?? row.kind ?? row.id ?? 'item')}</strong>
            <span>{String(row.value ?? row.note ?? row.reason ?? row.ref ?? row.count ?? '')}</span>
          </div>
        ))
      ) : (
        <p>None</p>
      )}
    </section>
  )
}

function recordRows(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((row): row is Record<string, unknown> => row !== null && typeof row === 'object') : []
}

function contextStateMatchesSourceRef(state: CaddieContextLoadState, sourceRef: string): boolean {
  if (state.status !== 'ready') return false
  return normalizeSourceRef(state.data.sourceRef) === normalizeSourceRef(sourceRef) || normalizeSourceRef(state.data.context?.sourceRef) === normalizeSourceRef(sourceRef)
}

function normalizeSourceRef(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function recordFrom(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function stringRows(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item).trim()).filter(Boolean) : []
}

function stringValue(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value.trim() : ''
}

function explanationSourceRefs(row: Record<string, unknown>): string[] {
  const refs = new Set<string>(rowSourceRefs(row))
  for (const item of [...recordRows(row.factsUsed), ...recordRows(row.missingData), ...recordRows(row.unsupportedClaims)]) {
    for (const ref of rowSourceRefs(item)) refs.add(ref)
  }
  return Array.from(refs)
}

function rowSourceRefs(row: Record<string, unknown>): string[] {
  return uniqueStrings([
    ...stringRows(row.sourceRefs),
    ...stringRows(row.refs),
    ...stringRows(row.evidenceRefs),
    ...stringRows(row.missingDataRefs),
  ])
}

function uniqueStrings(rows: string[]): string[] {
  return rows.filter((row, index, refs) => row && refs.indexOf(row) === index)
}

function formatMissDirection(value: string): string {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function explanationRowText(row: Record<string, unknown>): string {
  for (const key of ['claim', 'reason', 'value', 'state']) {
    const value = row[key]
    const formatted = formatExplanationValue(value)
    if (formatted) return formatted
  }
  return '-'
}

function formatExplanationValue(value: unknown): string {
  if (value === undefined || value === null || value === '') return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    return value.map(formatExplanationValue).filter(Boolean).join(', ')
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const formatted = formatExplanationValue(item)
        return formatted ? `${key} ${formatted}` : ''
      })
      .filter(Boolean)
      .join(', ')
  }
  return String(value)
}

function booleanLabel(value: unknown): string {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  return 'unknown'
}

function metersLabel(value: unknown): string {
  if (value === undefined || value === null || value === '') return 'unknown'
  return `${String(value)}m`
}

function auditSuggestion(value: unknown): string | null {
  if (typeof value === 'string') return value
  const row = recordFrom(value)
  const suggestion = row.text ?? row.suggestion ?? row.reason
  return typeof suggestion === 'string' && suggestion.trim() ? suggestion : null
}

function MediaContextPanel({
  state,
  onLoadMediaContext,
  onAttachMedia,
  onAnalyzeMedia,
  onRedactMedia,
  onConfirmVisionFinding,
}: {
  state: MediaContextState
  onLoadMediaContext?: (target: { targetType: MediaTargetType; targetId: string }) => void
  onAttachMedia?: (request: MediaCreateRequest) => void | Promise<void>
  onAnalyzeMedia?: (mediaId: string) => void
  onRedactMedia?: (mediaId: string) => void
  onConfirmVisionFinding?: (findingId: string, confirmationState: Extract<VisionConfirmationState, 'manual_confirmed' | 'rejected'>) => void
}) {
  const [targetType, setTargetType] = useState<MediaTargetType>('shot')
  const [targetId, setTargetId] = useState('fixture-round:4:approach')
  const [mediaKind, setMediaKind] = useState<MediaKind>('photo')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

  async function handleAttachMedia() {
    if (!selectedFile || !onAttachMedia) return
    setUploadError(null)
    try {
      await onAttachMedia({
        targetType,
        targetId,
        mediaKind,
        fileName: selectedFile.name,
        contentBase64: await fileToBase64(selectedFile),
        capturedAt: new Date().toISOString(),
        privacyState: 'private_local',
      })
    } catch (error: unknown) {
      setUploadError(error instanceof Error ? error.message : 'Media upload failed')
    }
  }

  const media = state.status === 'ready' ? state.media : []
  const findings = state.status === 'ready' ? state.findings : []

  return (
    <section className="media-context-panel" aria-label="Media context">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">Photo / video evidence</p>
          <h2>Media Context</h2>
          <p>Attach visual context as evidence with confidence before it influences caddie decisions.</p>
        </div>
        {state.status === 'loading' ? <span className="confidence-pill medium">loading</span> : null}
        {state.status === 'error' ? <span className="confidence-pill low">error</span> : null}
      </div>

      <div className="media-context-controls">
        <label htmlFor="media-target-type">Target type</label>
        <select
          id="media-target-type"
          value={targetType}
          onChange={(event) => setTargetType(event.target.value as MediaTargetType)}
        >
          <option value="shot">Shot</option>
          <option value="hole">Hole</option>
          <option value="round">Round</option>
        </select>

        <label htmlFor="media-target-id">Target ID</label>
        <input id="media-target-id" value={targetId} onChange={(event) => setTargetId(event.target.value)} />

        <label htmlFor="media-kind">Media kind</label>
        <select id="media-kind" value={mediaKind} onChange={(event) => setMediaKind(event.target.value as MediaKind)}>
          <option value="photo">Photo</option>
          <option value="video">Video</option>
        </select>

        <label htmlFor="media-file">Media file</label>
        <input
          id="media-file"
          type="file"
          accept="image/*,video/*"
          onChange={(event) => setSelectedFile(event.currentTarget.files?.[0] ?? null)}
        />

        <button type="button" onClick={() => onLoadMediaContext?.({ targetType, targetId })}>
          Load media context
        </button>
        <button type="button" onClick={() => void handleAttachMedia()} disabled={!selectedFile || !onAttachMedia}>
          Attach media
        </button>
      </div>

      {state.status === 'error' ? <p className="media-context-error">{state.message}</p> : null}
      {uploadError ? <p className="media-context-error">{uploadError}</p> : null}

      <div className="media-context-grid">
        <section aria-label="Attached media">
          <h3>Attached Media</h3>
          {media.length ? (
            media.map((item) => (
              <article className="media-context-row" key={item.id}>
                <div>
                  <strong>{item.mediaKind}</strong>
                  <span>{item.localPath}</span>
                </div>
                {onAnalyzeMedia ? (
                  <button
                    type="button"
                    aria-label={`Analyze media ${item.id}`}
                    onClick={() => onAnalyzeMedia(item.id)}
                    disabled={item.privacyState === 'redacted'}
                  >
                    Analyze
                  </button>
                ) : null}
                {onRedactMedia && item.privacyState !== 'redacted' ? (
                  <button type="button" aria-label={`Redact media ${item.id}`} onClick={() => onRedactMedia(item.id)}>
                    Redact
                  </button>
                ) : null}
              </article>
            ))
          ) : (
            <p>No media attached for this target.</p>
          )}
        </section>

        <section aria-label="Vision findings">
          <h3>Vision Findings</h3>
          {findings.length ? (
            findings.map((finding) => (
              <article className="media-context-row" key={finding.id}>
                <div>
                  <strong>{finding.findingType}</strong>
                  <span>{finding.evidenceText}</span>
                  <span>{finding.confirmationState ?? 'unconfirmed'}</span>
                  {finding.confirmedBy ? <span>confirmed by {finding.confirmedBy}</span> : null}
                </div>
                <span className={`confidence-pill ${finding.confidence}`}>{finding.confidence}</span>
                {onConfirmVisionFinding ? (
                  <div className="media-context-actions">
                    <button
                      type="button"
                      aria-label={`Confirm finding ${finding.id}`}
                      onClick={() => onConfirmVisionFinding(finding.id, 'manual_confirmed')}
                      disabled={finding.confirmationState === 'manual_confirmed'}
                    >
                      Confirm
                    </button>
                    <button
                      type="button"
                      aria-label={`Reject finding ${finding.id}`}
                      onClick={() => onConfirmVisionFinding(finding.id, 'rejected')}
                      disabled={finding.confirmationState === 'rejected'}
                    >
                      Reject
                    </button>
                  </div>
                ) : null}
              </article>
            ))
          ) : (
            <p>No analyzed findings yet.</p>
          )}
        </section>
      </div>
    </section>
  )
}

function buildDecisionRequest(
  shotType: CaddieShotType,
  contextState: CaddieContextLoadState,
  weatherSnapshot: WeatherSnapshotResponse | null,
  visionFindings: VisionFindingRecord[] = [],
): CaddieDecisionRequest {
  const baseContext =
    contextState.status === 'ready'
      ? contextState.data.context
      : {
          shotType,
          missingData: [{ label: 'caddie_context', reason: 'source-bound context has not been loaded' }],
        }
  return {
    shotType,
    context: {
      ...baseContext,
      shotType,
      ...(weatherSnapshot ? { weatherSnapshot } : {}),
      ...(visionFindings.length ? { visionFindings } : {}),
    },
  }
}

function formatSequenceMeta(sequence: Record<string, unknown>): string {
  const strokes = sequence.expectedStrokes
  const remaining = sequence.expectedRemaining_m
  const risk = sequence.riskScore
  const parts = []
  if (strokes !== undefined) parts.push(`${String(strokes)} shots`)
  if (remaining !== undefined) parts.push(`${String(remaining)}m remaining`)
  if (risk !== undefined) parts.push(`risk ${String(risk)}`)
  return parts.join(' - ') || '-'
}

function sequenceStepLabel(step: Record<string, unknown>): string {
  const carry = step.targetCarry_m ?? step.carry_m
  const remaining = step.expectedRemaining_m
  return [
    carry === undefined ? null : `${String(carry)}m carry`,
    remaining === undefined ? null : `${String(remaining)}m left`,
  ]
    .filter(Boolean)
    .join(' - ') || '-'
}

function numericInput(value: string): number | undefined {
  if (!value.trim()) return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  for (let index = 0; index < bytes.length; index += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000))
  }
  return btoa(binary)
}

function optionClubRows(option: Record<string, unknown>): Array<Record<string, unknown>> {
  const recommendation = recordFrom(option.clubRecommendation)
  return recordRows(recommendation.clubs)
}

function optionClubLabel(option: Record<string, unknown>): string {
  const direct = stringValue(option.recommendedClub) || stringValue(option.club)
  if (direct) return direct
  const clubs = optionClubRows(option)
    .map((club) => stringValue(club.clubName) || stringValue(club.name))
    .filter(Boolean)
  return clubs.length ? clubs.slice(0, 2).join(' / ') : '-'
}

function optionClubSampleSize(option: Record<string, unknown>): number | null {
  const first = optionClubRows(option)[0]
  if (!first) return null
  const sample = first.sampleSize
  return typeof sample === 'number' && Number.isFinite(sample) ? sample : null
}

function formatOptionMeta(option: Record<string, unknown>): string {
  const carry = option.carry_m ?? option.carryM ?? option.targetCarryM
  const risk = option.riskScore ?? option.risk
  const scoreImpact = option.scoreImpact && typeof option.scoreImpact === 'object' ? (option.scoreImpact as Record<string, unknown>) : null
  const hazardClearance = option.hazardClearance && typeof option.hazardClearance === 'object' ? (option.hazardClearance as Record<string, unknown>) : null
  const expected = scoreImpact?.expectedStrokes
  const clearance = hazardClearance?.minimumClearance_m
  return [
    carry === undefined ? null : `${String(carry)}m`,
    risk === undefined ? null : `risk ${String(risk)}`,
    expected === undefined ? null : `${String(expected)} exp`,
    clearance === undefined || clearance === null ? null : `${String(clearance)}m clear`,
  ]
    .filter(Boolean)
    .join(' - ')
}
