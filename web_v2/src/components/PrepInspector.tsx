import type { CoursePrepHole, PrepTip } from '../types'
import { tipBasisZh } from '../zhLabels'

interface PrepTipsCardProps {
  tips: PrepTip[] | null
  error: string | null
  onRetry: () => void
}

function PrepTipsCard({ tips, error, onRetry }: PrepTipsCardProps) {
  if (error) {
    return (
      <div className="prep-card empty-state prep-load-error" aria-label="个性化提示加载失败">
        <p>{error}</p>
        <button type="button" onClick={onRetry}>
          重试
        </button>
      </div>
    )
  }
  if (tips === null) return <p className="prep-inspector-placeholder">个性化提示加载中…</p>
  if (tips.length === 0) return <p className="prep-inspector-placeholder">暂无足够数据生成提示</p>
  return (
    <ul className="prep-tips-list">
      {tips.map((tip, index) => {
        const basisZh = tipBasisZh(tip.basis)
        return (
          <li key={index} className="prep-tip">
            <span className={`prep-tip-dot ${tip.severity}`} aria-hidden="true" />
            <div className="prep-tip-body">
              <p className="prep-tip-text">{tip.text}</p>
              {basisZh ? <p className="prep-tip-basis">依据:{basisZh}</p> : null}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

export interface PrepInspectorProps {
  hole: CoursePrepHole
  tips: PrepTip[] | null
  tipsError: string | null
  onRetryTips: () => void
}

// The map already carries target distance, recommended club, F/M/B and obstacle edges. Only facts
// that genuinely need reading/ordering live here, collapsed into a small map dock until requested.
export function PrepInspector({ hole, tips, tipsError, onRetryTips }: PrepInspectorProps): React.ReactElement {
  const hasPlanDetails = hole.steps.length > 0 || hole.cautions.length > 0
  const tipCount = tips?.length ?? 0
  return (
    <aside className="prep-inspector prep-inspector--map-dock" aria-label="球童试算">
      <div className="prep-map-detail-dock">
        {hasPlanDetails ? (
          <details className="prep-map-details" aria-label="展开完整打法">
            <summary>打法详情 · {hole.steps.length} 步</summary>
            {hole.steps.length > 0 ? (
              <ol className="prep-caddie-steps">
                {hole.steps.map((step, index) => (
                  <li key={index}>{step.club ? <><b>{step.club}</b> {step.note}</> : step.note}</li>
                ))}
              </ol>
            ) : null}
            {hole.cautions.length > 0 ? (
              <ul className="prep-caddie-cautions">
                {hole.cautions.map((caution, index) => <li key={index}>{caution}</li>)}
              </ul>
            ) : null}
          </details>
        ) : null}
        <details className="prep-map-details" aria-label="展开个性化提示">
          <summary>
            针对你 · {tips === null ? '载入中' : `${tipCount} 条`}
          </summary>
          <PrepTipsCard tips={tips} error={tipsError} onRetry={onRetryTips} />
        </details>
      </div>
    </aside>
  )
}
