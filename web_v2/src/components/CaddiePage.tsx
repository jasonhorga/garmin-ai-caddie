import { useEffect, useRef, useState } from 'react'
import { fmtYd } from '../units'
import { phaseZh, confidenceZh, missDirectionZh } from '../zhLabels'
import { useDiagnostics } from '../diagnosticsContext'
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
  WeatherSnapshotParams,
  WeatherSnapshotResponse,
  VisionConfirmationState,
  VisionFindingRecord,
} from '../types'
import { SourceRefs } from './SourceRefs'

const OPTION_LABEL_ZH: Record<string, string> = {
  safe: '稳妥',
  stock: '标准',
  attack: '进攻',
  protect_score: '保守',
  conservative_layup: '保守上道',
  stock_line: '标准路线',
  aggressive_line: '激进路线',
}

function optionLabelZh(id: string): string {
  return OPTION_LABEL_ZH[id] ?? id
}

const HAZARD_KIND_ZH: Record<string, string> = {
  bunker: '沙坑',
  water: '水域',
  ob: 'OB',
  rough: '长草',
}

function hazardKindZh(kind: string): string {
  return HAZARD_KIND_ZH[kind] ?? kind
}

const WIND_CARDINAL_ZH = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']

function windCardinalZh(deg: number): string {
  return WIND_CARDINAL_ZH[Math.round(deg / 45) % 8]
}

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
  onLoadWeather?: (params: WeatherSnapshotParams) => void
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
  const diagnostics = useDiagnostics()
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
  const mediaTarget = mediaTargetForSourceRef(contextSourceRef)
  const weatherSnapshot = weatherState.status === 'ready' ? weatherState.data : null
  const visionFindings = mediaStateMatchesTarget(mediaState, mediaTarget) ? mediaState.findings : []
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
          <p className="eyebrow">决策层</p>
          <h1>智能球童</h1>
          <p>对比保守、标准与进攻方案，结合证据、缺失数据与审计条件。</p>
        </div>
      </div>

      <section className="caddie-control-bar" aria-label="Caddie controls">
        <label htmlFor="shot-type">击球类型</label>
        <select id="shot-type" value={shotType} onChange={(event) => setShotType(event.target.value as CaddieShotType)}>
          {/* 击球类型 wording aligned with LiveSandbox SHOT_TYPE options */}
          <option value="approach">攻果岭</option>
          <option value="tee">开球</option>
          <option value="recovery">救球</option>
        </select>
        {onLoadWeather ? (
          <button
            type="button"
            onClick={() =>
              onLoadWeather(buildWeatherLoadParams({
                sourceRef: contextSourceRef,
                contextState,
                currentLatitude,
                currentLongitude,
                targetLatitude,
                targetLongitude,
              }))
            }
          >
            加载天气
          </button>
        ) : null}
        <button
          type="button"
          disabled={!hasSourceContext}
          onClick={() => onRequestDecision(buildDecisionRequest(shotType, contextState, weatherSnapshot, visionFindings))}
        >
          请求球童方案
        </button>
        {!hasSourceContext ? <span className="caddie-context-required">请先加载球童上下文再请求球场计划。</span> : null}
      </section>

      {onLoadWeather ? <WeatherContextPanel state={weatherState} /> : null}
      {diagnostics ? (
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
      ) : null}
      {diagnostics ? (
        <MediaContextPanel
          key={`${mediaTarget.targetType}:${mediaTarget.targetId}`}
          state={mediaState}
          defaultTarget={mediaTarget}
          onLoadMediaContext={onLoadMediaContext}
          onAttachMedia={onAttachMedia}
          onAnalyzeMedia={onAnalyzeMedia}
          onRedactMedia={onRedactMedia}
          onConfirmVisionFinding={onConfirmVisionFinding}
        />
      ) : null}
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

