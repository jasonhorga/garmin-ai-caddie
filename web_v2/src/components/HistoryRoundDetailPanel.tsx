import type { CSSProperties } from 'react'
import type { AnnotationRecord, AnnotationTargetType, HistoryRoundDetailResponse, ReviewReportResponse } from '../types'
import { phaseZh } from '../zhLabels'
import { SourceRefs } from './SourceRefs'

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
  if (from && to) return `${from} -> ${to}`
  const text = compactValue(record.payload.text) ?? compactValue(record.payload.note)
  if (text) return text
  return valueText(record.payload)
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

function RoundFacts({ data }: { data: HistoryRoundDetailResponse }) {
  const round = data.round ?? {}
  const coverage = typeof round.coverage === 'object' && round.coverage !== null ? round.coverage as Record<string, unknown> : {}
  const facts: Array<[string, unknown]> = [
    ['成绩', round.score],
    ['对标准杆', toParText(round.toPar)],
    ['洞数', round.holesScored ?? round.holesCompleted],
    ['击球数', round.shotCount],
    ['记分卡', coverage.scorecard],
    ['击球数据', coverage.shots],
    ['推杆数', coverage.putts],
    ['置信度', round.confidence],
  ]

  return (
    <section className="round-detail-facts" aria-label="球局数据">
      {facts.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <b>{valueText(value)}</b>
        </div>
      ))}
    </section>
  )
}

