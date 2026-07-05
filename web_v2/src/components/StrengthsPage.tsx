import { useState } from 'react'
import type { HistoryStatsResponse } from '../types'
import { useDiagnostics } from '../diagnosticsContext'
import { issueLabel } from '../issueLabels'
import { fmtYd } from '../units'
import { clubLabelZh, confidenceZh, coverageZh, PAR_LABEL_ZH, phaseZh } from '../zhLabels'
import { AggregateEvidence } from './AggregateEvidence'
import { ShowAllToggle } from './ShowAllToggle'
import { SourceRefs } from './SourceRefs'
import { asNumber, asRows, asString, formatNumber, formatSigned, semanticClass, type StatRow } from './statsValues'

// 强弱分析 conclusions-first page. Replaces the old HoleStats/ClubStats/
// IssueStats stack: 你最该练 (top weaknesses) + 总体数字 (fairway/GIR/putts) +
// anchored 按洞/按杆/问题 sections, with the decision-audit engine content
// preserved verbatim-ish inside a closed <details> at the bottom.

interface StrengthsPageProps {
  data: HistoryStatsResponse
  onSelectRef?: (sourceRef: string) => void
}

const DIRECTION_ZH: Record<string, string> = {
  left: '偏左',
  right: '偏右',
  short: '偏短',
  long: '偏长',
  other: '方向不定',
  mixed: '方向不定',
}

// Exact-key zh labels for backend player-profile signals (history_stats.py
// _player_profile); pattern rules below cover the parameterised keys.
const PROFILE_LABEL_ZH: Record<string, string> = {
  three_putt_pressure: '三推太多',
  tee_fairway_control: '开球上球道稳',
  approach_gir_control: '攻果岭上果岭稳',
  putting_efficiency: '推杆效率高',
}

// "Par 5" → 五杆洞 (PAR_LABEL_ZH wording); non-par subjects return null so
// callers keep their existing raw-label fallback shape.
function parNameZh(name: string): string | null {
  const match = /^par\s*([345])$/i.exec(name.trim())
  return match ? PAR_LABEL_ZH[`par${match[1]}`] : null
}

function profileLabelZh(row: StatRow): string {
  const key = asString(row.key) ?? ''
  const label = asString(row.label) ?? key
  if (PROFILE_LABEL_ZH[key]) return PROFILE_LABEL_ZH[key]
  const direction = asString(row.direction)?.toLowerCase() ?? null
  if (key.startsWith('tee_miss_')) {
    return `开球${DIRECTION_ZH[direction ?? key.slice('tee_miss_'.length)] ?? '落点不稳'}`
  }
  const approachMiss = /^approach_(.+)_miss$/.exec(key)
  if (approachMiss) return `攻果岭${DIRECTION_ZH[direction ?? approachMiss[1]] ?? '易偏'}`
  if (key.startsWith('recent_')) return `近期${issueLabel(key.slice('recent_'.length))}`
  const scoringLoss = /^(.+) scoring loss$/.exec(label)
  if (scoringLoss) {
    const parName = parNameZh(scoringLoss[1])
    return parName ? `${parName}易失分` : `${scoringLoss[1]} 易失分`
  }
  const surfaceRisk = /^(.+) surface risk$/.exec(label)
  if (surfaceRisk) return `${clubLabelZh(surfaceRisk[1])} 落点风险高`
  const shorter = /^(.+) trending shorter$/.exec(label)
  if (shorter) return `${clubLabelZh(shorter[1])} 距离在变短`
  return label
}

// 你最该练 reason lines: rebuild Chinese from the STRUCTURED fields
// (value/unit/direction per history_stats _player_profile kind); for rows that
// only carry the English sentence, map the known sentence patterns; unknown
// text stays raw rather than vanishing.
const TREND_DIRECTION_ZH: Record<string, string> = {
  new: '新出现',
  worsening: '在恶化',
  improving: '在好转',
  flat: '持平',
  active: '活跃',
}

