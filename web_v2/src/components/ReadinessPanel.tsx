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
  return Object.entries(check.evidence ?? {}).flatMap(([key, value]) => evidenceValueItems(key, value))
}

function evidenceValueItems(key: string, value: unknown): string[] {
  if (value === null || value === undefined) return []
  if (Array.isArray(value)) {
    const values = value.map(formatEvidenceScalar).filter((item): item is string => Boolean(item))
    return values.length ? [`${key}: ${values.join(', ')}`] : []
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).flatMap(([childKey, childValue]) => evidenceValueItems(`${key}.${childKey}`, childValue))
  }
  const formatted = formatEvidenceScalar(value)
  return formatted ? [`${key}: ${formatted}`] : []
}

function formatEvidenceScalar(value: unknown): string | null {
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return null
    return redactedEvidenceText(trimmed)
  }
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

function redactedEvidenceText(value: string): string {
  const lower = value.toLowerCase()
  const looksPrivate =
    value.startsWith('/') ||
    value.includes('\\') ||
    lower.includes('/users/') ||
    lower.includes('/home/') ||
    lower.includes('file://') ||
    lower.includes('cookie') ||
    lower.includes('csrf') ||
    lower.includes('token') ||
    lower.includes('secret')
  return looksPrivate ? '[redacted]' : value
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
          {(readiness.checks ?? []).map((check) => {
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