function buildWeatherLoadParams({
  sourceRef,
  contextState,
  currentLatitude,
  currentLongitude,
  targetLatitude,
  targetLongitude,
}: {
  sourceRef: string
  contextState: CaddieContextLoadState
  currentLatitude: string
  currentLongitude: string
  targetLatitude: string
  targetLongitude: string
}): WeatherSnapshotParams {
  const context = contextState.status === 'ready' ? contextState.data.context : {}
  const roundId = stringValue(context.roundId) || sourceRefRoundId(sourceRef)
  const hole = numberValue(context.hole) ?? numberValue(context.localHole) ?? sourceRefHole(sourceRef)
  const currentLat = numericInput(currentLatitude)
  const currentLon = numericInput(currentLongitude)
  const targetLat = numericInput(targetLatitude)
  const targetLon = numericInput(targetLongitude)
  const contextLocation = recordFrom(context.location)
  const contextCurrent = recordFrom(context.currentLocation)
  const latitude = currentLat ?? targetLat ?? numberValue(contextCurrent.latitude) ?? numberValue(contextLocation.latitude)
  const longitude = currentLon ?? targetLon ?? numberValue(contextCurrent.longitude) ?? numberValue(contextLocation.longitude)
  return {
    source: latitude !== null && longitude !== null ? 'open_meteo' : 'manual',
    persist: true,
    ...(roundId ? { roundId } : {}),
    ...(hole !== null ? { hole } : {}),
    capturedAt: new Date().toISOString(),
    ...(latitude !== null && longitude !== null ? { latitude, longitude } : {}),
  }
}

function sourceRefRoundId(sourceRef: string): string | undefined {
  const [roundId] = sourceRef.split(':')
  return roundId?.trim() || undefined
}

function sourceRefHole(sourceRef: string): number | null {
  const [, hole] = sourceRef.split(':')
  return numberValue(hole)
}

