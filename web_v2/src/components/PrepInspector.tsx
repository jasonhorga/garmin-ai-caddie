import type { CoursePrepClub, CoursePrepHole, PrepTip } from '../types'
import { useDiagnostics } from '../diagnosticsContext'
import { tipBasisZh } from '../zhLabels'
import {
  hazardSummary,
  headlineTargetYd,
  landingYd,
  recosForTarget,
  slopeYd,
  toGreenYd,
  waterCarryYards,
} from './prepWorkbenchLogic'

const SOURCE_LABEL: Record<string, string> = { played: '记分卡', courseview: 'CourseView', estimate: '推算' }

interface DistanceRow {
  key: string
  label: string
  value: string
}

function distanceRows(hole: CoursePrepHole, cum: number): DistanceRow[] {
  const rows: DistanceRow[] = []
  const overlay = hole.map?.overlay
  const headline = headlineTargetYd(hole, cum)
  if (overlay) {
    const toGreen = toGreenYd(hole, cum)
    rows.push({ key: 'tee', label: '距发球台', value: `${headline} 码` })
    if (toGreen !== null) rows.push({ key: 'green', label: '到果岭(中)', value: `${toGreen} 码` })
  } else {
    // No geometry — a "middle green" distance from a guessed landing would be
    // fiction, so show only what the payload actually carries.
    rows.push({ key: 'len', label: '全长', value: `${hole.blue_yards} 码` })
  }
  waterCarryYards(hole).forEach((carry, index) => {
    rows.push({ key: `water-${index}`, label: '过水需', value: `${carry} 码` })
  })
  const landing = landingYd(hole)
  if (landing !== null) rows.push({ key: 'landing', label: '落点(拐点)', value: `${landing} 码` })
  return rows
}

interface CaddieCardProps {
  hole: CoursePrepHole
  cum: number
  clubs: CoursePrepClub[]
}

function CaddieCard({ hole, cum, clubs }: CaddieCardProps) {
  const headline = headlineTargetYd(hole, cum)
  const slope = slopeYd(hole)
  const recos = recosForTarget(clubs, headline)
  const toGreen = toGreenYd(hole, cum)
  const playsLike = slope !== null ? headline + slope : null
  return (
    <div className="prep-card prep-card--caddie">
      <div className="prep-caddie-head">
        <div className="prep-caddie-big">
          {headline}
          <span className="prep-caddie-unit">码</span>
        </div>
        {playsLike !== null && slope !== null ? (
          <div className="prep-caddie-plays">
            <span className="prep-caddie-plays-label">实打</span>
            <span className="prep-caddie-updown">
              {slope > 0 ? '↑' : '↓'} {playsLike} 码
            </span>
            <span className="prep-caddie-tag">
              {slope > 0 ? '+' : ''}
              {slope} {slope > 0 ? '上坡' : '下坡'}
            </span>
          </div>
        ) : null}
      </div>
      {recos.length > 0 ? (
        <div className="prep-caddie-recos" aria-label="推荐球杆">
          {recos.map((club) => (
            <div key={club.name} className={club.on ? 'prep-club on' : 'prep-club'}>
              {club.name}
              <small>{club.yd} 码</small>
            </div>
          ))}
        </div>
      ) : null}
      {hole.steps.length > 0 ? (
        <ol className="prep-caddie-steps">
          {hole.steps.map((step, index) => (
            <li key={index}>{step.club ? <><b>{step.club}</b> {step.note}</> : step.note}</li>
          ))}
        </ol>
      ) : null}
      {hole.map?.overlay && hole.par !== 3 && toGreen !== null ? (
        <p className="prep-caddie-remain">落点后剩 ~{toGreen} 码攻果岭</p>
      ) : null}
      {hole.cautions.length > 0 ? (
        <ul className="prep-caddie-cautions">
          {hole.cautions.map((caution, index) => (
            <li key={index}>{caution}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

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
  cum: number
  clubs: CoursePrepClub[]
  tips: PrepTip[] | null
  tipsError: string | null
  onRetryTips: () => void
}

// The right-hand 球童试算 inspector: caddie card (recommended club + plays-like +
// strategy), the distance table for the current ball, the hole facts card, and
// the course-level personalized tips.
export function PrepInspector({ hole, cum, clubs, tips, tipsError, onRetryTips }: PrepInspectorProps): React.ReactElement {
  const diagnostics = useDiagnostics()
  const slope = slopeYd(hole)
  const hazards = hazardSummary(hole)
  const rows = distanceRows(hole, cum)
  return (
    <aside className="prep-inspector" aria-label="球童试算">
      <h3 className="prep-inspector-title">球童试算 · 第 {hole.hole} 洞</h3>
      <CaddieCard hole={hole} cum={cum} clubs={clubs} />

      <h3 className="prep-inspector-title">距离</h3>
      <div className="prep-card">
        {rows.map((row) => (
          <div key={row.key} className="prep-row">
            <span className="prep-row-k">{row.label}</span>
            <span className="prep-row-v">{row.value}</span>
          </div>
        ))}
      </div>

      <h3 className="prep-inspector-title">本洞信息</h3>
      <div className="prep-card">
        <div className="prep-row">
          <span className="prep-row-k">Par / 长度</span>
          <span className="prep-row-v">
            {hole.par} · {hole.blue_yards} 码
          </span>
        </div>
        {slope !== null ? (
          <div className="prep-row">
            <span className="prep-row-k">tee→果岭落差</span>
            <span className="prep-row-v">
              {slope > 0 ? '↑' : '↓'} {Math.abs(slope)} 码({slope > 0 ? '上坡' : '下坡'})
            </span>
          </div>
        ) : null}
        <div className="prep-row">
          <span className="prep-row-k">障碍</span>
          <span className="prep-row-v">{hazards.text}</span>
        </div>
        {diagnostics ? (
          <div className="prep-row">
            <span className="prep-row-k">Par 来源</span>
            <span className="prep-row-v">{SOURCE_LABEL[hole.par_source] ?? hole.par_source}</span>
          </div>
        ) : null}
      </div>

      <h3 className="prep-inspector-title">针对你</h3>
      <PrepTipsCard tips={tips} error={tipsError} onRetry={onRetryTips} />
    </aside>
  )
}
