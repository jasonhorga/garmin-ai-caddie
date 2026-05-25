import { useState } from 'react'
import type { CaddieDecisionRequest, CaddieDecisionResponse, CaddieShotType } from '../types'

interface CaddiePageProps {
  decisionState: { status: 'idle' } | { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: CaddieDecisionResponse }
  onRequestDecision: (request: CaddieDecisionRequest) => void
}

export function CaddiePage({ decisionState, onRequestDecision }: CaddiePageProps) {
  const [shotType, setShotType] = useState<CaddieShotType>('approach')

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
        <button type="button" onClick={() => onRequestDecision(buildFixtureRequest(shotType))}>
          Request caddie plan
        </button>
      </section>

      <DecisionDetail state={decisionState} />
    </section>
  )
}

function DecisionDetail({ state }: { state: CaddiePageProps['decisionState'] }) {
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

function buildFixtureRequest(shotType: CaddieShotType): CaddieDecisionRequest {
  if (shotType === 'tee') {
    return {
      shotType,
      context: {
        courseName: 'Fixture Links',
        hole: 1,
        shotType,
        clubProfiles: {
          '1W': { clubName: '1W', sampleSize: 24, median: 221, p10: 190, p90: 249 },
          '3H': { clubName: '3H', sampleSize: 18, median: 178, p10: 158, p90: 198 },
        },
      },
    }
  }
  if (shotType === 'recovery') {
    return {
      shotType,
      context: {
        courseName: 'Fixture Links',
        hole: 11,
        distanceToPin_m: 178,
        lie: 'rough',
        blockedView: true,
        hazards: [{ kind: 'tree_area', id: 'trees_right', distance_m: 6 }],
      },
    }
  }
  return {
    shotType,
    context: {
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
    },
  }
}

function formatOptionMeta(option: Record<string, unknown>): string {
  const carry = option.carry_m ?? option.carryM ?? option.targetCarryM
  const risk = option.riskScore ?? option.risk
  return [carry === undefined ? null : `${String(carry)}m`, risk === undefined ? null : `risk ${String(risk)}`]
    .filter(Boolean)
    .join(' - ')
}
