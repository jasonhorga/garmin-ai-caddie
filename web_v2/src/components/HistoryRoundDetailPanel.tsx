import { useEffect, useRef } from 'react'
import type { AnnotationRecord, AnnotationTargetType, HistoryRoundDetailResponse, ReviewReportResponse } from '../types'
import { issueLabel } from '../issueLabels'
import { annotationKindZh, confidenceZh, coverageZh, phaseZh, stateZh } from '../zhLabels'
import { useDiagnostics } from '../diagnosticsContext'
import { SourceRefs } from './SourceRefs'

// Reformat the backend round title ("Kawana Hotel Golf Course ~ Oshima Left -
// 2025-09-02T08:47:59+09:00") into product copy: friendly date (strip time/zone),
// single nine separator. Falls through to the raw string if it doesn't parse.
// Uses a deterministic date slice (no locale/ICU dependence) so it's test-stable.
function formatRoundTitle(title: string): string {
  if (!title) return title
  let courseAndNine = title
  let dateText = ''
  const isoMatch = title.match(/^(.*?)\s*[-–]\s*((\d{4}-\d{2}-\d{2})(?:T[0-9:+.Z-]+)?)\s*$/)
  if (isoMatch) {
    courseAndNine = isoMatch[1]
    dateText = isoMatch[3]
  }
  // Normalize the "~" nine separator between course and nine to " · ".
  const course = courseAndNine.replace(/\s*[~]\s*/g, ' · ').replace(/\s{2,}/g, ' ').trim()
  return dateText ? `${course} · ${dateText}` : course
}

export type HistoryRoundDetailPanelState =
  | { status: 'idle' }
  | { status: 'loading'; roundRef: string }
  | { status: 'error'; roundRef: string; message: string }
  | { status: 'ready'; data: HistoryRoundDetailResponse }

interface HistoryRoundDetailPanelProps {
  state: HistoryRoundDetailPanelState
  reportState?: { status: 'idle' } | { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: ReviewReportResponse }
  onSelectRef?: (sourceRef: string) => void
  onRetryRound?: (roundRef: string) => void
  onCreateAnnotationForRound?: (target: { targetType: AnnotationTargetType; targetId: string }) => void
  onLoadRoundReport?: (roundRef: string) => void
  onGenerateRoundReport?: (roundRef: string) => void
}

