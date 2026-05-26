import { useState } from 'react'
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
  VisionFindingRecord,
} from '../types'

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
  onCreateAudit?: (decision: CaddieDecisionResponse) => void
  onLoadWeather?: () => void
  onLoadCaddieContext?: (params: CaddieContextParams) => void
  onLoadMediaContext?: (target: { targetType: MediaTargetType; targetId: string }) => void
  onAttachMedia?: (request: MediaCreateRequest) => void | Promise<void>
  onAnalyzeMedia?: (mediaId: string) => void
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
}: CaddiePageProps) {
  const [shotType, setShotType] = useState<CaddieShotType>('approach')
  const [contextSourceRef, setContextSourceRef] = useState('900001:7')
  const [contextDistance, setContextDistance] = useState('142')
  const [contextLie, setContextLie] = useState('fairway')
  const weatherSnapshot = weatherState.status === 'ready' ? weatherState.data : null
  const visionFindings = mediaState.status === 'ready' ? mediaState.findings : []
  const hasSourceContext = contextState.status === 'ready'

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
        shotType={shotType}
        onSourceRefChange={setContextSourceRef}
        onDistanceChange={setContextDistance}
        onLieChange={setContextLie}
        onLoadCaddieContext={onLoadCaddieContext}
      />
      <MediaContextPanel
        state={mediaState}
        onLoadMediaContext={onLoadMediaContext}
        onAttachMedia={onAttachMedia}
        onAnalyzeMedia={onAnalyzeMedia}
      />
      <DecisionDetail state={decisionState} auditState={auditState} onCreateAudit={onCreateAudit} />
    </section>
  )
}

function CaddieContextPanel({
  state,
  sourceRef,
  distance,
  lie,
  shotType,
  onSourceRefChange,
  onDistanceChange,
  onLieChange,
  onLoadCaddieContext,
}: {
  state: CaddieContextLoadState
  sourceRef: string
  distance: string
  lie: string
  shotType: CaddieShotType
  onSourceRefChange: (value: string) => void
  onDistanceChange: (value: string) => void
  onLieChange: (value: string) => void
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
        <button
          type="button"
          onClick={() =>
            onLoadCaddieContext?.({
              sourceRef,
              shotType,
              distanceToPinM: numericInput(distance),
              lie,
            })
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
}: {
  state: CaddiePageProps['decisionState']
  auditState: AuditState
  onCreateAudit?: (decision: CaddieDecisionResponse) => void
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
              <strong>{String(option.recommendedClub ?? option.club ?? '-')}</strong>
              <p>{formatOptionMeta(option)}</p>
            </article>
          )
        })}
      </div>

      <DecisionSequences sequences={decision.sequences ?? []} selectedSequence={decision.selectedSequence ?? null} />

      <div className="report-evidence-grid">
        <EvidenceList title="Evidence" rows={decision.evidence} />
        <EvidenceList title="Missing Data" rows={decision.missingData} />
        <EvidenceList title="Avoid Zones" rows={decision.avoidZones} />
        <EvidenceList title="Audit" rows={decision.auditCriteria} />
      </div>
      {onCreateAudit ? <DecisionAuditPanel state={auditState} onCreateAudit={() => onCreateAudit(decision)} /> : null}
    </section>
  )
}

function DecisionSequences({
  sequences,
  selectedSequence,
}: {
  sequences: Array<Record<string, unknown>>
  selectedSequence: Record<string, unknown> | null
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
            </article>
          )
        })}
      </div>
    </section>
  )
}

function DecisionAuditPanel({ state, onCreateAudit }: { state: AuditState; onCreateAudit: () => void }) {
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
          <button type="button" onClick={onCreateAudit}>
            Audit with fixture outcome
          </button>
        </div>
      </section>
    )
  }

  const audit = state.status === 'ready' ? state.data?.audit : null
  const classification = audit ? String(audit.classification ?? 'unknown') : null
  const planned = audit ? String(audit.plannedOptionId ?? '-') : '-'
  const actual = audit ? String(audit.actualOptionId ?? '-') : '-'

  return (
    <section className="decision-outcome-audit" aria-label="Decision outcome audit">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">Outcome audit</p>
          <h3>{audit ? 'Latest decision audit' : 'No outcome audit yet'}</h3>
          <p>{audit ? `planned ${planned} -> actual ${actual}` : 'Compare the selected plan with the first actual shot.'}</p>
        </div>
        <button type="button" onClick={onCreateAudit}>
          Audit with fixture outcome
        </button>
      </div>
      {classification ? <span className={`audit-classification audit-${classification}`}>{classification}</span> : null}
    </section>
  )
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

function MediaContextPanel({
  state,
  onLoadMediaContext,
  onAttachMedia,
  onAnalyzeMedia,
}: {
  state: MediaContextState
  onLoadMediaContext?: (target: { targetType: MediaTargetType; targetId: string }) => void
  onAttachMedia?: (request: MediaCreateRequest) => void | Promise<void>
  onAnalyzeMedia?: (mediaId: string) => void
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
                  <button type="button" aria-label={`Analyze media ${item.id}`} onClick={() => onAnalyzeMedia(item.id)}>
                    Analyze
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
                </div>
                <span className={`confidence-pill ${finding.confidence}`}>{finding.confidence}</span>
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

function numericInput(value: string): number | undefined {
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
