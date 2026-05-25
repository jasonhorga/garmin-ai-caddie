import type { ReadinessCheck, ReadinessResponse, ReadinessState } from '../types'

interface ReadinessPanelProps {
  readiness: ReadinessResponse | null
  error?: string | null
}

const checkStateLabel: Record<ReadinessState, string> = {
  ready: 'ready',
  degraded: 'needs attention',
  error: 'error',
}

function evidenceItems(check: ReadinessCheck): string[] {
  return Object.entries(check.evidence ?? {})
    .filter(([, value]) => value !== null && value !== undefined && typeof value !== 'object')
    .map(([key, value]) => `${key}: ${String(value)}`)
}

export function ReadinessPanel({ readiness, error }: ReadinessPanelProps) {
  const status = readiness?.status ?? 'error'

  return (
    <section className="readiness-panel" aria-label="Private trial readiness">
      <div className="section-head">
        <div>
          <p className="eyebrow">Private Trial</p>
          <h2>Private Trial Readiness</h2>
          <p>Deployment, data, sync, mobile, and secret-handling checks from the live API.</p>
        </div>
        <span className={`semantic-chip readiness-${status}`}>{readiness ? status : 'unavailable'}</span>
      </div>

      {!readiness ? (
        <article className="readiness-empty">
          <p>{error ?? 'Readiness checks are not loaded yet.'}</p>
        </article>
      ) : (
        <div className="readiness-grid">
          {readiness.checks.map((check) => {
            const evidence = evidenceItems(check)
            return (
              <article key={check.label} className="readiness-check">
                <div className="readiness-check__main">
                  <h3>{check.label}</h3>
                  <p>{check.detail}</p>
                  {evidence.length ? (
                    <div className="readiness-evidence">
                      {evidence.map((item) => (
                        <span key={`${check.label}-${item}`}>{item}</span>
                      ))}
                    </div>
                  ) : null}
                </div>
                <span className={`semantic-chip readiness-${check.state}`}>{checkStateLabel[check.state]}</span>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}
