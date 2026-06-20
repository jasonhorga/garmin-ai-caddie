import { useMemo, useState } from 'react'
import type { HistoryStatsResponse, ReviewReportIndexResponse, ReviewReportIndexItem, ReviewReportResponse } from '../types'
import { useDiagnostics } from '../diagnosticsContext'
import { confidenceZh } from '../zhLabels'
import { SourceRefs } from './SourceRefs'
import { StatsQualityChips } from './StatsQualityChips'

// Human title for a report subject (instead of a raw subjectId like recent_10 /
// quarter:2026-Q2). Round/club/hole refs have no in-page lookup → shown raw.
function reportSubjectZh(kind: string, subjectId: unknown): string {
  const id = String(subjectId ?? '').trim()
  if (!id) return reportKindZh(kind)
  if (id === 'recent_10') return '近10场'
  const quarter = id.match(/^(?:quarter:)?(\d{4})-Q([1-4])$/i)
  if (quarter) return `${quarter[1]}年Q${quarter[2]}`
  const year = id.match(/^(?:year:)?(\d{4})$/)
  if (year) return `${year[1]}年`
  return id
}

const REPORT_KIND_ZH: Record<string, string> = {
  trend: '趋势',
  round: '球局',
  course: '球场',
  hole: '球洞',
  club: '球杆',
}

function reportKindZh(kind: string): string {
  return REPORT_KIND_ZH[kind] ?? kind
}

type ReportIndexState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: ReviewReportIndexResponse }

interface ReportsPageProps {
  stats: HistoryStatsResponse
  reportState: { status: 'idle' } | { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: ReviewReportResponse }
  reportIndexState: ReportIndexState
  onLoadTrend: (period: string) => void
  onGenerateTrend: (period: string) => void
  onLoadRound: (roundId: string) => void
  onGenerateRound: (roundId: string) => void
  onLoadCourse: (courseKey: string) => void
  onGenerateCourse: (courseKey: string) => void
  onLoadHole: (courseKey: string, hole: number) => void
  onGenerateHole: (courseKey: string, hole: number) => void
  onLoadClub: (clubName: string) => void
  onGenerateClub: (clubName: string) => void
  onSelectRef?: (sourceRef: string) => void
}

interface Option {
  id: string
  label: string
}

interface HoleOption extends Option {
  courseKey: string
  hole: number
}