function ScorecardGrid({ data, onSelectRef }: { data: HistoryRoundDetailResponse; onSelectRef?: (sourceRef: string) => void }) {
  if (data.scorecard.length === 0) return null
  return (
    <section className="round-detail-section" aria-label="记分卡">
      <div className="section-head">
        <div>
          <h3>记分卡</h3>
          <p>逐洞成绩、推杆数、果岭击球率、球道命中</p>
        </div>
      </div>
      <div className="round-detail-scorecard" style={{ '--round-detail-holes': Math.max(data.scorecard.length, 1) } as CSSProperties}>
        {data.scorecard.map((cell) => {
          const content = (
            <>
              <span>H{cell.hole}</span>
              <b>{cell.score ?? '-'}</b>
              <small>
                p{cell.par ?? '-'} / {toParText(cell.toPar)}
              </small>
              <em>{cell.putts === null ? 'putts -' : `${cell.putts} putts`}</em>
            </>
          )
          return onSelectRef ? (
            <button
              key={cell.holeRef}
              type="button"
              className={`round-detail-cell score-${cell.className}`}
              onClick={() => onSelectRef(cell.holeRef)}
              aria-label={`Open hole ${cell.hole} detail ${cell.holeRef}`}
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
            <b>{valueText(row.primary)}</b>
            <small>{valueText(row.state)}</small>
          </article>
        ))}
      </div>
    </section>
  )
}

function HoleDetails({ rows, onSelectRef }: { rows: Array<Record<string, unknown>>; onSelectRef?: (sourceRef: string) => void }) {
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
              <span>推杆</span>
              <b>{valueText(row.putts)}</b>
            </div>
            <div>
              <span>GIR</span>
              <b>{valueText(row.gir)}</b>
            </div>
            <div>
              <span>球道</span>
              <b>{valueText(row.fairway)}</b>
            </div>
            <div className="round-hole-sources">
              <span>击球</span>
              <SourceRefs refs={row.shotRefs} maxVisible={3} onSelectRef={onSelectRef} />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function RelatedSources({ data, onSelectRef }: { data: HistoryRoundDetailResponse; onSelectRef?: (sourceRef: string) => void }) {
  const groups = [
    ['Rounds', data.relatedRefs.roundRefs],
    ['Holes', data.relatedRefs.holeRefs],
    ['Shots', data.relatedRefs.shotRefs],
    ['Raw', data.relatedRefs.sourceRefs ?? []],
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

function MissingDataRows({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (rows.length === 0) return null
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
            {tag}
          </span>
        ))}
      </div>
    </section>
  )
}

function ShotSummary({ data }: { data: HistoryRoundDetailResponse }) {
  const round = data.round ?? {}
  const shotCount = typeof round.shotCount === 'number' ? round.shotCount : 0
  const holesWithShots = data.scorecard.filter((cell) => cell.shotRefs.length > 0).length
  const holesWithRoute = data.scorecard.filter((cell) => cell.shotRefs.length > 0 && cell.globalId != null && cell.localHole != null).length
  if (shotCount === 0 && holesWithShots === 0) return null
  const facts: Array<[string, string]> = [
    ['记录击球', String(shotCount)],
    ['有击球的洞数', String(holesWithShots)],
    ['有路径图的洞数', String(holesWithRoute)],
  ]
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
            <span>{row.kind}</span>
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
        {value.length > 4 ? <span className="fact-chip muted">+{value.length - 4} more</span> : null}
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
        <h4>Facts</h4>
        {facts.length ? (
          facts.map((fact, index) => (
            <div className="report-row" key={`${valueText(fact.label)}-${index}`}>
              <div className="report-row-main">
                <strong>{valueText(fact.label ?? 'fact')}</strong>
                <span>{valueText(fact.source ?? 'source')}</span>
                <EvidenceValue value={fact.value} />
              </div>
              <SourceRefs refs={evidenceRefs(fact)} onSelectRef={onSelectRef} />
            </div>
          ))
        ) : (
          <p>None</p>
        )}
      </section>

      <section aria-label="Round AI inferences">
        <h4>Inferences</h4>
        {inferences.length ? (
          inferences.map((inference, index) => (
            <div className="report-row" key={`${valueText(inference.claim)}-${index}`}>
              <div className="report-row-main">
                <strong>{valueText(inference.claim ?? 'Inference')}</strong>
                <div className="report-metadata">
                  {asStringArray(inference.factLabels).map((label) => <span key={`fact-${label}`} className="fact-chip muted">{label} fact</span>)}
                  {asStringArray(inference.missingDataLabels).map((label) => <span key={`missing-${label}`} className="fact-chip muted">{label} missing</span>)}
                  {typeof inference.confidence === 'string' ? <span className="fact-chip muted">{inference.confidence} inference confidence</span> : null}
                </div>
              </div>
              <SourceRefs refs={evidenceRefs(inference)} onSelectRef={onSelectRef} />
            </div>
          ))
        ) : (
          <p>None</p>
        )}
      </section>

      <section aria-label="Round AI missing data">
        <h4>Missing Data</h4>
        {missingData.length ? (
          missingData.map((item, index) => (
            <div className="report-row" key={`${valueText(item.label)}-${index}`}>
              <div className="report-row-main">
                <strong>{valueText(item.label ?? 'missing')}</strong>
                <span>{valueText(item.state ?? item.reason ?? 'needs review')}</span>
              </div>
              <SourceRefs refs={evidenceRefs(item)} onSelectRef={onSelectRef} />
            </div>
          ))
        ) : (
          <p>None</p>
        )}
      </section>

      <section aria-label="Round AI unsupported claims">
        <h4>Unsupported Claims</h4>
        {unsupportedClaims.length ? (
          unsupportedClaims.map((claim, index) => (
            <div className="report-row" key={`${valueText(claim.category)}-${index}`}>
              <div className="report-row-main">
                <strong>{valueText(claim.category ?? 'claim')}</strong>
                <span>{valueText(claim.claim ?? 'Unsupported claim')}</span>
                {typeof claim.reason === 'string' ? <span>{claim.reason}</span> : null}
              </div>
              <SourceRefs refs={evidenceRefs(claim)} onSelectRef={onSelectRef} />
            </div>
          ))
        ) : (
          <p>None</p>
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
}: {
  roundRef: string
  reportState?: HistoryRoundDetailPanelProps['reportState']
  onLoadRoundReport?: (roundRef: string) => void
  onGenerateRoundReport?: (roundRef: string) => void
  onSelectRef?: (sourceRef: string) => void
}) {
  if (!onLoadRoundReport && !onGenerateRoundReport && (!reportState || reportState.status === 'idle')) return null
  const loadedReport =
    reportState?.status === 'ready' &&
    reportState.data.kind === 'round' &&
    reportState.data.subjectId === roundRef
      ? reportState.data
      : null

  return (
    <section className="round-detail-section round-ai-review" aria-label="Round AI review">
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
            <span>{loadedReport.provider}</span>
            <span>{loadedReport.model}</span>
            <span>{loadedReport.confidence} confidence</span>
          </div>
          <p>{loadedReport.narrative}</p>
          <SourceRefs refs={loadedReport.sourceRefs} onSelectRef={onSelectRef} />
          <RoundAiEvidence report={loadedReport} onSelectRef={onSelectRef} />
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
  if (state.status === 'idle') return null

  if (state.status === 'loading') {
    return (
      <section className="panel round-detail-panel" aria-live="polite">
        <h2>球局回顾</h2>
        <p>Loading {state.roundRef}</p>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="panel round-detail-panel" aria-live="polite">
        <h2>球局回顾</h2>
        <p>{state.roundRef}</p>
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
    <section className="panel round-detail-panel" aria-live="polite">
      <div className="drilldown-title-row">
        <div>
          <p className="eyebrow">球局记分卡</p>
          <h2>{data.found ? '球局回顾' : '球局不可用'}</h2>
          <p>{data.title}</p>
        </div>
        <div className="drilldown-meta">
          <span>{data.roundRef}</span>
          <span>{data.found ? 'found' : 'not found'}</span>
          {canAnnotate ? (
            <button
              type="button"
              className="drilldown-action-button"
              onClick={() => onCreateAnnotationForRound?.({ targetType: 'round', targetId: data.roundRef })}
              aria-label={`Add correction for round ${data.roundRef}`}
            >
              添加订正
            </button>
          ) : null}
        </div>
      </div>

      {data.found ? <RoundFacts data={data} /> : null}
      {data.found ? <IssueTags annotations={data.annotations ?? []} /> : null}
      <ScorecardGrid data={data} onSelectRef={onSelectRef} />
      {data.found ? <ShotSummary data={data} /> : null}
      {data.found ? (
        <RoundAiReview
          roundRef={data.roundRef}
          reportState={reportState}
          onLoadRoundReport={onLoadRoundReport}
          onGenerateRoundReport={onGenerateRoundReport}
          onSelectRef={onSelectRef}
        />
      ) : null}
      <PhaseSummary rows={data.phaseSummary} />
      <HoleDetails rows={data.holeDetails} onSelectRef={onSelectRef} />
      <RelatedSources data={data} onSelectRef={onSelectRef} />
      <AnnotationRows title="球局标注" rows={data.annotations ?? []} />
      <AnnotationRows title="已应用订正" rows={data.corrections ?? []} />
      <MissingDataRows rows={data.missingData} />
    </section>
  )
}