function valueText(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

function compactValue(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() ? value : null
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

function toParText(value: unknown): string {
  if (typeof value !== 'number') return '-'
  if (value > 0) return `+${value}`
  return String(value)
}

function annotationSummary(record: AnnotationRecord): string {
  const from = compactValue(record.payload.from)
  const to = compactValue(record.payload.to)
  if (from && to) return `${from} → ${to}`
  const text = compactValue(record.payload.text) ?? compactValue(record.payload.note)
  if (text) return text
  return valueText(record.payload)
}

// Scorecard fairway tokens are stored raw (history_round_detail passes
// hole["fairway"] through): the closed normalization vocabulary lives in
// history_stats._fairway_direction. Unknown tokens fall through raw.
const FAIRWAY_ZH: Record<string, string> = {
  hit: '中',
  center: '中',
  centre: '中',
  fairway: '中',
  yes: '中',
  true: '中',
  left: '偏左',
  miss_left: '偏左',
  missed_left: '偏左',
  left_rough: '偏左',
  right: '偏右',
  miss_right: '偏右',
  missed_right: '偏右',
  right_rough: '偏右',
  miss: '未中',
  missed: '未中',
  rough: '长草',
}

function fairwayText(value: unknown): string {
  if (value === null || value === undefined) return '-'
  const token = String(value).trim().toLowerCase()
  return FAIRWAY_ZH[token] ?? valueText(value)
}

function girText(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (value === true || value === 'true') return '是'
  if (value === false || value === 'false') return '否'
  return valueText(value)
}

// row.primary closed sentence shapes from history_round_detail._phase_summary
// ('7/14 fairways', '9/18 GIR', '5 putts', …). Unknown shapes fall through raw.
const PHASE_PRIMARY_PATTERNS: Array<[RegExp, (match: RegExpExecArray) => string]> = [
  [/^(\d+)\/(\d+) fairways$/, (match) => `球道 ${match[1]}/${match[2]}`],
  [/^(\d+)\/(\d+) GIR$/, (match) => `GIR ${match[1]}/${match[2]}`],
  [/^(\d+) tee shots$/, (match) => `开球 ${match[1]} 杆`],
  [/^(\d+) approach shots$/, (match) => `攻果岭 ${match[1]} 杆`],
  [/^(\d+) short shots$/, (match) => `短杆 ${match[1]} 杆`],
  [/^(\d+) putts$/, (match) => `推杆 ${match[1]}`],
  [/^(\d+) putt shots$/, (match) => `推杆 ${match[1]} 杆`],
  [/^(\d+) double-or-worse holes$/, (match) => `双柏忌+ ${match[1]} 洞`],
]

function phasePrimaryZh(raw: string): string {
  for (const [pattern, build] of PHASE_PRIMARY_PATTERNS) {
    const match = pattern.exec(raw)
    if (match) return build(match)
  }
  return raw
}

// Coverage cells carry the closed ready/partial/missing vocabulary as plain
// strings; anything non-string (counts, null) keeps the generic rendering.
function factValueZh(value: unknown, translate: (token: string) => string): string {
  return typeof value === 'string' ? translate(value) : valueText(value)
}

const ISSUE_TAG_KINDS = new Set<AnnotationRecord['kind']>(['issue_tag', 'issue_tag_removed'])

// Resolve the issue tags that are currently active for the round: an `issue_tag`
// record adds a tag and a later `issue_tag_removed` record retracts it. The most
// recent record for a given tag wins, matching the IssueStats / history_stats logic.
function activeIssueTags(records: AnnotationRecord[]): string[] {
  const ordered = [...records]
    .filter((record) => ISSUE_TAG_KINDS.has(record.kind))
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
  const active = new Map<string, boolean>()
  const seenOrder: string[] = []
  for (const record of ordered) {
    const tag = compactValue(record.payload.tag)
    if (!tag) continue
    if (!active.has(tag)) seenOrder.push(tag)
    active.set(tag, record.kind === 'issue_tag')
  }
  return seenOrder.filter((tag) => active.get(tag))
}

function RoundFacts({ data, diagnostics }: { data: HistoryRoundDetailResponse; diagnostics: boolean }) {
  const round = data.round ?? {}
  const coverage = typeof round.coverage === 'object' && round.coverage !== null ? round.coverage as Record<string, unknown> : {}
  // Default: only real golf stats. Coverage/confidence are ETL completeness flags
  // (记分卡/击球数据/推杆数 齐全, 置信度) → diagnostics-only.
  const facts: Array<[string, string]> = [
    ['成绩', valueText(round.score)],
    ['对标准杆', toParText(round.toPar)],
    ['洞数', valueText(round.holesScored ?? round.holesCompleted)],
    ['击球数', valueText(round.shotCount)],
  ]
  if (diagnostics) {
    facts.push(
      ['记分卡', factValueZh(coverage.scorecard, coverageZh)],
      ['击球数据', factValueZh(coverage.shots, coverageZh)],
      ['推杆数', factValueZh(coverage.putts, coverageZh)],
      ['置信度', factValueZh(round.confidence, confidenceZh)],
    )
  }

  return (
    <section className="round-detail-facts" aria-label="球局数据">
      {facts.map(([label, value]) => (
        <div
          key={label}
          className={
            label === '成绩'
              ? 'round-detail-fact round-detail-fact--score'
              : label === '对标准杆'
                ? 'round-detail-fact round-detail-fact--topar'
                : 'round-detail-fact'
          }
        >
          <span>{label}</span>
          <b>{value}</b>
        </div>
      ))}
    </section>
  )
}

function ScorecardGrid({ data, onSelectRef }: { data: HistoryRoundDetailResponse; onSelectRef?: (sourceRef: string) => void }) {
  if (data.scorecard.length === 0) return null
  const front = data.scorecard.filter((cell) => cell.hole <= 9)
  const back = data.scorecard.filter((cell) => cell.hole > 9)
  const renderNine = (label: '前九' | '后九', cells: typeof data.scorecard) => {
    if (cells.length === 0) return null
    return (
      <div className="round-detail-nine" aria-label={`${label}记分卡`}>
        <span className="round-detail-nine-label">{label}</span>
        <div className="round-detail-nine-grid">
          {cells.map((cell) => {
            const content = (
              <>
                <span>H{cell.hole}</span>
                <b className="round-detail-score-mark">{cell.score ?? '-'}</b>
                <small>
                  Par {cell.par ?? '-'} · {toParText(cell.toPar)}
                </small>
                <em>
                  {cell.putts === null ? '推杆 —' : `${cell.putts}推`}
                  {cell.penalties == null ? '' : ` · 罚${cell.penalties}`}
                </em>
              </>
            )
            return onSelectRef ? (
              <button
                key={cell.holeRef}
                type="button"
                className={`round-detail-cell score-${cell.className}`}
                onClick={() => onSelectRef(cell.holeRef)}
                aria-label={`第${cell.hole}洞详情`}
              >
                {content}
              </button>
            ) : (
              <div key={cell.holeRef} className={`round-detail-cell score-${cell.className}`}>
                {content}
              </div>
            )
          })}
        </div>
      </div>
    )
  }
  return (
    <section className="round-detail-section" aria-label="记分卡">
      <div className="section-head">
        <div>
          <h3>记分卡</h3>
          <p>逐洞成绩、推杆数、罚杆数、果岭击球率、球道命中</p>
        </div>
      </div>
      <div className="round-detail-scorecard">
        {renderNine('前九', front)}
        {renderNine('后九', back)}
      </div>
    </section>
  )
}

function PhaseSummary({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (rows.length === 0) return null
  return (
    <section className="round-detail-section" aria-label="阶段汇总">
      <h3>阶段汇总</h3>
      <div className="round-phase-grid">
        {rows.map((row) => (
          <article key={valueText(row.phase)} className="round-phase-card">
            <span>{phaseZh(valueText(row.phase))}</span>
            <b>{phasePrimaryZh(valueText(row.primary))}</b>
            <small>{stateZh(valueText(row.state))}</small>
          </article>
        ))}
      </div>
    </section>
  )
}

function HoleDetails({ rows, onSelectRef, diagnostics }: { rows: Array<Record<string, unknown>>; onSelectRef?: (sourceRef: string) => void; diagnostics: boolean }) {
  if (rows.length === 0) return null
  return (
    <section className="round-detail-section" aria-label="逐洞详情">
      <h3>逐洞详情</h3>
      <div className="round-hole-table">
        {rows.map((row) => (
          <div key={valueText(row.holeRef)} className="round-hole-row">
            <div>
              <span>H{valueText(row.hole)}</span>
              <b>{valueText(row.score)} / {toParText(row.toPar)}</b>
            </div>
            <div>
              <span>推杆 / 罚杆</span>
              <b>{valueText(row.putts)} / {valueText(row.penalties)}</b>
            </div>
            <div>
              <span>GIR</span>
              <b>{girText(row.gir)}</b>
            </div>
            <div>
              <span>球道</span>
              <b>{fairwayText(row.fairway)}</b>
            </div>
            <div className="round-hole-sources">
              <span>击球</span>
              {diagnostics ? (
                <SourceRefs refs={row.shotRefs} maxVisible={3} onSelectRef={onSelectRef} />
              ) : (
                <b>{Array.isArray(row.shotRefs) && row.shotRefs.length ? `${row.shotRefs.length} 杆` : '—'}</b>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function RelatedSources({ data, onSelectRef }: { data: HistoryRoundDetailResponse; onSelectRef?: (sourceRef: string) => void }) {
  const groups = [
    ['球局', data.relatedRefs.roundRefs],
    ['球洞', data.relatedRefs.holeRefs],
    ['击球', data.relatedRefs.shotRefs],
    ['原始', data.relatedRefs.sourceRefs ?? []],
  ] as const
  if (!groups.some(([, refs]) => refs.length > 0)) return null
  return (
    <section className="round-detail-section" aria-label="相关来源">
      <h3>相关来源</h3>
      <div className="drilldown-rows">
        {groups.map(([label, refs]) => (
          <div key={label} className="drilldown-row">
            <span>{label}</span>
            <b>
              <SourceRefs refs={refs} maxVisible={5} onSelectRef={onSelectRef} />
            </b>
          </div>
        ))}
      </div>
    </section>
  )
}

function MissingDataRows({ rows, diagnostics }: { rows: Array<Record<string, unknown>>; diagnostics: boolean }) {
  if (rows.length === 0) return null
  // Default: one graceful sentence. The per-row ETL gap detail is diagnostics-only.
  if (!diagnostics) {
    return (
      <section className="round-detail-section" aria-label="数据说明">
        <p className="round-detail-missing-note">部分数据不完整，分析可能略有缺失。</p>
      </section>
    )
  }
  return (
    <section className="round-detail-section" aria-label="缺失数据">
      <h3>缺失数据</h3>
      <div className="drilldown-rows">
        {rows.map((row, index) => (
          <div key={`${valueText(row.label)}-${index}`} className="drilldown-row">
            <span>{valueText(row.label)}</span>
            <b>{valueText(row.state ?? row.reason)}</b>
          </div>
        ))}
      </div>
    </section>
  )
}

function IssueTags({ annotations }: { annotations: AnnotationRecord[] }) {
  const tags = activeIssueTags(annotations)
  if (tags.length === 0) return null
  return (
    <section className="round-detail-section" aria-label="问题标签">
      <h3>问题标签</h3>
      <div className="fact-array">
        {tags.map((tag) => (
          <span key={tag} className="fact-chip">
            {issueLabel(tag)}
          </span>
        ))}
      </div>
    </section>
  )
}

function ShotSummary({ data, diagnostics }: { data: HistoryRoundDetailResponse; diagnostics: boolean }) {
  const round = data.round ?? {}
  const shotCount = typeof round.shotCount === 'number' ? round.shotCount : 0
  const holesWithShots = data.scorecard.filter((cell) => cell.shotRefs.length > 0).length
  const holesWithRoute = data.scorecard.filter((cell) => cell.shotRefs.length > 0 && cell.globalId != null && cell.localHole != null).length
  if (shotCount === 0 && holesWithShots === 0) return null
  const facts: Array<[string, string]> = [
    ['记录击球', String(shotCount)],
    ['有击球的洞数', String(holesWithShots)],
  ]
  // 有路径图的洞数 = geometry coverage jargon → diagnostics-only.
  if (diagnostics) facts.push(['有路径图的洞数', String(holesWithRoute)])
  return (
    <section className="round-detail-section" aria-label="击球汇总">
      <h3>击球汇总</h3>
      <div className="fact-array">
        {facts.map(([label, value]) => (
          <span key={label} className="fact-chip">
            {label} {value}
          </span>
        ))}
      </div>
    </section>
  )
}

function AnnotationRows({ title, rows }: { title: string; rows: AnnotationRecord[] }) {
  // Issue tags are surfaced in their own IssueTags section, so keep them out of
  // the generic annotation list to avoid showing the same tag twice.
  const visible = rows.filter((row) => !ISSUE_TAG_KINDS.has(row.kind))
  if (visible.length === 0) return null
  return (
    <section className="round-detail-section" aria-label={title}>
      <h3>{title}</h3>
      <div className="drilldown-rows">
        {visible.map((row) => (
          <div key={row.id} className="drilldown-row">
            <span>{annotationKindZh(row.kind)}</span>
            <b>{annotationSummary(row)}</b>
          </div>
        ))}
      </div>
    </section>
  )
}

function asRecordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
    : []
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item).trim()).filter(Boolean)
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>()
  const unique: string[] = []
  for (const value of values) {
    if (seen.has(value)) continue
    seen.add(value)
    unique.push(value)
  }
  return unique
}

function evidenceRefs(row: Record<string, unknown>): string[] {
  return uniqueStrings([
    ...asStringArray(row.refs),
    ...asStringArray(row.sourceRefs),
    ...asStringArray(row.roundRefs),
    ...asStringArray(row.holeRefs),
    ...asStringArray(row.shotRefs),
    ...asStringArray(row.missingDataRefs),
  ])
}

function EvidenceValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return null
  if (Array.isArray(value)) {
    return (
      <div className="fact-array">
        {value.slice(0, 4).map((item, index) => (
          <span key={`${valueText(item)}-${index}`} className="fact-chip">
            {valueText(item)}
          </span>
        ))}
        {value.length > 4 ? <span className="fact-chip muted">等 {value.length - 4} 处</span> : null}
      </div>
    )
  }
  if (typeof value === 'object') {
    return (
      <div className="fact-object compact">
        {Object.entries(value as Record<string, unknown>)
          .filter(([, item]) => item === null || ['string', 'number', 'boolean'].includes(typeof item))
          .slice(0, 6)
          .map(([key, item]) => (
            <span key={key} className="fact-chip">
              {key} {valueText(item)}
            </span>
          ))}
      </div>
    )
  }
  return <div className="fact-value">{valueText(value)}</div>
}

function RoundAiEvidence({ report, onSelectRef }: { report: ReviewReportResponse; onSelectRef?: (sourceRef: string) => void }) {
  const facts = asRecordArray(report.factsUsed)
  const missingData = asRecordArray(report.missingData)
  const inferences = asRecordArray(report.inferencesMade)
  const unsupportedClaims = asRecordArray(report.unsupportedClaims)

  return (
    <div className="report-evidence-grid round-ai-review-evidence">
      <section aria-label="Round AI facts">
        <h4>事实</h4>
        {facts.length ? (
          facts.map((fact, index) => (
            <div className="report-row" key={`${valueText(fact.label)}-${index}`}>
              <div className="report-row-main">
                <strong>{valueText(fact.label ?? '事实')}</strong>
                <span>{valueText(fact.source ?? '来源')}</span>
                <EvidenceValue value={fact.value} />
              </div>
              <SourceRefs refs={evidenceRefs(fact)} onSelectRef={onSelectRef} />
            </div>
          ))
        ) : (
          <p>无</p>
        )}
      </section>

      <section aria-label="Round AI inferences">
        <h4>推断</h4>
        {inferences.length ? (
          inferences.map((inference, index) => (
            <div className="report-row" key={`${valueText(inference.claim)}-${index}`}>
              <div className="report-row-main">
                <strong>{valueText(inference.claim ?? '推断')}</strong>
                <div className="report-metadata">
                  {asStringArray(inference.factLabels).map((label) => <span key={`fact-${label}`} className="fact-chip muted">{label} 事实</span>)}
                  {asStringArray(inference.missingDataLabels).map((label) => <span key={`missing-${label}`} className="fact-chip muted">{label} 缺失</span>)}
                  {typeof inference.confidence === 'string' ? <span className="fact-chip muted">{confidenceZh(inference.confidence)} 推断置信</span> : null}
                </div>
              </div>
              <SourceRefs refs={evidenceRefs(inference)} onSelectRef={onSelectRef} />
            </div>
          ))
        ) : (
          <p>无</p>
        )}
      </section>

      <section aria-label="Round AI missing data">
        <h4>缺失数据</h4>
        {missingData.length ? (
          missingData.map((item, index) => (
            <div className="report-row" key={`${valueText(item.label)}-${index}`}>
              <div className="report-row-main">
                <strong>{valueText(item.label ?? '缺失项')}</strong>
                <span>{valueText(item.state ?? item.reason ?? '待复核')}</span>
              </div>
              <SourceRefs refs={evidenceRefs(item)} onSelectRef={onSelectRef} />
            </div>
          ))
        ) : (
          <p>无</p>
        )}
      </section>

      <section aria-label="Round AI unsupported claims">
        <h4>无依据断言</h4>
        {unsupportedClaims.length ? (
          unsupportedClaims.map((claim, index) => (
            <div className="report-row" key={`${valueText(claim.category)}-${index}`}>
              <div className="report-row-main">
                <strong>{valueText(claim.category ?? '断言')}</strong>
                <span>{valueText(claim.claim ?? '无依据断言')}</span>
                {typeof claim.reason === 'string' ? <span>{claim.reason}</span> : null}
              </div>
              <SourceRefs refs={evidenceRefs(claim)} onSelectRef={onSelectRef} />
            </div>
          ))
        ) : (
          <p>无</p>
        )}
      </section>
    </div>
  )
}

function RoundAiReview({
  roundRef,
  reportState,
  onLoadRoundReport,
  onGenerateRoundReport,
  onSelectRef,
  diagnostics,
}: {
  roundRef: string
  reportState?: HistoryRoundDetailPanelProps['reportState']
  onLoadRoundReport?: (roundRef: string) => void
  onGenerateRoundReport?: (roundRef: string) => void
  onSelectRef?: (sourceRef: string) => void
  diagnostics: boolean
}) {
  if (!onLoadRoundReport && !onGenerateRoundReport && (!reportState || reportState.status === 'idle')) return null
  const loadedReport =
    reportState?.status === 'ready' &&
    reportState.data.kind === 'round' &&
    reportState.data.subjectId === roundRef
      ? reportState.data
      : null

  return (
    <section
      className={loadedReport ? 'round-detail-section round-ai-review' : 'round-detail-section round-ai-review round-ai-review--empty'}
      aria-label="Round AI review"
    >
      <div className="section-head">
        <div>
          <h3>AI 回顾</h3>
          <p>基于事实的球局叙述，含来源引用和缺失数据说明。</p>
        </div>
        <div className="button-row">
          {onLoadRoundReport ? (
            <button type="button" onClick={() => onLoadRoundReport(roundRef)}>
              载入 AI 回顾
            </button>
          ) : null}
          {onGenerateRoundReport ? (
            <button type="button" onClick={() => onGenerateRoundReport(roundRef)}>
              生成 AI 回顾
            </button>
          ) : null}
        </div>
      </div>
      {reportState?.status === 'loading' ? <p>AI 回顾加载中</p> : null}
      {reportState?.status === 'error' ? <p>{reportState.message}</p> : null}
      {loadedReport ? (
        <div className="round-ai-review-body">
          <div className="round-ai-review-meta">
            <span>置信度：{confidenceZh(loadedReport.confidence)}</span>
            {diagnostics ? <span>{loadedReport.provider}</span> : null}
            {diagnostics ? <span>{loadedReport.model}</span> : null}
          </div>
          <p>{loadedReport.narrative}</p>
          {diagnostics ? <SourceRefs refs={loadedReport.sourceRefs} onSelectRef={onSelectRef} /> : null}
          {diagnostics ? <RoundAiEvidence report={loadedReport} onSelectRef={onSelectRef} /> : null}
        </div>
      ) : null}
    </section>
  )
}

export function HistoryRoundDetailPanel({
  state,
  reportState,
  onSelectRef,
  onRetryRound,
  onCreateAnnotationForRound,
  onLoadRoundReport,
  onGenerateRoundReport,
}: HistoryRoundDetailPanelProps) {
  const diagnostics = useDiagnostics()
  const rootRef = useRef<HTMLElement | null>(null)
  // The panel mounts below the full timeline — without this, 打开 on a card up
  // top looks like a no-op because the detail appears thousands of pixels down.
  const scrollKey =
    state.status === 'idle'
      ? null
      : state.status === 'ready'
        ? state.data.requestedRef || state.data.roundRef
        : state.roundRef
  useEffect(() => {
    if (scrollKey) rootRef.current?.scrollIntoView?.({ block: 'start', behavior: 'smooth' })
  }, [scrollKey])
  if (state.status === 'idle') return null

  if (state.status === 'loading') {
    return (
      <section ref={rootRef} className="panel round-detail-panel" aria-live="polite">
        <h2>球局回顾</h2>
        <p>正在加载球局…</p>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section ref={rootRef} className="panel round-detail-panel" aria-live="polite">
        <h2>球局回顾</h2>
        <p>{state.message}</p>
        {onRetryRound ? (
          <button type="button" className="drilldown-action-button" onClick={() => onRetryRound(state.roundRef)}>
            重试
          </button>
        ) : null}
      </section>
    )
  }

  const data = state.data
  const canAnnotate = data.found && Boolean(data.roundRef.trim()) && Boolean(onCreateAnnotationForRound)
  return (
    <section ref={rootRef} className="panel round-detail-panel" aria-live="polite">
      <div className="drilldown-title-row round-detail-hero">
        <div>
          <p className="eyebrow">球局记分卡</p>
          <h2>{data.found ? '球局回顾' : '球局不可用'}</h2>
          <p className="round-detail-course-title">{formatRoundTitle(data.title)}</p>
        </div>
        <div className="drilldown-meta">
          {diagnostics ? <span>{data.roundRef}</span> : null}
          {diagnostics ? <span>{data.found ? '已找到' : '未找到'}</span> : null}
          {canAnnotate ? (
            <button
              type="button"
              className="drilldown-action-button"
              onClick={() => onCreateAnnotationForRound?.({ targetType: 'round', targetId: data.roundRef })}
              aria-label="为这一局添加订正"
            >
              添加订正
            </button>
          ) : null}
        </div>
      </div>

      {data.found ? <RoundFacts data={data} diagnostics={diagnostics} /> : null}
      {data.found ? <IssueTags annotations={data.annotations ?? []} /> : null}
      <ScorecardGrid data={data} onSelectRef={diagnostics ? onSelectRef : undefined} />
      {data.found ? <ShotSummary data={data} diagnostics={diagnostics} /> : null}
      {data.found ? (
        <RoundAiReview
          roundRef={data.roundRef}
          reportState={reportState}
          onLoadRoundReport={onLoadRoundReport}
          onGenerateRoundReport={onGenerateRoundReport}
          onSelectRef={onSelectRef}
          diagnostics={diagnostics}
        />
      ) : null}
      <PhaseSummary rows={data.phaseSummary} />
      <HoleDetails rows={data.holeDetails} onSelectRef={onSelectRef} diagnostics={diagnostics} />
      {diagnostics ? <RelatedSources data={data} onSelectRef={onSelectRef} /> : null}
      <AnnotationRows title="球局标注" rows={data.annotations ?? []} />
      <AnnotationRows title="已应用订正" rows={data.corrections ?? []} />
      <MissingDataRows rows={data.missingData} diagnostics={diagnostics} />
    </section>
  )
}
