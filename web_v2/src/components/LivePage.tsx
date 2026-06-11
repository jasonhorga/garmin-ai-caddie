import { useEffect, useRef, useState, type ComponentProps } from 'react'
import type { AnnotationTargetType, CourseSearchResponse, HistoryRoundDetailResponse, MobileCourseOptionsResponse, RoundCard as RoundCardType } from '../types'
import { fetchHistoryRoundDetail } from '../api'
import { CaddiePage } from './CaddiePage'
import { HistoryRoundDetailPanel, type HistoryRoundDetailPanelState } from './HistoryRoundDetailPanel'
import { LiveSandbox } from './LiveSandbox'

// 实战 page shell (spec §5.4 web scope), three inner tabs in the PrepPage idiom
// (local tab state + subnav--inner classes, NOT SubNav — these tabs are not
// ProductPages): 决策沙盘 (default; course/hole simulation, sandbox lands in
// W3 T3/T4) / 最近回放 (recent-round replay) / 完整工具 — the EXISTING
// CaddiePage rendered VERBATIM so every media/audit/context tool stays
// reachable with zero functionality deleted.
interface LivePageProps {
  // 决策沙盘 course-pick entry (sandbox state machine consumes these in T3).
  courseOptions: MobileCourseOptionsResponse | null
  adminToken?: string
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>
  // 最近回放: recent-round picker rows + the EXISTING HistoryRoundDetailPanel
  // fed by a LivePage-local fetchHistoryRoundDetail state machine. The
  // drilldown/annotation/AI-review handlers below mirror EXACTLY what App
  // passes to the panel on the history pages, so 回放 source-ref clicks and AI
  // review behave the same there as here (App renders the drilldown panels
  // under LivePage). onRetryRound is deliberately NOT threaded: retries must
  // refetch the LivePage-local state, and the error path renders locally in
  // zh (重试) instead of the panel's English error view.
  recentRounds: RoundCardType[]
  reportState?: ComponentProps<typeof HistoryRoundDetailPanel>['reportState']
  onSelectRef?: (sourceRef: string) => void
  onCreateAnnotationForRound?: (target: { targetType: AnnotationTargetType; targetId: string }) => void
  onLoadRoundReport?: (roundRef: string) => void
  onGenerateRoundReport?: (roundRef: string) => void
  // 完整工具: CaddiePage's full props bundle, spread through untouched.
  // ComponentProps keeps this in lockstep with CaddiePage without exporting or
  // re-listing its private props interface.
  caddieProps: ComponentProps<typeof CaddiePage>
}

type LiveTab = 'sandbox' | 'replay' | 'tools'

const LIVE_TABS: Array<{ key: LiveTab; label: string }> = [
  { key: 'sandbox', label: '决策沙盘' },
  { key: 'replay', label: '最近回放' },
  { key: 'tools', label: '完整工具' },
]

// PrepPage PrepDone idiom: the fetch effect records only its settled result
// keyed by round+attempt; loading is DERIVED from a key mismatch, so the
// effect never sets state synchronously (react-hooks/set-state-in-effect).
interface ReplayDone {
  key: string
  result: { data: HistoryRoundDetailResponse } | { error: string }
}

// Row formatting matches the TrendsOverview 最近球局 rows (module-private
// helper idiom used across HomeOverview/TrendsOverview/RoundCard).
function formatToPar(value: number | null): string {
  if (value === null) return '—'
  return value > 0 ? `+${value}` : String(value)
}

function toParChipClass(value: number | null): string {
  if (value === null) return 'none'
  if (value <= 0) return 'under'
  if (value >= 18) return 'bigover'
  return 'over'
}

function dateLabel(value: string | null): string {
  return typeof value === 'string' && value.length >= 10 ? value.slice(5, 10) : '—'
}