function scoringReasonZh(name: string, value: number): string {
  // "Par 5" reads as 五杆洞 (already contains 洞); unknown subjects keep the
  // previous `${name} 洞` shape.
  const subject = parNameZh(name) ?? `${name} 洞`
  if (value > 0) return `${subject}平均比标准杆多 ${formatNumber(value)} 杆`
  if (value < 0) return `${subject}平均比标准杆少 ${formatNumber(Math.abs(value))} 杆`
  return `${subject}平均持平标准杆`
}

function profileReasonZh(row: StatRow): string | null {
  const key = asString(row.key) ?? ''
  const reason = asString(row.reason) ?? ''
  const value = asNumber(row.value)
  const direction = asString(row.direction)?.toLowerCase() ?? null

  if (key === 'three_putt_pressure' || /^(\d+) three-putt holes/.test(reason)) {
    const count = value ?? Number(/^(\d+) three-putt holes/.exec(reason)?.[1])
    if (Number.isFinite(count)) return `有推杆记录的洞中三推 ${formatNumber(count)} 次`
  }
  if (key.startsWith('tee_miss_')) {
    const directionZh = DIRECTION_ZH[direction ?? key.slice('tee_miss_'.length)]
    // value is misses / recorded TEE SHOTS (history_stats leftPct = left/recorded),
    // not a share of the misses — 开球, not 失误.
    if (directionZh && value !== null) return `开球失误主要${directionZh},占已记录开球的 ${formatNumber(value)}%`
  }
  const approachMiss = /^approach_(.+)_miss$/.exec(key)
  if (approachMiss) {
    const directionZh = DIRECTION_ZH[direction ?? approachMiss[1]]
    if (directionZh && value !== null) return `攻果岭失误主要${directionZh},占 ${formatNumber(value)}%`
  }
  if (/_scoring_(loss|strength)$/.test(key) && value !== null) {
    const name = /^(.+) scoring (?:loss|strength)$/.exec(asString(row.label) ?? '')?.[1]
    if (name) return scoringReasonZh(name, value)
  }
  if (key.startsWith('club_distance_shorter_') || /recent median is [\d.]+m shorter/.test(reason)) {
    const meters = value ?? Number(/recent median is ([\d.]+)m shorter/.exec(reason)?.[1])
    if (Number.isFinite(meters)) return `近期常用距离比基准短 ${fmtYd(meters)}`
  }
  if (key.startsWith('club_surface_risk_') && value !== null) return `有 ${formatNumber(value)}% 的击球落入风险区(沙坑/长草/水)`
  if (key === 'tee_fairway_control' && value !== null) return `球道命中率 ${formatNumber(value)}%`
  if (key === 'approach_gir_control' && value !== null) return `GIR 上果岭率 ${formatNumber(value)}%`
  if (key === 'putting_efficiency' && value !== null) return `平均每洞 ${formatNumber(value)} 推`

  // English sentence patterns for rows where only the sentence exists.
  const teeMiss = /^dominant tee miss is (\w+) with ([\d.]+)% recorded misses$/.exec(reason)
  if (teeMiss && DIRECTION_ZH[teeMiss[1]]) return `开球失误主要${DIRECTION_ZH[teeMiss[1]]},占已记录开球的 ${teeMiss[2]}%`
  const approachSentence = /^dominant approach miss is (\w+) at ([\d.]+)%$/.exec(reason)
  if (approachSentence && DIRECTION_ZH[approachSentence[1]]) {
    return `攻果岭失误主要${DIRECTION_ZH[approachSentence[1]]},占 ${approachSentence[2]}%`
  }
  const toPar = /^(.+) averages ([+-]?[\d.]+) to par$/.exec(reason)
  if (toPar) return scoringReasonZh(toPar[1], Number(toPar[2]))
  const trend = /^recent trend is (\w+)$/.exec(reason)
  if (trend) return `近期趋势:${TREND_DIRECTION_ZH[trend[1]] ?? trend[1]}`
  const risk = /^.+ has ([\d.]+)% risk-result samples$/.exec(reason)
  if (risk) return `有 ${risk[1]}% 的击球落入风险区(沙坑/长草/水)`
  return asString(row.reason)
}

function profileValueZh(row: StatRow): string | null {
  const value = asNumber(row.value)
  if (value === null) return null
  switch (asString(row.unit)) {
    case 'pct':
      return `${value}%`
    case 'count':
      return `${value}次`
    case 'strokes':
      return `约损${value}杆`
    case 'to_par':
      return `平均${formatSigned(value)}杆`
    case 'putts':
      return `平均${value}推`
    case 'meters':
      return fmtYd(value)
    default:
      return String(value)
  }
}

