import { useState } from 'react'
import type {
  CaddieDecisionAuditRecord,
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
  mediaState?: MediaContextState
  onRequestDecision: (request: CaddieDecisionRequest) => void
  onCreateAudit?: (decision: CaddieDecisionResponse) => void
  onLoadWeather?: () => void
  onLoadMediaContext?: (target: { targetType: MediaTargetType; targetId: string }) => void
  onAttachMedia?: (request: MediaCreateRequest) => void | Promise<void>
  onAnalyzeMedia?: (mediaId: string) => void
}

export function CaddiePage({
  decisionState,
  auditState = { status: 'idle' },
  weatherState = { status: 'idle' },
  mediaState = { status: 'idle' },
  onRequestDecision,
  onCreateAudit,
  onLoadWeather,
  onLoadMediaContext,
  onAttachMedia,
  onAnalyzeMedia,
}: CaddiePageProps) {
  const [shotType, setShotType] = useState<CaddieShotType>('approach')
  const weatherSnapshot = weatherState.status === 'ready' ? weatherState.data : null
  const visionFindings = mediaState.status === 'ready' ? mediaState.findings : []

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
        <button type="button" onClick={() => onRequestDecision(buildFixtureRequest(shotType, weatherSnapshot, visionFindings))}>
          Request caddie plan
        </button>
      </section>

      {onLoadWeather ? <WeatherContextPanel state={weatherState} /> : null}
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
            <span>{String(row.value ?? row.reason ?? row.distance_m ?? row.carryToClear_m ?? '')}</span>
          </div>
        ))
      ) : (
        <p>None</p>
      )}
    </section>
  )
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

function buildFixtureRequest(
  shotType: CaddieShotType,
  weatherSnapshot: WeatherSnapshotResponse | null,
  visionFindings: VisionFindingRecord[] = [],
): CaddieDecisionRequest {
  const withContext = (context: Record<string, unknown>) => ({
    ...context,
    ...(weatherSnapshot ? { weatherSnapshot } : {}),
    ...(visionFindings.length ? { visionFindings } : {}),
  })

  if (shotType === 'tee') {
    return {
      shotType,
      context: withContext({
        courseName: 'Fixture Links',
        hole: 1,
        shotType,
        clubProfiles: {
          '1W': { clubName: '1W', sampleSize: 24, median: 221, p10: 190, p90: 249 },
          '3H': { clubName: '3H', sampleSize: 18, median: 178, p10: 158, p90: 198 },
        },
      }),
    }
  }
  if (shotType === 'recovery') {
    return {
      shotType,
      context: withContext({
        courseName: 'Fixture Links',
        hole: 11,
        distanceToPin_m: 178,
        lie: 'rough',
        blockedView: true,
        hazards: [{ kind: 'tree_area', id: 'trees_right', distance_m: 6 }],
      }),
    }
  }
  return {
    shotType,
    context: withContext({
      courseName: 'Fixture Links',
      hole: 4,
      distanceToPin_m: 142,
      lie: 'fairway',
      hazards: [{ kind: 'water', id: 'water_front', carryToClear_m: 126, distance_m: 14 }],
      clubProfiles: {
        '9I': { clubName: '9I', sampleSize: 24, median: 132, p10: 120, p90: 140 },
        '8I': { clubName: '8I', sampleSize: 24, median: 144, p10: 132, p90: 153 },
        '7I': { clubName: '7I', sampleSize: 24, median: 156, p10: 142, p90: 168 },
      },
    }),
  }
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
  return [carry === undefined ? null : `${String(carry)}m`, risk === undefined ? null : `risk ${String(risk)}`]
    .filter(Boolean)
    .join(' - ')
}
