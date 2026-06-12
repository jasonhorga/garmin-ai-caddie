import { stateZh } from '../zhLabels'
import type { ReadinessCheck, ReadinessResponse, ReadinessState } from '../types'

interface ReadinessPanelProps {
  readiness: ReadinessResponse | null
  error?: string | null
}

const checkStateLabel: Record<ReadinessState, string> = {
  ready: '就绪',
  degraded: '需关注',
  error: '错误',
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
    <section className="readiness-panel" aria-label="试运行就绪度">
      <div className="section-head">
        <div>
          <p className="eyebrow">私享试运行</p>
          <h2>试运行就绪度</h2>
          <p>来自线上 API 的部署、数据、同步、移动端与密钥处理检查。</p>
        </div>
        <span className={`semantic-chip readiness-${status}`}>{readiness ? stateZh(status) : '不可用'}</span>
      </div>

      {!readiness ? (
        <article className="readiness-empty">
          <p>{error ?? '就绪检查尚未加载。'}</p>
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