// Score-distribution buckets arrive with English labels; map by stable key
// first (backend bucket keys), label as fallback for older payloads.
const OUTCOME_KEY_ZH: Record<string, string> = {
  eagleOrBetter: '老鹰',
  birdie: '小鸟',
  par: '帕',
  bogey: '柏忌',
  doubleOrWorse: '双+',
}

const OUTCOME_LABEL_ZH: Record<string, string> = {
  'Eagle+': '老鹰',
  Birdie: '小鸟',
  Par: '帕',
  Bogey: '柏忌',
  'Double+': '双+',
}

function outcomeZh(row: StatRow): string {
  const key = asString(row.key)
  if (key && OUTCOME_KEY_ZH[key]) return OUTCOME_KEY_ZH[key]
  const label = asString(row.label)
  if (label && OUTCOME_LABEL_ZH[label]) return OUTCOME_LABEL_ZH[label]
  return label ?? '结果'
}

interface FocusEntry {
  id: string
  label: string
  valueText: string | null
  phase: string | null
  reason: string | null
  refs: unknown
}

function focusEntries(data: HistoryStatsResponse): FocusEntry[] {
  const profile = (data.playerProfile ?? {}) as Record<string, unknown>
  const weaknesses = asRows(profile.weaknesses)
    .slice()
    .sort((a, b) => (asNumber(b.severityScore) ?? 0) - (asNumber(a.severityScore) ?? 0))
    .slice(0, 3)
  if (weaknesses.length > 0) {
    return weaknesses.map((row, index) => ({
      id: asString(row.key) ?? `weakness-${index}`,
      label: profileLabelZh(row),
      valueText: profileValueZh(row),
      phase: asString(row.phase),
      reason: profileReasonZh(row),
      refs: row.sourceRefs ?? row.refs,
    }))
  }
  return asRows(data.issues)
    .slice()
    .sort((a, b) => (asNumber(b.count) ?? 0) - (asNumber(a.count) ?? 0))
    .slice(0, 3)
    .map((issue, index) => ({
      id: asString(issue.issue) ?? `issue-${index}`,
      label: issueLabel(asString(issue.issue) ?? '问题'),
      valueText: asNumber(issue.count) !== null ? `${formatNumber(issue.count)}次` : null,
      phase: asString(issue.phase),
      reason: null,
      refs: issue.sourceRefs ?? issue.refs,
    }))
}

function TrendContextFacts({ row }: { row: StatRow }) {
  const baselineCount = asNumber(row.baselineCount)
  const recentCount = asNumber(row.recentCount)
  const baselineRate = asNumber(row.baselineRatePerRound)
  const recentRate = asNumber(row.recentRatePerRound)
  const actualImpact = asNumber(row.actualToParImpact)
  const actualCoverage = asRecord(row.actualImpactCoverage)
  const actualReady = asNumber(actualCoverage.ready)
  const actualTotal = asNumber(actualCoverage.total)

  return (
    <>
      {baselineCount !== null ? <span>baseline {formatNumber(baselineCount)}</span> : null}
      {recentCount !== null ? <span>recent {formatNumber(recentCount)}</span> : null}
      {baselineRate !== null || recentRate !== null ? (
        <span>
          rate {formatNumber(baselineRate)} -&gt; {formatNumber(recentRate)}/round
        </span>
      ) : null}
      {actualImpact !== null ? <span>{formatSigned(actualImpact)} actual to-par</span> : null}
      {actualReady !== null && actualTotal !== null ? (
        <span>
          actual {formatNumber(actualReady)}/{formatNumber(actualTotal)}
        </span>
      ) : null}
      <AggregateEvidence row={row} showReason={false} />
    </>
  )
}

// Real data renders 1200+ hole rows at once and froze the page — cap each
// section and expand on demand (pure display truncation, data unchanged).
const HOLES_CAP = 24
const CLUBS_CAP = 30
const ISSUES_CAP = 30