export function ReportsPage({
  stats,
  reportState,
  reportIndexState,
  onLoadTrend,
  onGenerateTrend,
  onLoadRound,
  onGenerateRound,
  onLoadCourse,
  onGenerateCourse,
  onLoadHole,
  onGenerateHole,
  onLoadClub,
  onGenerateClub,
  onSelectRef,
}: ReportsPageProps) {
  const trendOptions = useMemo(() => buildTrendOptions(stats), [stats])
  const roundOptions = useMemo(() => buildRoundOptions(stats), [stats])
  const courseOptions = useMemo(() => buildCourseOptions(stats), [stats])
  const holeOptions = useMemo(() => buildHoleOptions(stats), [stats])
  const clubOptions = useMemo(() => buildClubOptions(stats), [stats])
  const [trendPeriod, setTrendPeriod] = useState(trendOptions[0]?.id ?? 'recent_10')
  const [roundId, setRoundId] = useState(roundOptions[0]?.id ?? '')
  const [courseKey, setCourseKey] = useState(courseOptions[0]?.id ?? '')
  const [holeId, setHoleId] = useState(holeOptions[0]?.id ?? '')
  const [clubName, setClubName] = useState(clubOptions[0]?.id ?? '')
  const selectedHole = holeOptions.find((option) => option.id === holeId)

  return (
    <section className="reports-workspace">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">事实驱动评测</p>
          <h1>报告</h1>
          <p>基于事实的球局和趋势报告，含缺失数据追踪。</p>
        </div>
        <StatsQualityChips data={stats} labels={['reports']} />
      </div>

      <div className="reports-layout">
        <section className="report-controls" aria-label="报告控制">
          <div className="field-row">
            <label htmlFor="trend-period">周期</label>
            <select id="trend-period" value={trendPeriod} onChange={(event) => setTrendPeriod(event.target.value)}>
              {trendOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="button-row">
            <button type="button" onClick={() => onLoadTrend(trendPeriod)}>
              载入趋势报告
            </button>
            <button type="button" onClick={() => onGenerateTrend(trendPeriod)}>
              生成趋势报告
            </button>
          </div>

          <div className="field-row">
            <label htmlFor="round-id">球局编号</label>
            <select id="round-id" value={roundId} onChange={(event) => setRoundId(event.target.value)}>
              {roundOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="button-row">
            <button type="button" disabled={!roundId} onClick={() => onLoadRound(roundId)}>
              载入球局报告
            </button>
            <button type="button" disabled={!roundId} onClick={() => onGenerateRound(roundId)}>
              生成球局报告
            </button>
          </div>

          <div className="field-row">
            <label htmlFor="course-key">球场</label>
            <select id="course-key" value={courseKey} onChange={(event) => setCourseKey(event.target.value)}>
              {courseOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="button-row">
            <button type="button" disabled={!courseKey} onClick={() => onLoadCourse(courseKey)}>
              载入球场报告
            </button>
            <button type="button" disabled={!courseKey} onClick={() => onGenerateCourse(courseKey)}>
              生成球场报告
            </button>
          </div>

          <div className="field-row">
            <label htmlFor="hole-key">洞号</label>
            <select id="hole-key" value={holeId} onChange={(event) => setHoleId(event.target.value)}>
              {holeOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="button-row">
            <button
              type="button"
              disabled={!selectedHole}
              onClick={() => selectedHole && onLoadHole(selectedHole.courseKey, selectedHole.hole)}
            >
              载入球洞报告
            </button>
            <button
              type="button"
              disabled={!selectedHole}
              onClick={() => selectedHole && onGenerateHole(selectedHole.courseKey, selectedHole.hole)}
            >
              生成球洞报告
            </button>
          </div>

          <div className="field-row">
            <label htmlFor="club-name">球杆</label>
            <select id="club-name" value={clubName} onChange={(event) => setClubName(event.target.value)}>
              {clubOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="button-row">
            <button type="button" disabled={!clubName} onClick={() => onLoadClub(clubName)}>
              载入球杆报告
            </button>
            <button type="button" disabled={!clubName} onClick={() => onGenerateClub(clubName)}>
              生成球杆报告
            </button>
          </div>

          <ReportInventory
            state={reportIndexState}
            onLoadTrend={onLoadTrend}
            onLoadRound={onLoadRound}
            onLoadCourse={onLoadCourse}
            onLoadHole={onLoadHole}
            onLoadClub={onLoadClub}
            onSelectRef={onSelectRef}
          />
        </section>

        <ReportDetail state={reportState} onSelectRef={onSelectRef} />
      </div>
    </section>
  )
}

const REPORTS_BATCH = 30
// Stable empty array so the last-key comparison cannot loop while loading.
const EMPTY_REPORTS: ReviewReportIndexItem[] = []

function ReportInventory({
  state,
  onLoadTrend,
  onLoadRound,
  onLoadCourse,
  onLoadHole,
  onLoadClub,
  onSelectRef,
}: {
  state: ReportIndexState
  onLoadTrend: (period: string) => void
  onLoadRound: (roundId: string) => void
  onLoadCourse: (courseKey: string) => void
  onLoadHole: (courseKey: string, hole: number) => void
  onLoadClub: (clubName: string) => void
  onSelectRef?: (sourceRef: string) => void
}) {
  // 973 real reports rendered at once froze the renderer — show the first batch
  // and append on demand, resetting when a fresh index arrives (last-key idiom).
  const reports = state.status === 'ready' ? state.data.reports : EMPTY_REPORTS
  const [visibleCount, setVisibleCount] = useState(REPORTS_BATCH)
  const [lastReports, setLastReports] = useState(reports)
  if (lastReports !== reports) {
    setLastReports(reports)
    setVisibleCount(REPORTS_BATCH)
  }
  if (state.status === 'loading') {
    return (
      <section className="report-inventory" aria-label="报告索引">
        <h2>报告索引</h2>
        <p>载入报告中</p>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="report-inventory" aria-label="报告索引">
        <h2>报告索引</h2>
        <p>{state.message}</p>
      </section>
    )
  }

  if (state.status !== 'ready' || state.data.reports.length === 0) {
    return (
      <section className="report-inventory" aria-label="报告索引">
        <h2>报告索引</h2>
        <p>暂无报告</p>
      </section>
    )
  }

  return (
    <section className="report-inventory" aria-label="报告索引">
      <div className="report-inventory-head">
        <h2>报告索引</h2>
        <span className="fact-chip muted">{state.data.total} 条</span>
      </div>
      <div className="report-inventory-list">
        {reports.slice(0, visibleCount).map((report) => (
          <ReportInventoryRow
            key={report.id || `${report.kind}-${report.subjectId}-${report.storedAt}`}
            report={report}
            onLoadTrend={onLoadTrend}
            onLoadRound={onLoadRound}
            onLoadCourse={onLoadCourse}
            onLoadHole={onLoadHole}
            onLoadClub={onLoadClub}
            onSelectRef={onSelectRef}
          />
        ))}
      </div>
      {reports.length > visibleCount ? (
        <button
          type="button"
          className="w4-load-more-btn"
          onClick={() => setVisibleCount((count) => count + REPORTS_BATCH)}
        >
          加载更多(还有 {reports.length - visibleCount} 条)
        </button>
      ) : null}
    </section>
  )
}

function ReportInventoryRow({
  report,
  onLoadTrend,
  onLoadRound,
  onLoadCourse,
  onLoadHole,
  onLoadClub,
  onSelectRef,
}: {
  report: ReviewReportIndexItem
  onLoadTrend: (period: string) => void
  onLoadRound: (roundId: string) => void
  onLoadCourse: (courseKey: string) => void
  onLoadHole: (courseKey: string, hole: number) => void
  onLoadClub: (clubName: string) => void
  onSelectRef?: (sourceRef: string) => void
}) {
  const handleOpen = () => {
    if (report.kind === 'trend') {
      onLoadTrend(report.subjectId)
    } else if (report.kind === 'round') {
      onLoadRound(report.subjectId)
    } else if (report.kind === 'course') {
      onLoadCourse(report.subjectId)
    } else if (report.kind === 'club') {
      onLoadClub(report.subjectId)
    } else if (report.kind === 'hole') {
      const hole = parseHoleSubject(report.subjectId)
      if (hole) onLoadHole(hole.courseKey, hole.hole)
    }
  }

  const diagnostics = useDiagnostics()
  return (
    <div className="report-inventory-row">
      <div className="report-inventory-main">
        <div className="report-inventory-title">
          <span className="fact-chip muted">{reportKindZh(report.kind)}</span>
          <strong>{reportSubjectZh(report.kind, report.subjectId)}</strong>
        </div>
        <div className="report-inventory-meta">
          {diagnostics ? <span>{report.provider}</span> : null}
          {diagnostics ? <span>{report.model}</span> : null}
          <span>{confidenceZh(report.confidence)} 置信</span>
        </div>
        <SourceRefs refs={report.sourceRefs} onSelectRef={onSelectRef} />
      </div>
      <button type="button" onClick={handleOpen} aria-label={`打开已存 ${reportKindZh(report.kind)} ${reportSubjectZh(report.kind, report.subjectId)}`}>
        打开
      </button>
    </div>
  )
}

function ReportDetail({ state, onSelectRef }: { state: ReportsPageProps['reportState']; onSelectRef?: (sourceRef: string) => void }) {
  if (state.status === 'loading') {
    return (
      <section className="report-detail" aria-label="报告详情">
        <h2>载入中</h2>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="report-detail" aria-label="报告详情">
        <h2>报告不可用</h2>
        <p>{state.message}</p>
      </section>
    )
  }

  if (state.status === 'idle') {
    return (
      <section className="report-detail" aria-label="报告详情">
        <h2>未选报告</h2>
        <p>选择趋势或球局报告以查看事实审查。</p>
      </section>
    )
  }

  const report = state.data
  const diagnostics = useDiagnostics()
  return (
    <section className="report-detail" aria-label="报告详情">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">{reportKindZh(report.kind)}</p>
          <h2>{reportSubjectZh(report.kind, report.subjectId)}</h2>
        </div>
        <span className={`confidence-pill ${report.confidence}`}>{confidenceZh(report.confidence)} 置信</span>
      </div>
      <section className="report-identity" aria-label="报告信息">
        {/* provider/model are AI infra — owner diagnostics only. */}
        {diagnostics ? <span className="fact-chip muted">供应方</span> : null}
        {diagnostics ? <span className="fact-chip">{report.provider}</span> : null}
        {diagnostics ? <span className="fact-chip muted">模型</span> : null}
        {diagnostics ? <span className="fact-chip">{report.model}</span> : null}
        <ReportFactBinding factBinding={report.factBinding} />
        <SourceRefs refs={report.sourceRefs} onSelectRef={onSelectRef} />
      </section>
      <p className="report-narrative">{report.narrative}</p>
      <p className="report-body-note">由 AI 生成</p>

      <div className="report-evidence-grid">
        <ReportInferences inferences={report.inferencesMade} onSelectRef={onSelectRef} />
        <UnsupportedClaims claims={report.unsupportedClaims} onSelectRef={onSelectRef} />
        <section aria-label="事实">
          <h3>事实</h3>
          {report.factsUsed.map((fact, index) => (
            <div className="report-row" key={`${String(fact.label)}-${index}`}>
              <div className="report-row-main">
                <strong>{String(fact.label ?? 'fact')}</strong>
                <span>{String(fact.source ?? 'source')}</span>
                <FactValue value={fact.value} />
                <ReportMetadata row={fact} confidenceLabel="事实置信" />
              </div>
              <SourceRefs refs={refsForFact(fact)} onSelectRef={onSelectRef} />
            </div>
          ))}
        </section>
        <section aria-label="缺失数据">
          <h3>缺失数据</h3>
          {report.missingData.length ? (
            report.missingData.map((item, index) => (
              <div className="report-row" key={`${String(item.label)}-${index}`}>
                <div className="report-row-main">
                  <strong>{String(item.label ?? 'missing')}</strong>
                  <span>{String(item.state ?? item.reason ?? '待复核')}</span>
                  <ReportMetadata row={item} confidenceLabel="缺失置信" />
                </div>
                <SourceRefs refs={refsForFact(item)} onSelectRef={onSelectRef} />
              </div>
            ))
          ) : (
            <p>无</p>
          )}
        </section>
      </div>
    </section>
  )
}

// factBinding.state is a closed bound/needs_review pair; unknown states keep
// the previous `${state} 绑定` raw shape.
const FACT_BINDING_ZH: Record<string, string> = {
  bound: '绑定正常',
  needs_review: '待复核',
}

function ReportFactBinding({ factBinding }: { factBinding: unknown }) {
  const row = factBinding && typeof factBinding === 'object' && !Array.isArray(factBinding) ? (factBinding as Record<string, unknown>) : {}
  const state = typeof row.state === 'string' && row.state.trim() ? row.state : 'bound'
  return <span className="fact-chip muted">{FACT_BINDING_ZH[state] ?? `${state} 绑定`}</span>
}

function UnsupportedClaims({
  claims,
  onSelectRef,
}: {
  claims: unknown
  onSelectRef?: (sourceRef: string) => void
}) {
  const rows = asRecordArray(claims)
  return (
    <section className="report-unsupported-claims" aria-label="无依据断言">
      <h3>无依据断言</h3>
      {rows.length ? (
        rows.map((claim, index) => (
          <div className="report-row" key={`${String(claim.category ?? 'claim')}-${index}`}>
            <div className="report-row-main">
              <strong>{String(claim.category ?? 'claim')}</strong>
              <span>{String(claim.claim ?? 'Unsupported claim')}</span>
              {typeof claim.reason === 'string' ? <span>{claim.reason}</span> : null}
              <div className="report-metadata">
                {labeledChips(claim.missingDataLabels, 'missing', '缺失')}
                {typeof claim.confidence === 'string' ? (
                  <span className="fact-chip muted">{`${confidenceZh(claim.confidence)} 断言置信`}</span>
                ) : null}
              </div>
            </div>
            <SourceRefs refs={claimRefs(claim)} onSelectRef={onSelectRef} />
          </div>
        ))
      ) : (
        <p>无</p>
      )}
    </section>
  )
}

function ReportInferences({
  inferences,
  onSelectRef,
}: {
  inferences: unknown
  onSelectRef?: (sourceRef: string) => void
}) {
  const rows = asRecordArray(inferences)
  return (
    <section className="report-inferences" aria-label="推断">
      <h3>推断</h3>
      {rows.length ? (
        rows.map((inference, index) => (
          <div className="report-row" key={`${String(inference.claim ?? 'inference')}-${index}`}>
            <div className="report-row-main">
              <strong>{String(inference.claim ?? 'Inference')}</strong>
              <div className="report-metadata">
                {labeledChips(inference.factLabels, 'fact', '事实')}
                {labeledChips(inference.missingDataLabels, 'missing', '缺失')}
                {typeof inference.confidence === 'string' ? (
                  <span className="fact-chip muted">{`${confidenceZh(inference.confidence)} 推断置信`}</span>
                ) : null}
              </div>
            </div>
            <SourceRefs refs={inferenceRefs(inference)} onSelectRef={onSelectRef} />
          </div>
        ))
      ) : (
        <p>无</p>
      )}
    </section>
  )
}

function ReportMetadata({ row, confidenceLabel }: { row: Record<string, unknown>; confidenceLabel: string }) {
  const coverage = metadataCoverage(row.coverage)
  const confidence = typeof row.confidence === 'string' ? row.confidence : null
  if (!coverage && !confidence) return null

  return (
    <div className="report-metadata">
      {coverage ? <span className="fact-chip muted">{coverage}</span> : null}
      {confidence ? <span className="fact-chip muted">{`${confidenceZh(confidence)} ${confidenceLabel}`}</span> : null}
    </div>
  )
}

function metadataCoverage(value: unknown): string | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const row = value as Record<string, unknown>
  const ready = typeof row.ready === 'number' ? row.ready : null
  const total = typeof row.total === 'number' ? row.total : null
  const pct = typeof row.pct === 'number' ? row.pct : null
  if (ready === null || total === null) return null
  return `覆盖率 ${ready}/${total}${pct === null ? '' : ` ${pct}%`}`
}

function FactValue({ value }: { value: unknown }) {
  if (value === undefined || value === null) return null
  if (Array.isArray(value)) return <FactArray rows={value} />
  if (typeof value === 'object') return <FactObject value={value as Record<string, unknown>} />
  return <div className="fact-value">{formatFactPrimitive(value)}</div>
}

function FactArray({ rows }: { rows: unknown[] }) {
  const displayRows = rows.slice(0, 4)
  return (
    <div className="fact-array">
      {displayRows.map((row, index) => {
        if (row && typeof row === 'object' && !Array.isArray(row)) {
          return <FactObject key={factObjectKey(row as Record<string, unknown>, index)} value={row as Record<string, unknown>} compact />
        }
        return (
          <span className="fact-chip" key={`${String(row)}-${index}`}>
            {formatFactPrimitive(row)}
          </span>
        )
      })}
      {rows.length > displayRows.length ? <span className="fact-chip muted">等 {rows.length - displayRows.length} 处</span> : null}
    </div>
  )
}

function FactObject({ value, compact = false }: { value: Record<string, unknown>; compact?: boolean }) {
  const entries = Object.entries(value).filter(([, item]) => isRenderableFactPrimitive(item))
  if (!entries.length) return null
  return (
    <div className={compact ? 'fact-object compact' : 'fact-object'}>
      {entries.map(([key, item]) => (
        <span className="fact-chip" key={key}>
          {formatFactPair(key, item)}
        </span>
      ))}
    </div>
  )
}

function isRenderableFactPrimitive(value: unknown): boolean {
  return value === null || ['string', 'number', 'boolean'].includes(typeof value)
}

function formatFactPair(key: string, value: unknown): string {
  const rendered = formatFactPrimitive(value, key)
  if (key === 'course') return rendered
  return `${key} ${rendered}`
}

function formatFactPrimitive(value: unknown, key = ''): string {
  if (value === null) return '无'
  if (typeof value === 'number') {
    if (key === 'toPar' && value > 0) return `+${value}`
    return String(value)
  }
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

function factObjectKey(value: Record<string, unknown>, index: number): string {
  const ref = value.holeRef ?? value.shotRef ?? value.roundRef ?? value.id
  return `${String(ref ?? 'row')}-${index}`
}

// Quarter keys are `{year}-Q{n}` (history_stats byQuarter) → 「2026年Q2」;
// other keys (e.g. 'unknown') keep the previous raw shape.
function quarterLabelZh(key: string): string {
  const match = /^(\d{4})-Q(\d)$/.exec(key)
  return match ? `${match[1]}年Q${match[2]}` : `Q ${key}`
}

function buildTrendOptions(stats: HistoryStatsResponse): Option[] {
  const options: Option[] = [{ id: 'recent_10', label: '近10场' }]
  for (const row of asRecordArray(stats.time.byQuarter)) {
    const key = String(row.key ?? '')
    if (key) options.push({ id: `quarter:${key}`, label: quarterLabelZh(key) })
  }
  for (const row of asRecordArray(stats.time.byYear)) {
    const key = String(row.key ?? row.year ?? '')
    if (key) options.push({ id: `year:${key}`, label: `${key}年` })
  }
  return options
}

function buildRoundOptions(stats: HistoryStatsResponse): Option[] {
  const drillDown = stats.drillDown
  const refs = Array.isArray(drillDown.roundRefs)
    ? drillDown.roundRefs
    : Array.isArray(drillDown.roundIds)
      ? drillDown.roundIds
      : []
  return refs.map((ref) => ({ id: String(ref), label: String(ref) }))
}

function buildCourseOptions(stats: HistoryStatsResponse): Option[] {
  const labels = new Map<string, string>()
  for (const row of [...asRecordArray(stats.courses), ...asRecordArray(stats.courseDistribution)]) {
    const courseKey = stringField(row, 'courseKey')
    if (!courseKey || labels.has(courseKey)) continue
    labels.set(courseKey, stringField(row, 'courseName') || courseKey)
  }
  return Array.from(labels.entries()).map(([id, label]) => ({ id, label }))
}

function buildHoleOptions(stats: HistoryStatsResponse): HoleOption[] {
  const courseLabels = new Map(buildCourseOptions(stats).map((option) => [option.id, option.label]))
  const options: HoleOption[] = []
  const seen = new Set<string>()
  for (const row of asRecordArray(stats.holes)) {
    const courseKey = stringField(row, 'courseKey')
    const hole = numberField(row, 'hole')
    if (!courseKey || hole === null) continue
    const id = `${courseKey}:${hole}`
    if (seen.has(id)) continue
    seen.add(id)
    const courseLabel = courseLabels.get(courseKey) ?? courseKey
    options.push({ id, courseKey, hole, label: `${courseLabel} H${hole}` })
  }
  return options
}

function buildClubOptions(stats: HistoryStatsResponse): Option[] {
  const options: Option[] = []
  const seen = new Set<string>()
  for (const row of asRecordArray(stats.clubs)) {
    const clubName = stringField(row, 'club') || stringField(row, 'clubName')
    if (!clubName || seen.has(clubName)) continue
    seen.add(clubName)
    options.push({ id: clubName, label: clubName })
  }
  return options
}

function parseHoleSubject(subjectId: string): { courseKey: string; hole: number } | null {
  const divider = subjectId.lastIndexOf(':')
  if (divider <= 0 || divider === subjectId.length - 1) return null
  const courseKey = subjectId.slice(0, divider)
  const hole = Number(subjectId.slice(divider + 1))
  if (!courseKey || !Number.isInteger(hole) || hole <= 0) return null
  return { courseKey, hole }
}

function stringField(row: Record<string, unknown>, key: string): string {
  return typeof row[key] === 'string' ? row[key].trim() : ''
}

function numberField(row: Record<string, unknown>, key: string): number | null {
  const value = row[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function asRecordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object') : []
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item).trim()).filter(Boolean)
}

function labeledChips(value: unknown, suffix: string, displaySuffix?: string) {
  return asStringArray(value).map((label) => (
    <span className="fact-chip muted" key={`${suffix}-${label}`}>
      {`${label} ${displaySuffix ?? suffix}`}
    </span>
  ))
}

function inferenceRefs(inference: Record<string, unknown>): string[] {
  return uniqueStrings([...asStringArray(inference.sourceRefs), ...asStringArray(inference.missingDataRefs)])
}

function claimRefs(claim: Record<string, unknown>): string[] {
  return uniqueStrings([...asStringArray(claim.sourceRefs), ...asStringArray(claim.missingDataRefs)])
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

function refsForFact(fact: Record<string, unknown>): string[] {
  return collectRefs(fact)
}

function collectRefs(value: unknown): string[] {
  const refs: string[] = []
  const seen = new Set<string>()

  function add(ref: unknown) {
    const normalized = String(ref ?? '').trim()
    if (!normalized || seen.has(normalized)) return
    seen.add(normalized)
    refs.push(normalized)
  }

  function walk(current: unknown, keyHint = '') {
    if (Array.isArray(current)) {
      if (isRefKey(keyHint)) {
        current.forEach(add)
        return
      }
      current.forEach((item) => walk(item))
      return
    }

    if (typeof current === 'string' && isRefKey(keyHint)) {
      add(current)
      return
    }

    if (current === null || typeof current !== 'object') return

    Object.entries(current).forEach(([key, item]) => {
      if (isRefKey(key)) {
        if (Array.isArray(item)) item.forEach(add)
        else add(item)
      } else {
        walk(item, key)
      }
    })
  }

  walk(value)
  return refs
}

function isRefKey(key: string) {
  return /^(refs|sourceRefs|roundRefs|holeRefs|shotRefs|missingDataRefs|roundIds|roundRef|holeRef|shotRef|missingDataRef)$/i.test(key)
}
