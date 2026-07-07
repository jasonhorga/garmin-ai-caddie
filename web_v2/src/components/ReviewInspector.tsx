import type { TimelineRow } from './reviewShotMapLogic'

// The caddie-recommended vs actually-played comparison. Historical Garmin rounds
// carry no live caddie decision, so this is usually absent — the card renders ONLY
// when a decision was actually recorded (never invented from nothing).
export interface ReviewDecision {
  seqLabel: string
  recommended: string
  actual: string
  cost?: string | null
  good?: string | null
}

interface ReviewInspectorProps {
  hole: number
  par: number | null
  score: number | null
  toPar: number | null
  timeline: TimelineRow[]
  decision?: ReviewDecision | null
  shotsLoading?: boolean
  // 这一洞用户手填的罚杆数(复盘修改层,默认 0)。>0 时在洞信息区显示一个只读徽标。
  manualPenalty?: number
}

function toParText(toPar: number | null): string {
  if (toPar === null) return ''
  if (toPar === 0) return 'E'
  return toPar > 0 ? `+${toPar}` : String(toPar)
}

function holeSubtitle(par: number | null, score: number | null, toPar: number | null): string {
  const parPart = par === null ? 'Par —' : `Par ${par}`
  const scorePart = score === null ? '' : ` → ${score}`
  const toParPart = toParText(toPar)
  return `${parPart}${scorePart}${toParPart ? ` · ${toParPart}` : ''}`
}

export function ReviewInspector({ hole, par, score, toPar, timeline, decision, shotsLoading, manualPenalty }: ReviewInspectorProps): React.ReactElement {
  const penalty = manualPenalty ?? 0
  return (
    <aside className="review-inspector" aria-label="杆序">
      <h3 className="review-inspector-title">
        杆序 · 第 {hole} 洞
        <span className="review-inspector-sub">（{holeSubtitle(par, score, toPar)}）</span>
      </h3>

      {penalty > 0 ? (
        <div className="review-manual-penalty" aria-label={`本洞手填罚杆 加 ${penalty}`}>
          <span className="review-manual-penalty-tag" aria-hidden="true">改</span>
          本洞手填罚杆 +{penalty}
        </div>
      ) : null}

      {timeline.length > 0 ? (
        <ol className="review-timeline">
          {timeline.map((row, index) =>
            row.kind === 'shot' ? (
              <li key={`shot-${index}`} className={row.synthetic ? 'review-shot synthetic' : 'review-shot'}>
                <span className="review-shot-dot" aria-hidden="true" />
                <div className="review-shot-body">
                  <div className="review-shot-head">
                    <span className="review-shot-club">{row.club}</span>
                    {row.distanceYd !== null ? <span className="review-shot-yd">{row.distanceYd} 码</span> : null}
                    {row.corrected ? (
                      <span className="review-corrected" title="你修正过这一杆(球杆或球位)" aria-label="已修正">
                        改
                      </span>
                    ) : null}
                  </div>
                  {row.resultZh ? <div className="review-shot-result">{row.resultZh}</div> : null}
                </div>
              </li>
            ) : (
              <li key={`putt-${index}`} className="review-shot putt">
                <span className="review-shot-dot" aria-hidden="true" />
                <div className="review-shot-body">
                  <div className="review-shot-head">
                    <span className="review-shot-club">推杆</span>
                    <span className="review-shot-yd">×{row.count}</span>
                  </div>
                </div>
              </li>
            ),
          )}
        </ol>
      ) : (
        <p className="review-inspector-empty">{shotsLoading ? '正在载入这一洞的击球…' : '这一洞没有逐杆击球记录。'}</p>
      )}

      {decision ? (
        <div className="review-card review-card--decision" aria-label="决策对比">
          <h4 className="review-card-title">决策 vs 实际</h4>
          <div className="review-diff">
            <span className="review-diff-k">{decision.seqLabel} 球童建议</span>
            <span className="review-diff-v">{decision.recommended}</span>
          </div>
          <div className="review-diff">
            <span className="review-diff-k">实际</span>
            <span className="review-diff-v bad">{decision.actual}</span>
          </div>
          {decision.cost ? (
            <div className="review-diff">
              <span className="review-diff-k">代价</span>
              <span className="review-diff-v bad">{decision.cost}</span>
            </div>
          ) : null}
          {decision.good ? (
            <div className="review-diff">
              <span className="review-diff-k">亮点</span>
              <span className="review-diff-v good">{decision.good}</span>
            </div>
          ) : null}
        </div>
      ) : null}
    </aside>
  )
}