export function StrengthsPage({ data, onSelectRef }: StrengthsPageProps) {
  const focus = focusEntries(data)
  const [holesExpanded, setHolesExpanded] = useState(false)
  const [clubsExpanded, setClubsExpanded] = useState(false)
  const [issuesExpanded, setIssuesExpanded] = useState(false)
  const visibleHoles = holesExpanded ? data.holes : data.holes.slice(0, HOLES_CAP)
  const visibleClubs = clubsExpanded ? data.clubs : data.clubs.slice(0, CLUBS_CAP)
  const visibleIssues = issuesExpanded ? data.issues : data.issues.slice(0, ISSUES_CAP)

  const diagnostics = useDiagnostics()
  const phaseRows = asRows((data.scoring as Record<string, unknown>).phaseStats)
  const teeRow = phaseRows.find((row) => asString(row.phase) === 'Tee')
  const approachRow = phaseRows.find((row) => asString(row.phase) === 'Approach')
  const puttingRow = phaseRows.find((row) => asString(row.phase) === 'Putting')
  const fairwaysHit = asNumber(teeRow?.fairwaysHit)
  const teeSamples = asNumber(teeRow?.sampleCount)
  const fairwayPct = fairwaysHit !== null && teeSamples !== null && teeSamples > 0 ? Math.round((fairwaysHit / teeSamples) * 100) : null
  const girPct = asNumber(approachRow?.girPct)
  const approachSamples = asNumber(approachRow?.sampleCount)
  // Per-ROUND putts (~33) is the meaningful KPI (matches iOS); fall back to the
  // per-hole phase value only if the per-round field is absent.
  const puttingStats = asRecord((data.scoring as Record<string, unknown>).putting)
  const averagePuttsPerRound = asNumber(puttingStats.averagePuttsPerRound)
  const averagePuttsPerHole = asNumber(puttingRow?.averagePutts)
  const puttsKpiValue = averagePuttsPerRound ?? averagePuttsPerHole
  const puttsKpiSub = averagePuttsPerRound !== null ? '每场 · 估算' : '每洞 · 估算'

  const courseNames = new Map(
    asRows(data.courses).flatMap((course) => {
      const key = asString(course.courseKey)
      const name = asString(course.courseName)
      return key && name ? [[key, name] as const] : []
    }),
  )

  const issueTrends = asRows(data.diagnosis?.issueTrends)
  const auditDiagnosis = asRecord(data.diagnosis?.decisionAuditTrends)
  const auditCounts = asRows(auditDiagnosis.classificationCounts)
  const auditDrivers = asRows(auditDiagnosis.recentCostDrivers)
  const auditCriteria = asRows(auditDiagnosis.criteriaBreakdown)
  const optionOutcomes = asRows(auditDiagnosis.optionOutcomes)
  const hasAudit = auditCounts.length > 0 || auditDrivers.length > 0 || auditCriteria.length > 0 || optionOutcomes.length > 0

  return (
    <section className="stats-page strengths-page" aria-label="强弱分析">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">强弱分析</p>
          <h1>你最该练</h1>
          <p>按对成绩的影响排序；点出处编号可查看原始球局。</p>
        </div>
        <nav className="strengths-jump" aria-label="本页目录">
          <a href="#strengths-holes">按洞</a>
          <a href="#strengths-clubs">按杆</a>
          <a href="#strengths-issues">问题</a>
        </nav>
      </div>

      <div className="stats-list strengths-focus" aria-label="你最该练清单">
        {focus.length === 0 ? (
          <article className="stats-empty">
            <h2>样本不足，先多打几场</h2>
            <p>有了几场带逐洞记录的球局后，这里会给出最值得练的方向。</p>
          </article>
        ) : null}
        {focus.map((entry, index) => (
          <article key={entry.id} className="stats-item strengths-focus-item">
            <div className="stats-item-main">
              <h2>
                {index + 1}. {entry.label}
              </h2>
              {entry.reason ? <p>{entry.reason}</p> : null}
            </div>
            <div className="stats-item-facts">
              {entry.phase ? <span>{phaseZh(entry.phase)}</span> : null}
              {entry.valueText ? <span>{entry.valueText}</span> : null}
            </div>
            <p className="stats-refs">
              <SourceRefs refs={entry.refs} maxVisible={2} onSelectRef={onSelectRef} />
            </p>
          </article>
        ))}
      </div>

      {fairwayPct !== null || girPct !== null || puttsKpiValue !== null ? (
        <section className="trends-kpis strengths-kpis" aria-label="总体数字">
          {fairwayPct !== null ? (
            <article className="trends-kpi">
              <span className="trends-kpi-label">球道命中率</span>
              <b className="trends-kpi-value">{fairwayPct}%</b>
              <span className="trends-kpi-sub">
                {formatNumber(fairwaysHit)}/{formatNumber(teeSamples)} 个开球洞
              </span>
            </article>
          ) : null}
          {girPct !== null ? (
            <article className="trends-kpi">
              <span className="trends-kpi-label">GIR 上果岭率</span>
              <b className="trends-kpi-value">{girPct}%</b>
              {approachSamples !== null ? <span className="trends-kpi-sub">{approachSamples} 洞样本</span> : null}
            </article>
          ) : null}
          {puttsKpiValue !== null ? (
            <article className="trends-kpi">
              <span className="trends-kpi-label">平均推杆</span>
              <b className="trends-kpi-value">{puttsKpiValue}</b>
              <span className="trends-kpi-sub">{puttsKpiSub}</span>
            </article>
          ) : null}
        </section>
      ) : null}

      <section id="strengths-holes" className="panel compact-panel" aria-label="按洞">
        <div className="section-head compact-head">
          <div>
            <h2>按洞</h2>
            <p>反复丢杆的洞、得分分布和重复出现的问题。</p>
          </div>
        </div>
        <div className="stats-list">
          {data.holes.length === 0 ? (
            <article className="stats-empty">
              <h2>暂无逐洞数据</h2>
              <p>需要带逐洞成绩的记分卡才能看出重复模式。</p>
            </article>
          ) : null}
          {visibleHoles.map((hole) => {
            const distribution = asRows(hole.scoreDistribution).filter((row) => (asNumber(row.count) ?? 0) > 0)
            const repeatedIssues = asRows(hole.repeatedIssues)
            const courseKey = asString(hole.courseKey)
            const geometryCoverage = asString(hole.geometryCoverage)
            return (
              <article key={`${courseKey ?? 'course'}-${formatNumber(hole.hole)}`} className="stats-item hole-stats-item">
                <div className="stats-item-main">
                  <h2>第{formatNumber(hole.hole)}洞</h2>
                  <p>{(courseKey ? courseNames.get(courseKey) : null) ?? courseKey ?? '未知球场'}</p>
                </div>
                <div className="stats-item-facts">
                  <span>打过{formatNumber(hole.sampleCount)}次</span>
                  <span>平均{formatSigned(hole.averageToPar)}</span>
                  <span>最差{formatSigned(hole.worstToPar)}</span>
                  {geometryCoverage ? (
                    <span className={`semantic-chip ${semanticClass('quality', geometryCoverage)}`}>几何{coverageZh(geometryCoverage)}</span>
                  ) : null}
                </div>
                <p className="stats-refs">
                  <SourceRefs refs={hole.holeRefs ?? hole.refs} maxVisible={2} onSelectRef={onSelectRef} />
                </p>
                {distribution.length || repeatedIssues.length ? (
                  <div className="hole-breakdown">
                    {distribution.length ? (
                      <div className="hole-distribution" aria-label={`第${formatNumber(hole.hole)}洞得分分布`}>
                        {distribution.map((row) => {
                          // Each segment is sized to its share of the hole's rounds
                          // (row.pct), so a 40% bucket reads as 40% of the track — not
                          // a lone segment stretched to fill the full width.
                          const share = Math.max(0, Math.min(100, asNumber(row.pct) ?? 0))
                          return (
                            <span
                              key={asString(row.key) ?? asString(row.label) ?? 'bucket'}
                              className={`hole-distribution-bucket score-${asString(row.className) ?? 'missing'}`}
                              style={{ flexBasis: `${share}%` }}
                            >
                              <strong>{outcomeZh(row)}</strong>
                              <b>{formatNumber(row.count)}</b>
                              <em>{formatNumber(row.pct)}%</em>
                            </span>
                          )
                        })}
                      </div>
                    ) : null}
                    {/* evidence chips live BELOW the bar, never inside it (W4a finding) */}
                    {distribution.some((row) => hasRefs(row.holeRefs ?? row.refs ?? row.sourceRefs)) ? (
                      <div className="w4-distribution-refs" aria-label={`第${formatNumber(hole.hole)}洞得分出处`}>
                        {distribution
                          .filter((row) => hasRefs(row.holeRefs ?? row.refs ?? row.sourceRefs))
                          .map((row) => (
                            <span key={`refs-${asString(row.key) ?? asString(row.label) ?? 'bucket'}`} className="w4-distribution-ref-row">
                              <strong>{outcomeZh(row)}</strong>
                              <SourceRefs refs={row.holeRefs ?? row.refs ?? row.sourceRefs} maxVisible={2} onSelectRef={onSelectRef} />
                            </span>
                          ))}
                      </div>
                    ) : null}
                    {repeatedIssues.length ? (
                      <div className="hole-issues" aria-label={`第${formatNumber(hole.hole)}洞重复问题`}>
                        {repeatedIssues.slice(0, 3).map((issue) => (
                          <div key={`${asString(issue.issue) ?? 'issue'}-${asString(issue.source) ?? 'source'}`} className="hole-issue-row">
                            <span>
                              <strong>{issueLabel(asString(issue.issue) ?? '问题')}</strong>
                              {asString(issue.phase) ? <b>{phaseZh(asString(issue.phase) ?? '')}</b> : null}
                              <em>{formatNumber(issue.count)}次</em>
                            </span>
                            <SourceRefs refs={issue.sourceRefs ?? issue.refs} maxVisible={2} onSelectRef={onSelectRef} />
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </article>
            )
          })}
        </div>
        {data.holes.length > HOLES_CAP ? (
          <ShowAllToggle total={data.holes.length} expanded={holesExpanded} onToggle={() => setHolesExpanded((value) => !value)} />
        ) : null}
      </section>

      <section id="strengths-clubs" className="panel compact-panel" aria-label="按杆">
        <div className="section-head compact-head">
          <div>
            <h2>按杆</h2>
            <p>每支杆的常用距离和波动区间，全部按码显示。</p>
          </div>
        </div>
        <div className="stats-list">
          {data.clubs.length === 0 ? (
            <article className="stats-empty">
              <h2>暂无球杆样本</h2>
              <p>有击球数据或手动录入球杆后，这里会给出每支杆的距离模型。</p>
            </article>
          ) : null}
          {visibleClubs.map((club) => {
            const confidence = asString(club.confidence)
            const hazardRate = asNumber(club.hazardRate)
            const trend = asRecord(club.distanceTrend)
            const trendDirection = asString(trend.direction)
            const trendDelta = asNumber(trend.deltaMedian)
            return (
              <article key={asString(club.club) ?? 'club'} className="stats-item">
                <div className="stats-item-main">
                  <h2>{clubLabelZh(asString(club.club) ?? '未知球杆')}</h2>
                  <p>常用距离 {fmtYd(asNumber(club.median))}</p>
                </div>
                <div className="stats-item-facts">
                  <span>
                    波动 {fmtYd(asNumber(club.p10))}–{fmtYd(asNumber(club.p90))}
                  </span>
                  <span>最远 {fmtYd(asNumber(club.max))}</span>
                  <span>样本 {formatNumber(club.sampleCount)}</span>
                  {hazardRate !== null ? <span>风险率 {hazardRate}%</span> : null}
                  {/* distanceTrend chip restored from the old ClubStats — only
                      shorter/longer carry a meaningful delta; stable and
                      insufficient_data stay chipless */}
                  {(trendDirection === 'shorter' || trendDirection === 'longer') && trendDelta !== null ? (
                    <span className={`semantic-chip ${semanticClass('trend', trendDirection)}`}>
                      近期{trendDirection === 'shorter' ? '短' : '长'} {fmtYd(Math.abs(trendDelta))}
                    </span>
                  ) : null}
                  {confidence ? (
                    <span className={`semantic-chip ${semanticClass('confidence', confidence)}`}>信心{confidenceZh(confidence)}</span>
                  ) : null}
                </div>
                <p className="stats-refs">
                  <SourceRefs refs={club.validShotRefs ?? club.shotRefs ?? club.roundRefs ?? club.roundIds} maxVisible={2} onSelectRef={onSelectRef} />
                  {Array.isArray(club.riskShotRefs) && club.riskShotRefs.length > 0 ? (
                    <SourceRefs refs={club.riskShotRefs} maxVisible={2} onSelectRef={onSelectRef} />
                  ) : null}
                </p>
              </article>
            )
          })}
        </div>
        {data.clubs.length > CLUBS_CAP ? (
          <ShowAllToggle total={data.clubs.length} expanded={clubsExpanded} onToggle={() => setClubsExpanded((value) => !value)} />
        ) : null}
      </section>

      <section id="strengths-issues" className="panel compact-panel" aria-label="问题">
        <div className="section-head compact-head">
          <div>
            <h2>问题</h2>
            <p>反复出现的丢杆原因和近期在恶化的趋势。</p>
          </div>
        </div>
        {issueTrends.length > 0 ? (
          <>
            {/* visible sub-heading: the signed deltas below are recent-window
                changes, not lifetime totals — unlabeled they read as noise */}
            <h3 className="w4-list-subhead">近期变化</h3>
            <div className="stats-list" aria-label="近期变化">
              {issueTrends.slice(0, 5).map((trend) => {
                const issue = asString(trend.issue) ?? 'unknown_issue'
                const estimated = asNumber(trend.estimatedStrokesLost)
                return (
                  <article key={issue} className="stats-item diagnosis-item">
                    <div className="stats-item-main">
                      <h2>{issueLabel(issue)}</h2>
                      <p>
                        <SourceRefs refs={trend.recentRefs ?? trend.sourceRefs} maxVisible={2} onSelectRef={onSelectRef} />
                      </p>
                    </div>
                    <div className="stats-item-facts">
                      {asString(trend.phase) ? <span>{phaseZh(asString(trend.phase) ?? '')}</span> : null}
                      {estimated !== null ? <span>估损 {estimated.toFixed(1)}杆</span> : null}
                    </div>
                    <strong className="stats-count">{formatSigned(trend.deltaCount)} 次</strong>
                  </article>
                )
              })}
            </div>
          </>
        ) : null}
        {data.issues.length > 0 ? <h3 className="w4-list-subhead">全部问题</h3> : null}
        <div className="stats-list" aria-label={data.issues.length > 0 ? '全部问题' : undefined}>
          {data.issues.length === 0 ? (
            <article className="stats-empty">
              <h2>暂无重复问题</h2>
              <p>分析跑过之后，规则、AI 建议和手动标注的问题会出现在这里。</p>
            </article>
          ) : null}
          {visibleIssues.map((issue) => {
            const confidence = asString(issue.confidence)
            return (
              <article key={asString(issue.issue) ?? 'issue'} className="stats-item">
                <div className="stats-item-main">
                  <h2>{issueLabel(asString(issue.issue) ?? '问题')}</h2>
                  <p>
                    <SourceRefs refs={issue.sourceRefs ?? issue.refs} maxVisible={2} onSelectRef={onSelectRef} />
                  </p>
                </div>
                <div className="stats-item-facts">
                  {asString(issue.phase) ? <span>{phaseZh(asString(issue.phase) ?? '')}</span> : null}
                  {confidence ? (
                    <span className={`semantic-chip ${semanticClass('confidence', confidence)}`}>信心{confidenceZh(confidence)}</span>
                  ) : null}
                </div>
                <strong className="stats-count">{formatNumber(issue.count)} 次</strong>
              </article>
            )
          })}
        </div>
        {data.issues.length > ISSUES_CAP ? (
          <ShowAllToggle total={data.issues.length} expanded={issuesExpanded} onToggle={() => setIssuesExpanded((value) => !value)} />
        ) : null}
      </section>

      {hasAudit && diagnostics ? (
        <details className="strengths-audit">
          <summary>引擎自检（高级）</summary>
          <div className="stats-list">
            {auditCounts.slice(0, 4).map((row) => {
              const classification = asString(row.classification) ?? 'unknown'
              const pct = asNumber(row.pct)
              return (
                <article key={`audit-count-${classification}`} className="stats-item diagnosis-item">
                  <div className="stats-item-main">
                    <h3>{classification}</h3>
                    <p>
                      <SourceRefs refs={row.sourceRefs ?? row.refs} onSelectRef={onSelectRef} />
                    </p>
                  </div>
                  <div className="stats-item-facts">
                    <span className={`semantic-chip ${semanticClass('confidence', row.confidence)}`}>
                      {asString(row.confidence) ?? 'unknown'} confidence
                    </span>
                    <span>{pct === null ? '-%' : `${pct.toFixed(1)}%`}</span>
                  </div>
                  <strong className="stats-count">{formatNumber(row.count)}</strong>
                </article>
              )
            })}
            {auditDrivers.slice(0, 4).map((row) => {
              const classification = asString(row.classification) ?? 'unknown'
              const estimated = asNumber(row.estimatedStrokesLost)
              return (
                <article key={`audit-driver-${classification}`} className="stats-item diagnosis-item">
                  <div className="stats-item-main">
                    <h3>{classification}</h3>
                    <p>
                      <SourceRefs refs={row.recentRefs ?? row.sourceRefs} onSelectRef={onSelectRef} />
                    </p>
                  </div>
                  <div className="stats-item-facts">
                    {asString(row.phase) ? <span>{asString(row.phase)}</span> : null}
                    <TrendContextFacts row={row} />
                    {asString(row.direction) ? (
                      <span className={`semantic-chip ${semanticClass('trend', row.direction)}`}>{asString(row.direction)}</span>
                    ) : null}
                    <span>{estimated === null ? '- est. strokes' : `${estimated.toFixed(1)} est. strokes`}</span>
                  </div>
                  <strong className="stats-count">{formatSigned(row.deltaCount)}</strong>
                </article>
              )
            })}
            {auditCriteria.slice(0, 5).map((row) => {
              const label = asString(row.label) ?? 'criterion'
              const status = asString(row.status) ?? 'unknown'
              const pct = asNumber(row.pct)
              return (
                <article key={`audit-criterion-${label}-${status}`} className="stats-item diagnosis-item">
                  <div className="stats-item-main">
                    <h3>{label}</h3>
                    <p>
                      <SourceRefs refs={row.sourceRefs ?? row.refs} onSelectRef={onSelectRef} />
                    </p>
                  </div>
                  <div className="stats-item-facts">
                    <span className={`semantic-chip ${semanticClass('status', status)}`}>{status}</span>
                    <span>{pct === null ? '-%' : `${pct.toFixed(1)}% audits`}</span>
                    <AggregateEvidence row={row} showReason={false} showConfidence={false} />
                  </div>
                  <strong className="stats-count">{formatNumber(row.count)}</strong>
                </article>
              )
            })}
            {optionOutcomes.slice(0, 5).map((row) => {
              const selected = asString(row.selectedOptionId) ?? 'unknown'
              const actual = asString(row.actualOptionId) ?? 'unknown'
              const classification = asString(row.classification) ?? 'unknown'
              const pct = asNumber(row.pct)
              return (
                <article key={`audit-option-${selected}-${actual}-${classification}`} className="stats-item diagnosis-item">
                  <div className="stats-item-main">
                    <h3>
                      {selected} -&gt; {actual}
                    </h3>
                    <p>
                      <SourceRefs refs={row.sourceRefs ?? row.refs} onSelectRef={onSelectRef} />
                    </p>
                  </div>
                  <div className="stats-item-facts">
                    <span className={`semantic-chip ${semanticClass('confidence', row.confidence)}`}>
                      {asString(row.confidence) ?? 'unknown'} confidence
                    </span>
                    <span>{classification}</span>
                    <span>{pct === null ? '-%' : `${pct.toFixed(1)}% audits`}</span>
                  </div>
                  <strong className="stats-count">{formatNumber(row.count)}</strong>
                </article>
              )
            })}
          </div>
        </details>
      ) : null}
    </section>
  )
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function hasRefs(value: unknown): boolean {
  return Array.isArray(value) && value.some((item) => String(item).trim() !== '')
}