function WeatherContextPanel({ state }: { state: WeatherLoadState }) {
  if (state.status === 'loading') {
    return (
      <section className="weather-context-panel" aria-label="Weather context">
        <h2>天气加载中</h2>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="weather-context-panel" aria-label="Weather context">
        <h2>天气暂不可用</h2>
        <p>{state.message}</p>
      </section>
    )
  }

  if (state.status === 'idle') {
    return (
      <section className="weather-context-panel" aria-label="Weather context">
        <h2>天气</h2>
        <p>暂无天气</p>
      </section>
    )
  }

  const windKph = state.data.windSpeedMps !== undefined && state.data.windSpeedMps !== null
    ? Math.round(Number(state.data.windSpeedMps) * 3.6)
    : null
  const windDir = state.data.windDirectionDeg !== undefined && state.data.windDirectionDeg !== null
    ? windCardinalZh(Number(state.data.windDirectionDeg))
    : null

  return (
    <section className="weather-context-panel" aria-label="Weather context">
      <div>
        <p className="eyebrow">{state.data.source}</p>
        <h2>天气</h2>
      </div>
      <div className="weather-context-facts">
        <span>风 {windKph !== null ? `${windKph} km/h` : '-'}</span>
        <span>{windDir ?? '-'}</span>
        <span>{state.data.temperatureC !== undefined && state.data.temperatureC !== null ? `${state.data.temperatureC}°C` : '-'}</span>
        <span>{confidenceZh(String(state.data.confidence))} 置信度</span>
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
        <h2>球童方案加载中</h2>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="decision-detail" aria-label="Caddie decision">
        <h2>球童方案暂不可用</h2>
        <p>{state.message}</p>
      </section>
    )
  }

  if (state.status === 'idle') {
    return (
      <section className="decision-detail" aria-label="Caddie decision">
        <h2>尚未加载球童方案</h2>
        <p>请求方案以查看选项与依据。</p>
      </section>
    )
  }

  const decision = state.data
  const confidence = String(decision.confidence.level ?? decision.confidence.state ?? 'unknown')
  return (
    <section className="decision-detail" aria-label="Caddie decision">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">{phaseZh(String(decision.phase ?? ''))}</p>
          <h2>{decision.selectedOptionId ? optionLabelZh(String(decision.selectedOptionId)) : '尚无方案'}</h2>
        </div>
        <span className={`confidence-pill ${confidence}`}>{confidenceZh(confidence)} 置信度</span>
      </div>

      <div className="decision-options">
        {decision.options.map((option) => {
          const id = String(option.id ?? option.label ?? 'option')
          return (
            <article className={`decision-option strategy-${id}`} key={id}>
              <div>
                <h3>{optionLabelZh(id)}</h3>
                {decision.selectedOptionId === id ? <span className="selected-pill">已选</span> : null}
              </div>
              <strong>{optionClubLabel(option)}</strong>
              <p>{formatOptionMeta(option)}</p>
              <OptionQualityChips option={option} onSelectRef={onSelectRef} />
            </article>
          )
        })}
      </div>

      <DecisionScoreImpact decision={decision} onSelectRef={onSelectRef} />
      <DecisionAcceptableMiss decision={decision} onSelectRef={onSelectRef} />
      <DecisionSequences sequences={decision.sequences ?? []} selectedSequence={decision.selectedSequence ?? null} onSelectRef={onSelectRef} />
      <DecisionExplanation explanation={decision.explanation} onSelectRef={onSelectRef} />

      <div className="report-evidence-grid">
        <EvidenceList title="证据" rows={decision.evidence} />
        <EvidenceList title="缺失数据" rows={decision.missingData} />
        <AvoidZonesList rows={decision.avoidZones} />
        <EvidenceList title="审计条件" rows={decision.auditCriteria} />
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

function DecisionScoreImpact({
  decision,
  onSelectRef,
}: {
  decision: CaddieDecisionResponse
  onSelectRef: (sourceRef: string) => void
}) {
  const selected = selectedDecisionOption(decision)
  const scoreImpact = recordFrom(selected.scoreImpact)
  if (!Object.keys(scoreImpact).length) return null

  const model = stringValue(scoreImpact.model)
  const expectedStrokes = numberValue(scoreImpact.expectedStrokes)
  const expectedDelta = numberValue(scoreImpact.expectedStrokesDelta)
  const components = recordFrom(scoreImpact.components)
  const componentRows = Object.entries(components)
    .map(([key, value]) => ({ key, value: numberValue(value) }))
    .filter((row): row is { key: string; value: number } => row.value !== null)
  const historyAdjustment = recordFrom(scoreImpact.historyAdjustment)
  const historyFactors = recordRows(historyAdjustment.factors)
  const clubConfidence = recordFrom(scoreImpact.clubConfidence)
  const clubConfidenceReason = stringValue(clubConfidence.reason)
  const refs = uniqueStrings([
    ...rowSourceRefs(historyAdjustment),
    ...historyFactors.flatMap(rowSourceRefs),
    ...rowSourceRefs(recordFrom(scoreImpact.clubSurfaceRisk)),
  ])

  return (
    <section className="decision-score-impact" aria-label="Decision score impact">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">预期结果</p>
          <h3>得分影响</h3>
        </div>
        {model ? <span className="fact-chip muted">{model}</span> : null}
      </div>
      <div className="decision-score-summary">
        {expectedStrokes !== null ? (
          <div>
            <strong>{formatStrokes(expectedStrokes)}</strong>
            <span>预期得杆</span>
          </div>
        ) : null}
        {expectedDelta !== null ? (
          <div>
            <strong>{formatSignedStrokes(expectedDelta)}</strong>
            <span>对比基准</span>
          </div>
        ) : null}
        <SourceRefs refs={refs} maxVisible={3} onSelectRef={onSelectRef} />
      </div>
      {componentRows.length ? (
        <div className="decision-score-components" aria-label="Score impact components">
          {componentRows.map((row) => (
            <span className="fact-chip muted" key={row.key}>
              {missDirectionZh(row.key)} {formatSignedStrokes(row.value)}
            </span>
          ))}
        </div>
      ) : null}
      {historyFactors.length ? (
        <div className="decision-score-factors" aria-label="Score impact history factors">
          {historyFactors.map((factor, index) => (
            <div className="report-row" key={`${String(factor.label ?? 'history')}-${index}`}>
              <div className="report-row-main">
                <strong>{String(factor.label ?? 'history')}</strong>
                <span>{formatSignedStrokes(numberValue(factor.expectedStrokesDelta) ?? 0)}</span>
              </div>
              <SourceRefs refs={rowSourceRefs(factor)} maxVisible={2} onSelectRef={onSelectRef} />
            </div>
          ))}
        </div>
      ) : null}
      {clubConfidenceReason ? <p className="decision-score-note">{clubConfidenceReason}</p> : null}
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
          <p className="eyebrow">事实绑定 AI</p>
          <h3>决策说明</h3>
        </div>
        <span className={`confidence-pill ${confidence}`}>{confidenceZh(confidence)} 置信度</span>
      </div>
      <div className="decision-explanation-identity">
        <span className="fact-chip muted">供应方</span>
        <span className="fact-chip">{provider}</span>
        <span className="fact-chip muted">{`${bindingState} 绑定`}</span>
        <SourceRefs refs={sourceRefs} onSelectRef={onSelectRef} />
      </div>
      <div className="decision-explanation-grid">
        <ExplanationRows title="依据" rows={facts} onSelectRef={onSelectRef} />
        <ExplanationRows title="缺失数据" rows={missingData} onSelectRef={onSelectRef} />
        <ExplanationRows title="无依据判断" rows={unsupportedClaims} onSelectRef={onSelectRef} />
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
        <p>无</p>
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
          <p className="eyebrow">路线排序</p>
          <h3>逐杆序列</h3>
        </div>
      </div>
      <div className="decision-sequence-grid">
        {sequences.map((sequence) => {
          const id = String(sequence.id ?? sequence.label ?? 'sequence')
          const isSelected = id === selectedId
          return (
            <article className={`decision-sequence ${isSelected ? 'is-selected' : ''}`} key={id}>
              <div>
                <strong>{optionLabelZh(String(sequence.label ?? id))}</strong>
                {isSelected ? <span className="selected-pill">已选</span> : null}
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
          覆盖 {String(ready ?? '-')}/{String(total ?? '-')}
        </span>
      ) : null}
      {confidence ? <span className={`fact-chip confidence-${confidence}`}>{confidenceZh(confidence)} 序列置信度</span> : null}
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
        const role = stringValue(step.role) || `第${index + 1}杆`
        const confidence = stringValue(step.confidence)
        const refs = stringRows(step.sourceRefs)
        return (
          <div className="decision-sequence-step" key={`${role}-${club}-${index}`}>
            <div>
              <strong>{`${role} ${club}`}</strong>
              <span>{sequenceStepLabel(step)}</span>
            </div>
            <div className="decision-option-chips">
              {step.sampleSize !== undefined ? <span className="fact-chip muted">{String(step.sampleSize)} 样本</span> : null}
              {confidence ? <span className={`fact-chip confidence-${confidence}`}>{confidenceZh(confidence)}</span> : null}
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
  const avoidPatterns = stringRows(miss.avoidPatterns)
  const preferredMiss = recordFrom(miss.preferredMiss)
  const rationale = stringValue(miss.rationale) || stringValue(miss.reason)
  const refs = uniqueStrings([...rowSourceRefs(miss), ...stringRows(decision.evidenceRefs), ...(decision.sourceRef ? [decision.sourceRef] : [])])

  return (
    <section className="decision-acceptable-miss" aria-label="Decision acceptable miss">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">目标纪律</p>
          <h3>可接受偏差</h3>
        </div>
        <span className="fact-chip muted">{optionLabelZh(selectedOptionId)}</span>
      </div>
      <div className="decision-miss-summary">
        <strong>{missDirectionZh(direction)}</strong>
        <span>{rationale || '未提供理由。'}</span>
      </div>
      <div className="decision-option-chips">
        {avoidRiskKinds.length ? <span className="fact-chip muted">避开 {avoidRiskKinds.join(', ')}</span> : null}
        {stringValue(preferredMiss.side) ? <span className="fact-chip muted">偏向侧面 {missDirectionZh(stringValue(preferredMiss.side))}</span> : null}
        {stringValue(preferredMiss.depth) ? <span className="fact-chip muted">偏向深度 {missDirectionZh(stringValue(preferredMiss.depth))}</span> : null}
        {avoidPatterns.length ? <span className="fact-chip muted">避开模式 {avoidPatterns.join(', ')}</span> : null}
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
  const historyText = historyDelta && historyDelta !== 0 ? `历史 ${historyDelta > 0 ? '+' : ''}${historyDelta} 风险` : null
  const refs = uniqueStrings([...stringRows(option.sourceRefs), ...stringRows(historyAdjustment.sourceRefs)])
  if (sampleSize === null && ready === undefined && !confidence && missingCount === 0 && !historyText && refs.length === 0) return null

  return (
    <div className="decision-option-chips">
      {sampleSize !== null ? <span className="fact-chip muted">样本 {sampleSize}</span> : null}
      {ready !== undefined || total !== undefined ? (
        <span className="fact-chip muted">
          覆盖 {String(ready ?? '-')}/{String(total ?? '-')}
        </span>
      ) : null}
      {confidence ? <span className={`fact-chip confidence-${confidence}`}>{confidenceZh(confidence)} 方案置信度</span> : null}
      {historyText ? <span className="fact-chip muted">{historyText}</span> : null}
      {missingCount ? <span className="fact-chip muted">缺失 {missingCount}</span> : null}
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
  const [secondClub, setSecondClub] = useState(sequenceClubDefault(decision, 1))
  const [secondCarry, setSecondCarry] = useState('')
  const [secondLie, setSecondLie] = useState('fairway')
  const [thirdClub, setThirdClub] = useState(sequenceClubDefault(decision, 2))
  const [thirdCarry, setThirdCarry] = useState('')
  const [thirdLie, setThirdLie] = useState('green')
  const [actualScoreToPar, setActualScoreToPar] = useState('')
  const [penalty, setPenalty] = useState(false)
  const actualCarryMeters = numericInput(actualCarry)
  const canAudit = actualClub.trim().length > 0 && actualCarryMeters !== undefined
  const auditControls = (
    <div className="decision-audit-controls">
      <label htmlFor="actual-club">实际球杆</label>
      <input id="actual-club" value={actualClub} onChange={(event) => setActualClub(event.target.value)} />
      <label htmlFor="actual-carry">实际带球 (米)</label>
      <input id="actual-carry" inputMode="decimal" value={actualCarry} onChange={(event) => setActualCarry(event.target.value)} />
      <label htmlFor="result-lie">落位</label>
      <select id="result-lie" value={resultLie} onChange={(event) => setResultLie(event.target.value)}>
        <option value="green">果岭</option>
        <option value="fringe">果岭边</option>
        <option value="fairway">球道</option>
        <option value="rough">长草</option>
        <option value="bunker">沙坑</option>
        <option value="water">水</option>
        <option value="penalty">罚杆</option>
      </select>
      <label htmlFor="actual-second-club">第2杆球杆</label>
      <input id="actual-second-club" value={secondClub} onChange={(event) => setSecondClub(event.target.value)} />
      <label htmlFor="actual-second-carry">第2杆带球 (米)</label>
      <input id="actual-second-carry" inputMode="decimal" value={secondCarry} onChange={(event) => setSecondCarry(event.target.value)} />
      <label htmlFor="actual-second-lie">第2杆落位</label>
      <select id="actual-second-lie" value={secondLie} onChange={(event) => setSecondLie(event.target.value)}>
        <option value="green">果岭</option>
        <option value="fringe">果岭边</option>
        <option value="fairway">球道</option>
        <option value="rough">长草</option>
        <option value="bunker">沙坑</option>
        <option value="water">水</option>
        <option value="penalty">罚杆</option>
      </select>
      <label htmlFor="actual-third-club">第3杆球杆</label>
      <input id="actual-third-club" value={thirdClub} onChange={(event) => setThirdClub(event.target.value)} />
      <label htmlFor="actual-third-carry">第3杆带球 (米)</label>
      <input id="actual-third-carry" inputMode="decimal" value={thirdCarry} onChange={(event) => setThirdCarry(event.target.value)} />
      <label htmlFor="actual-third-lie">第3杆落位</label>
      <select id="actual-third-lie" value={thirdLie} onChange={(event) => setThirdLie(event.target.value)}>
        <option value="green">果岭</option>
        <option value="fringe">果岭边</option>
        <option value="fairway">球道</option>
        <option value="rough">长草</option>
        <option value="bunker">沙坑</option>
        <option value="water">水</option>
        <option value="penalty">罚杆</option>
      </select>
      <label htmlFor="actual-score-to-par">实际相对标准杆</label>
      <input id="actual-score-to-par" inputMode="numeric" value={actualScoreToPar} onChange={(event) => setActualScoreToPar(event.target.value)} />
      <label className="decision-audit-checkbox" htmlFor="actual-penalty">
        <input id="actual-penalty" type="checkbox" checked={penalty} onChange={(event) => setPenalty(event.target.checked)} />
        发生罚杆
      </label>
      <button
        type="button"
        disabled={!canAudit}
        onClick={() =>
          onCreateAudit(buildActualOutcome({
            actualClub,
            actualCarryMeters: actualCarryMeters ?? 0,
            resultLie,
            secondClub,
            secondCarry,
            secondLie,
            thirdClub,
            thirdCarry,
            thirdLie,
            actualScoreToPar,
            penalty,
          }))
        }
      >
        复盘结果
      </button>
    </div>
  )

  if (state.status === 'loading') {
    return (
      <section className="decision-outcome-audit" aria-label="Decision outcome audit">
        <div className="report-title-row">
          <div>
            <p className="eyebrow">复盘审计</p>
            <h3>复盘处理中</h3>
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
            <p className="eyebrow">复盘审计</p>
            <h3>复盘暂不可用</h3>
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
  const criteriaResults = recordRows(audit?.criteriaResults)
  const actualShotRefs = stringRows(record?.actualShotRefs ?? audit?.actualShotRefs)
  const evidenceRefs = stringRows(record?.evidenceRefs ?? audit?.evidenceRefs)
  const suggestion = auditSuggestion(audit?.modelUpdateSuggestion)

  return (
    <section className="decision-outcome-audit" aria-label="Decision outcome audit">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">复盘审计</p>
          <h3>{audit ? '最新决策复盘' : '尚无复盘'}</h3>
          <p>{audit ? `计划 ${planned} → 实际 ${actual}` : '将已选方案与实际首杆对比。'}</p>
        </div>
      </div>
      {auditControls}
      {classification ? <span className={`audit-classification audit-${classification}`}>{classification}</span> : null}
      {audit ? (
        <div className="decision-audit-summary">
          <div className="report-row">
            <strong>实际击球</strong>
            <SourceRefs refs={actualShotRefs} onSelectRef={onSelectRef} />
          </div>
          <div className="report-row">
            <strong>依据</strong>
            <SourceRefs refs={evidenceRefs} onSelectRef={onSelectRef} />
          </div>
          <div className="decision-audit-facts" aria-label="Decision audit execution facts">
            <span className="fact-chip">选杆一致 {booleanLabel(executionMatch.clubMatch)}</span>
            <span className="fact-chip">距离 {metersLabel(executionMatch.distanceDelta_m)}</span>
            <span className="fact-chip">风险 {booleanLabel(executionMatch.riskTriggered)}</span>
          </div>
          <DecisionAuditCriteria rows={criteriaResults} />
          {Object.keys(result).length ? (
            <p className="decision-audit-result">
              {[
                result.clubName ? String(result.clubName) : null,
                result.meters !== undefined && result.meters !== null ? fmtYd(Number(result.meters)) : null,
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

function DecisionAuditCriteria({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return null

  return (
    <div className="decision-audit-criteria" aria-label="Decision audit criteria results">
      {rows.map((row, index) => {
        const status = stringValue(row.status) || 'unknown'
        const label = String(row.label ?? `criterion ${index + 1}`)
        return (
          <div className="decision-audit-criterion" key={`${label}-${index}`}>
            <div>
              <strong>{label}</strong>
              <span>{auditCriterionText(row)}</span>
            </div>
            <span className={`audit-criterion-status audit-criterion-${status}`}>{status}</span>
          </div>
        )
      })}
    </div>
  )
}

function buildActualOutcome({
  actualClub,
  actualCarryMeters,
  resultLie,
  secondClub,
  secondCarry,
  secondLie,
  thirdClub,
  thirdCarry,
  thirdLie,
  actualScoreToPar,
  penalty,
}: {
  actualClub: string
  actualCarryMeters: number
  resultLie: string
  secondClub: string
  secondCarry: string
  secondLie: string
  thirdClub: string
  thirdCarry: string
  thirdLie: string
  actualScoreToPar: string
  penalty: boolean
}): Record<string, unknown> {
  const firstShot = buildActualShot(1, actualClub, actualCarryMeters, resultLie, penalty)
  const actualShots = [
    firstShot,
    optionalActualShot(2, secondClub, secondCarry, secondLie),
    optionalActualShot(3, thirdClub, thirdCarry, thirdLie),
  ].filter((shot): shot is Record<string, unknown> => Boolean(shot))
  const scoreToPar = numericInput(actualScoreToPar)
  return {
    actualShot: firstShot,
    actualShots,
    ...(scoreToPar !== undefined ? { actualScoreToPar: scoreToPar } : {}),
    penalty,
  }
}

function optionalActualShot(shotOrder: number, clubName: string, carry: string, resultLie: string): Record<string, unknown> | null {
  const meters = numericInput(carry)
  if (!clubName.trim() || meters === undefined) return null
  return buildActualShot(shotOrder, clubName, meters, resultLie, false)
}

function buildActualShot(shotOrder: number, clubName: string, meters: number, resultLie: string, penalty: boolean): Record<string, unknown> {
  const shot: Record<string, unknown> = {
    shotOrder,
    clubName: clubName.trim(),
    meters,
    end: { lie: resultLie, feature: { surface: { kind: resultLie }, nearRisks: [] } },
  }
  if (penalty) shot.penalty = true
  return shot
}

function sequenceClubDefault(decision: CaddieDecisionResponse, index: number): string {
  const selectedSequence = recordFrom(decision.selectedSequence)
  const clubs = recordRows(selectedSequence.clubs)
  const club = clubs[index]
  return stringValue(club?.clubName)
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
        <p>无</p>
      )}
    </section>
  )
}

function AvoidZonesList({ rows }: { rows: Array<Record<string, unknown>> }) {
  const kindCounts: Record<string, number> = {}
  for (const row of rows) {
    const kind = stringValue(row.kind) || 'zone'
    kindCounts[kind] = (kindCounts[kind] ?? 0) + 1
  }
  const kindSeen: Record<string, number> = {}
  const labels = rows.map((row) => {
    const kind = stringValue(row.kind)
    if (!kind) return stringValue(row.label) || stringValue(row.id) || '项目'
    const zhKind = hazardKindZh(kind)
    kindSeen[kind] = (kindSeen[kind] ?? 0) + 1
    return kindCounts[kind] > 1 ? `${zhKind} ${kindSeen[kind]}` : zhKind
  })
  return (
    <section aria-label="Decision 避开区">
      <h3>避开区</h3>
      {rows.length ? (
        rows.map((row, index) => (
          <div className="report-row" key={`${String(row.label ?? row.id ?? row.kind ?? 'zone')}-${index}`}>
            <strong>{labels[index]}</strong>
            <span>{String(row.value ?? row.reason ?? row.text ?? row.distance_m ?? row.carryToClear_m ?? '')}</span>
          </div>
        ))
      ) : (
        <p>无</p>
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
        <p>无</p>
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

function numberValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return null
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

function formatStrokes(value: number): string {
  return Number.isInteger(value) ? `${value}` : value.toFixed(2).replace(/0+$/, '').replace(/\.$/, '')
}

function formatSignedStrokes(value: number): string {
  const formatted = formatStrokes(Math.abs(value))
  const sign = value > 0 ? '+' : value < 0 ? '-' : ''
  return `${sign}${formatted} 杆`
}

function selectedDecisionOption(decision: CaddieDecisionResponse): Record<string, unknown> {
  const selectedId = stringValue(decision.selectedOptionId)
  const fromOptions = (decision.options ?? []).find((option) => stringValue(option.id) === selectedId)
  if (fromOptions) return fromOptions
  return recordFrom(decision.selectedOption ?? decision.selected)
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
  if (value === true) return '是'
  if (value === false) return '否'
  return '未知'
}

function metersLabel(value: unknown): string {
  if (value === undefined || value === null || value === '') return '未知'
  const num = Number(value)
  return Number.isFinite(num) ? fmtYd(num) : String(value)
}

function auditCriterionText(row: Record<string, unknown>): string {
  const expected = formatExplanationValue(row.expected ?? row.expected_m ?? row.expectedRange_m)
  const actual = formatExplanationValue(row.actual ?? row.actual_m ?? row.actualScoreToPar ?? row.surface)
  const delta = row.distanceDelta_m !== undefined && row.distanceDelta_m !== null ? `差值 ${metersLabel(row.distanceDelta_m)}` : ''
  const parts = [expected ? `预期 ${expected}` : '', actual ? `实际 ${actual}` : '', delta].filter(Boolean)
  return parts.length ? parts.join(' - ') : String(row.rule ?? '')
}

function auditSuggestion(value: unknown): string | null {
  if (typeof value === 'string') return value
  const row = recordFrom(value)
  const suggestion = row.text ?? row.suggestion ?? row.reason
  return typeof suggestion === 'string' && suggestion.trim() ? suggestion : null
}

function MediaContextPanel({
  state,
  defaultTarget,
  onLoadMediaContext,
  onAttachMedia,
  onAnalyzeMedia,
  onRedactMedia,
  onConfirmVisionFinding,
}: {
  state: MediaContextState
  defaultTarget: { targetType: MediaTargetType; targetId: string }
  onLoadMediaContext?: (target: { targetType: MediaTargetType; targetId: string }) => void
  onAttachMedia?: (request: MediaCreateRequest) => void | Promise<void>
  onAnalyzeMedia?: (mediaId: string) => void
  onRedactMedia?: (mediaId: string) => void
  onConfirmVisionFinding?: (findingId: string, confirmationState: Extract<VisionConfirmationState, 'manual_confirmed' | 'rejected'>) => void
}) {
  const [targetType, setTargetType] = useState<MediaTargetType>(defaultTarget.targetType)
  const [targetId, setTargetId] = useState(defaultTarget.targetId)
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

  const targetMatchesLoaded = state.status === 'ready' && state.targetType === targetType && state.targetId === targetId
  const media = targetMatchesLoaded && Array.isArray(state.media) ? state.media : []
  const findings = targetMatchesLoaded && Array.isArray(state.findings) ? state.findings : []

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
      {state.status === 'ready' && !targetMatchesLoaded ? (
        <p className="media-context-error">
          Loaded media belongs to {state.targetType} {state.targetId}; reload media for {targetType} {targetId}.
        </p>
      ) : null}
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

function mediaTargetForSourceRef(sourceRef: string): { targetType: MediaTargetType; targetId: string } {
  const normalized = sourceRef.trim()
  const partCount = normalized.split(':').filter(Boolean).length
  if (partCount >= 3) return { targetType: 'shot', targetId: normalized }
  if (partCount >= 2) return { targetType: 'hole', targetId: normalized }
  return { targetType: 'round', targetId: normalized }
}

function mediaStateMatchesTarget(
  state: MediaContextState,
  target: { targetType: MediaTargetType; targetId: string },
): state is Extract<MediaContextState, { status: 'ready' }> {
  return state.status === 'ready' && state.targetType === target.targetType && state.targetId === target.targetId
}

function formatSequenceMeta(sequence: Record<string, unknown>): string {
  const strokes = sequence.expectedStrokes
  const remaining = sequence.expectedRemaining_m
  const risk = sequence.riskScore
  const parts = []
  if (strokes !== undefined) parts.push(`${String(strokes)} 杆`)
  if (remaining !== undefined) parts.push(`${fmtYd(Number(remaining))} 剩余`)
  if (risk !== undefined) parts.push(`风险 ${String(risk)}`)
  return parts.join(' - ') || '-'
}

function sequenceStepLabel(step: Record<string, unknown>): string {
  const carry = step.targetCarry_m ?? step.carry_m
  const remaining = step.expectedRemaining_m
  return [
    carry === undefined ? null : `${fmtYd(Number(carry))} 带球`,
    remaining === undefined ? null : `${fmtYd(Number(remaining))} 剩余`,
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
    carry === undefined ? null : fmtYd(Number(carry)),
    risk === undefined ? null : `风险 ${String(risk)}`,
    expected === undefined ? null : `${String(expected)} 预期`,
    clearance === undefined || clearance === null ? null : `${fmtYd(Number(clearance))} 余量`,
  ]
    .filter(Boolean)
    .join(' - ')
}