export function LivePage({
  courseOptions,
  adminToken,
  onSearchCourses,
  recentRounds,
  reportState,
  onSelectRef,
  onCreateAnnotationForRound,
  onLoadRoundReport,
  onGenerateRoundReport,
  caddieProps,
}: LivePageProps) {
  const [tab, setTab] = useState<LiveTab>('sandbox')
  // 最近回放 state machine: replayRoundRef drives the detail fetch; attempt
  // bumps force a refetch (重试).
  const [replayRoundRef, setReplayRoundRef] = useState<string | null>(null)
  const [replayAttempt, setReplayAttempt] = useState(0)
  const [replayDone, setReplayDone] = useState<ReplayDone | null>(null)
  // The W1b seq-ref race guard (HomeOverview searchSeq idiom): a stale detail
  // response from an earlier round/attempt must never clobber the latest one
  // (a late stale write would regress the derived state to 加载中 forever).
  const replaySeq = useRef(0)

  // Lazy default selection (React "adjust state during render", PrepPage
  // idiom): the first time 最近回放 opens, pick the newest round. Nothing is
  // fetched while the tab stays closed.
  const firstRoundId = recentRounds[0]?.id ?? null
  if (tab === 'replay' && replayRoundRef === null && firstRoundId !== null) {
    setReplayRoundRef(firstRoundId)
  }

  useEffect(() => {
    if (replayRoundRef === null) return
    const key = `${replayRoundRef}:${replayAttempt}`
    const seq = ++replaySeq.current
    fetchHistoryRoundDetail(replayRoundRef, adminToken)
      .then((data) => {
        if (replaySeq.current !== seq) return
        setReplayDone({ key, result: { data } })
      })
      .catch((error: unknown) => {
        if (replaySeq.current !== seq) return
        setReplayDone({ key, result: { error: error instanceof Error ? error.message : '未知错误' } })
      })
  }, [replayRoundRef, adminToken, replayAttempt])

  const replayKey = replayRoundRef === null ? null : `${replayRoundRef}:${replayAttempt}`
  const replayState: HistoryRoundDetailPanelState =
    replayRoundRef === null || replayKey === null
      ? { status: 'idle' }
      : replayDone?.key !== replayKey
        ? { status: 'loading', roundRef: replayRoundRef }
        : 'data' in replayDone.result
          ? { status: 'ready', data: replayDone.result.data }
          : { status: 'error', roundRef: replayRoundRef, message: replayDone.result.error }

  // 决策沙盘 owns its whole state machine (course → prep fetch → hole picker →
  // ball drag → situation readout) in the LiveSandbox subcomponent.
  const sandboxContent = <LiveSandbox courseOptions={courseOptions} adminToken={adminToken} onSearchCourses={onSearchCourses} />

  const replayContent = (
    <>
      <section className="panel live-replay-list" aria-label="最近回放球局">
        <div className="trends-panel-head">
          <div>
            <h2>最近回放</h2>
            <span className="trends-panel-sub">选一场球局,逐洞回看</span>
          </div>
        </div>
        {recentRounds.length ? (
          recentRounds.map((round) => (
            <button
              key={round.id}
              type="button"
              className={round.id === replayRoundRef ? 'trends-round-row selected' : 'trends-round-row'}
              aria-current={round.id === replayRoundRef ? 'true' : undefined}
              onClick={() => setReplayRoundRef(round.id)}
              aria-label={`回放 ${round.courseName} ${dateLabel(round.date)}`}
            >
              <span className="trends-round-date">{dateLabel(round.date)}</span>
              <span className="trends-round-course">{round.courseName}</span>
              <span className="trends-round-score">{round.score ?? '—'}</span>
              <span className={`trends-pchip ${toParChipClass(round.toPar)}`}>{formatToPar(round.toPar)}</span>
            </button>
          ))
        ) : (
          <p className="trends-empty">还没有球局数据</p>
        )}
      </section>
      {replayState.status === 'error' ? (
        <section className="panel empty-state prep-load-error" aria-label="回放加载失败" aria-live="polite">
          <h2>回放加载失败</h2>
          <p>{replayState.message}</p>
          <button type="button" onClick={() => setReplayAttempt((attempt) => attempt + 1)}>
            重试
          </button>
        </section>
      ) : (
        <HistoryRoundDetailPanel
          state={replayState}
          reportState={reportState}
          onSelectRef={onSelectRef}
          onCreateAnnotationForRound={onCreateAnnotationForRound}
          onLoadRoundReport={onLoadRoundReport}
          onGenerateRoundReport={onGenerateRoundReport}
        />
      )}
    </>
  )

  return (
    <section className="live-page" aria-label="实战">
      <nav className="subnav subnav--inner" aria-label="实战页签">
        {LIVE_TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={tab === item.key ? 'subnav-tab active' : 'subnav-tab'}
            aria-current={tab === item.key ? 'page' : undefined}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      {tab === 'sandbox' ? sandboxContent : tab === 'replay' ? replayContent : <CaddiePage {...caddieProps} />}
    </section>
  )
}
