import { useEffect, useState } from 'react'
import {
  analyzeMedia,
  createCaddieDecisionAudit,
  createAnnotation,
  createMedia,
  fetchCaddieContext,
  fetchCaddieDecision,
  fetchAnnotations,
  fetchMediaForTarget,
  fetchHoleGeometryEvidence,
  fetchHoleMap,
  fetchHistoryDrilldown,
  fetchHistoryOverview,
  fetchHistoryRounds,
  fetchHistoryStats,
  fetchReadiness,
  fetchRoundReport,
  fetchTrendReport,
  fetchVisionFindingsForTarget,
  fetchWeatherSnapshot,
  generateRoundReport,
  generateTrendReport,
  fetchSyncStatus,
  runGarminSync,
} from './api'
import { CaddiePage, type MediaContextState } from './components/CaddiePage'
import { ClubStats } from './components/ClubStats'
import { CorrectionsPage } from './components/CorrectionsPage'
import { CourseStats } from './components/CourseStats'
import { DataQualityPage } from './components/DataQualityPage'
import { HistoryOverview } from './components/HistoryOverview'
import { HistoryDrilldownPanel, type HistoryDrilldownPanelState } from './components/HistoryDrilldownPanel'
import { HistoryTimeline } from './components/HistoryTimeline'
import { HoleEvidencePanel, type HoleEvidenceState } from './components/HoleEvidencePanel'
import { HoleStats } from './components/HoleStats'
import { IssueStats } from './components/IssueStats'
import { ProductNav } from './components/ProductNav'
import { ReadinessPanel } from './components/ReadinessPanel'
import { ReportsPage } from './components/ReportsPage'
import { SettingsPage } from './components/SettingsPage'
import { StatsOverview } from './components/StatsOverview'
import { SyncStatusPanel } from './components/SyncStatusPanel'
import type { ProductPage } from './components/ProductNav'
import type {
  AnnotationCreateRequest,
  AnnotationCreateResponse,
  AnnotationListResponse,
  CaddieContextParams,
  CaddieContextResponse,
  CaddieDecisionAuditRecord,
  CaddieDecisionRequest,
  CaddieDecisionResponse,
  HistoryOverviewResponse,
  HistoryDrilldownResponse,
  HistoryRoundsResponse,
  HistoryStatsResponse,
  MediaCreateRequest,
  MediaTargetType,
  ReadinessResponse,
  ReviewReportResponse,
  SyncStatusResponse,
  WeatherSnapshotResponse,
} from './types'

type LoadState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }

type DeferredLoadState<T> = { status: 'idle' } | LoadState<T>

const statsPages: ProductPage[] = ['history', 'courses', 'holes', 'clubs', 'issues', 'reports', 'sync-quality']

export default function App() {
  const [activePage, setActivePage] = useState<ProductPage>('overview')
  const [overviewState, setOverviewState] = useState<LoadState<HistoryOverviewResponse>>({ status: 'loading' })
  const [roundsState, setRoundsState] = useState<DeferredLoadState<HistoryRoundsResponse>>({ status: 'idle' })
  const [statsState, setStatsState] = useState<DeferredLoadState<HistoryStatsResponse>>({ status: 'idle' })
  const [annotationsState, setAnnotationsState] = useState<DeferredLoadState<AnnotationListResponse>>({ status: 'idle' })
  const [reportState, setReportState] = useState<DeferredLoadState<ReviewReportResponse>>({ status: 'idle' })
  const [readinessState, setReadinessState] = useState<DeferredLoadState<ReadinessResponse>>({ status: 'idle' })
  const [decisionState, setDecisionState] = useState<DeferredLoadState<CaddieDecisionResponse>>({ status: 'idle' })
  const [decisionAuditState, setDecisionAuditState] = useState<DeferredLoadState<CaddieDecisionAuditRecord | null>>({ status: 'idle' })
  const [weatherState, setWeatherState] = useState<DeferredLoadState<WeatherSnapshotResponse>>({ status: 'idle' })
  const [caddieContextState, setCaddieContextState] = useState<DeferredLoadState<CaddieContextResponse>>({ status: 'idle' })
  const [mediaState, setMediaState] = useState<MediaContextState>({ status: 'idle' })
  const [drilldownState, setDrilldownState] = useState<HistoryDrilldownPanelState>({ status: 'idle' })
  const [holeEvidenceState, setHoleEvidenceState] = useState<HoleEvidenceState>({ status: 'idle' })
  const [syncStatus, setSyncStatus] = useState<SyncStatusResponse | null>(null)
  const [syncRunState, setSyncRunState] = useState<'idle' | 'running' | 'error'>('idle')

  useEffect(() => {
    let cancelled = false

    fetchHistoryOverview()
      .then((data) => {
        if (!cancelled) setOverviewState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (!cancelled) setOverviewState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
      })

    fetchSyncStatus()
      .then((data) => {
        if (!cancelled) setSyncStatus(data)
      })
      .catch(() => {
        if (!cancelled) setSyncStatus(null)
      })

    return () => {
      cancelled = true
    }
  }, [])

  function navigate(page: ProductPage) {
    setActivePage(page)
    if (page === 'rounds' && roundsState.status === 'idle') {
      setRoundsState({ status: 'loading' })
      fetchHistoryRounds()
        .then((data) => setRoundsState({ status: 'ready', data }))
        .catch((error: unknown) =>
          setRoundsState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' }),
        )
    }
    if (statsPages.includes(page) && statsState.status === 'idle') {
      setStatsState({ status: 'loading' })
      fetchHistoryStats()
        .then((data) => setStatsState({ status: 'ready', data }))
        .catch((error: unknown) =>
          setStatsState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' }),
        )
    }
    if (page === 'sync-quality' && readinessState.status === 'idle') {
      setReadinessState({ status: 'loading' })
      fetchReadiness()
        .then((data) => setReadinessState({ status: 'ready', data }))
        .catch((error: unknown) =>
          setReadinessState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' }),
        )
    }
    if (page === 'corrections' && annotationsState.status === 'idle') {
      setAnnotationsState({ status: 'loading' })
      fetchAnnotations()
        .then((data) => setAnnotationsState({ status: 'ready', data }))
        .catch((error: unknown) =>
          setAnnotationsState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' }),
        )
    }
  }

  async function handleCreateAnnotation(request: AnnotationCreateRequest): Promise<AnnotationCreateResponse> {
    const response = await createAnnotation(request)
    setAnnotationsState((current) => {
      if (current.status !== 'ready') return current
      return {
        status: 'ready',
        data: {
          ...current.data,
          total: current.data.total + 1,
          annotations: [response.annotation, ...current.data.annotations],
        },
      }
    })
    return response
  }

  async function handleSelectSourceRef(sourceRef: string): Promise<HistoryDrilldownResponse | null> {
    setDrilldownState({ status: 'loading', sourceRef })
    setHoleEvidenceState({ status: 'idle' })
    try {
      const data = await fetchHistoryDrilldown(sourceRef)
      setDrilldownState({ status: 'ready', data })
      void loadHoleEvidenceForDrilldown(sourceRef, data)
      return data
    } catch (error: unknown) {
      setDrilldownState({
        status: 'error',
        sourceRef,
        message: error instanceof Error ? error.message : 'Unknown error',
      })
      setHoleEvidenceState({ status: 'idle' })
      return null
    }
  }

  async function loadHoleEvidenceForDrilldown(sourceRef: string, drilldown: HistoryDrilldownResponse) {
    const target = holeGeometryTargetFromDrilldown(sourceRef, drilldown)
    if (!target) {
      setHoleEvidenceState({ status: 'idle' })
      return
    }
    setHoleEvidenceState({ status: 'loading', sourceRef })
    try {
      const [evidence, map] = await Promise.all([
        fetchHoleGeometryEvidence(target.globalId, target.localHole),
        fetchHoleMap(target.globalId, target.localHole),
      ])
      setHoleEvidenceState({ status: 'ready', sourceRef, evidence, map })
    } catch (error: unknown) {
      setHoleEvidenceState({
        status: 'error',
        sourceRef,
        message: error instanceof Error ? error.message : 'Unknown error',
      })
    }
  }

  async function handleRunSync() {
    setSyncRunState('running')
    try {
      await runGarminSync({ withShots: true, forceRefreshAuth: false })
      const status = await fetchSyncStatus()
      setSyncStatus(status)
      setSyncRunState('idle')
    } catch {
      const status = await fetchSyncStatus().catch(() => null)
      if (status) setSyncStatus(status)
      setSyncRunState('error')
    }
  }

  function renderSyncPanel() {
    return syncStatus ? (
      <div className="app-shell sync-panel-shell">
        <SyncStatusPanel status={syncStatus} onSync={handleRunSync} syncState={syncRunState} />
      </div>
    ) : null
  }

  function renderDrilldownPanels() {
    if (drilldownState.status === 'idle' && holeEvidenceState.status === 'idle') return null
    return (
      <div className="app-shell">
        <HistoryDrilldownPanel state={drilldownState} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
        {holeEvidenceState.status === 'idle' ? null : <HoleEvidencePanel state={holeEvidenceState} />}
      </div>
    )
  }

  function renderStatsContent(data: HistoryStatsResponse) {
    if (activePage === 'courses') return <CourseStats data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
    if (activePage === 'holes') return <HoleStats data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
    if (activePage === 'clubs') return <ClubStats data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
    if (activePage === 'issues') return <IssueStats data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
    if (activePage === 'reports') {
      return (
        <ReportsPage
          stats={data}
          reportState={reportState}
          onLoadTrend={handleLoadTrendReport}
          onGenerateTrend={handleGenerateTrendReport}
          onLoadRound={handleLoadRoundReport}
          onGenerateRound={handleGenerateRoundReport}
          onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
        />
      )
    }
    if (activePage === 'sync-quality') {
      return (
        <section className="sync-quality-workspace" aria-label="Sync and data quality workspace">
          <div className="section-head stats-head">
            <div>
              <p className="eyebrow">Evidence Coverage</p>
              <h1>Sync & Data Quality</h1>
              <p>Garmin connector state, local snapshot coverage, and confidence-impacting gaps.</p>
            </div>
          </div>
          {syncStatus ? <SyncStatusPanel status={syncStatus} onSync={handleRunSync} syncState={syncRunState} /> : null}
          {readinessState.status === 'ready' ? <ReadinessPanel readiness={readinessState.data} /> : null}
          {readinessState.status === 'error' ? <ReadinessPanel readiness={null} error={readinessState.message} /> : null}
          <DataQualityPage data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
        </section>
      )
    }
    return <StatsOverview data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
  }

  async function loadReport(loader: () => Promise<ReviewReportResponse>) {
    setReportState({ status: 'loading' })
    try {
      const data = await loader()
      setReportState({ status: 'ready', data })
    } catch (error: unknown) {
      setReportState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
    }
  }

  function handleLoadTrendReport(period: string) {
    void loadReport(() => fetchTrendReport(period))
  }

  function handleGenerateTrendReport(period: string) {
    void loadReport(() => generateTrendReport(period))
  }

  function handleLoadRoundReport(roundId: string) {
    void loadReport(() => fetchRoundReport(roundId))
  }

  function handleGenerateRoundReport(roundId: string) {
    void loadReport(() => generateRoundReport(roundId))
  }

  async function handleRequestCaddieDecision(request: CaddieDecisionRequest) {
    setDecisionState({ status: 'loading' })
    setDecisionAuditState({ status: 'idle' })
    try {
      const data = await fetchCaddieDecision(request)
      setDecisionState({ status: 'ready', data })
    } catch (error: unknown) {
      setDecisionState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
    }
  }

  async function handleCreateDecisionAudit(decision: CaddieDecisionResponse, actualShot: Record<string, unknown>) {
    setDecisionAuditState({ status: 'loading' })
    try {
      const response = await createCaddieDecisionAudit(decisionIdFromDecision(decision), {
        decision,
        actualShot,
      })
      setDecisionAuditState({ status: 'ready', data: response.record })
    } catch (error: unknown) {
      setDecisionAuditState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
    }
  }

  async function handleLoadWeather() {
    setWeatherState({ status: 'loading' })
    try {
      const snapshot = await fetchWeatherSnapshot({
        source: 'manual',
        roundId: 'fixture-round',
        hole: 4,
        capturedAt: '2026-05-25T08:00:00Z',
        latitude: 22.279,
        longitude: 114.162,
        windSpeedMps: 5.4,
        windDirectionDeg: 110,
        temperatureC: 28.5,
        precipitationMm: 0,
      })
      setWeatherState({ status: 'ready', data: snapshot })
    } catch (error: unknown) {
      setWeatherState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
    }
  }

  async function handleLoadCaddieContext(params: CaddieContextParams) {
    setCaddieContextState({ status: 'loading' })
    try {
      const context = await fetchCaddieContext(params)
      setCaddieContextState({ status: 'ready', data: context })
    } catch (error: unknown) {
      setCaddieContextState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
    }
  }

  async function handleLoadMediaContext(target: { targetType: MediaTargetType; targetId: string }) {
    setMediaState({ status: 'loading', ...target })
    try {
      const [media, findings] = await Promise.all([
        fetchMediaForTarget(target.targetType, target.targetId),
        fetchVisionFindingsForTarget(target.targetType, target.targetId),
      ])
      setMediaState({
        status: 'ready',
        targetType: target.targetType,
        targetId: target.targetId,
        media: media.media,
        findings: findings.findings,
      })
    } catch (error: unknown) {
      setMediaState({
        status: 'error',
        targetType: target.targetType,
        targetId: target.targetId,
        message: error instanceof Error ? error.message : 'Unknown error',
      })
    }
  }

  async function handleAttachMedia(request: MediaCreateRequest) {
    const response = await createMedia(request)
    setMediaState((current) => {
      if (current.status === 'ready' && current.targetType === request.targetType && current.targetId === request.targetId) {
        return {
          ...current,
          media: [response.media, ...current.media],
        }
      }
      return {
        status: 'ready',
        targetType: request.targetType,
        targetId: request.targetId,
        media: [response.media],
        findings: [],
      }
    })
  }

  async function handleAnalyzeMedia(mediaId: string) {
    const target = mediaState.status === 'ready' ? { targetType: mediaState.targetType, targetId: mediaState.targetId } : null
    await analyzeMedia(mediaId)
    if (!target) return
    try {
      const findings = await fetchVisionFindingsForTarget(target.targetType, target.targetId)
      setMediaState((current) => {
        if (current.status !== 'ready' || current.targetType !== target.targetType || current.targetId !== target.targetId) return current
        return { ...current, findings: findings.findings }
      })
    } catch {
      return
    }
  }

  if (overviewState.status === 'loading') {
    return (
      <main className="app-shell">
        <section className="panel empty-state">
          <h1>Loading history</h1>
        </section>
      </main>
    )
  }

  if (overviewState.status === 'error') {
    return (
      <main className="app-shell">
        <section className="panel empty-state">
          <h1>History API unavailable</h1>
          <p>{overviewState.message}</p>
        </section>
      </main>
    )
  }

  if (activePage === 'rounds') {
    if (roundsState.status === 'ready') {
      return (
        <>
          {renderSyncPanel()}
          <HistoryTimeline data={roundsState.data} onNavigate={navigate} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
          {renderDrilldownPanels()}
        </>
      )
    }

    if (roundsState.status === 'error') {
      return (
        <main className="app-shell">
          <section className="panel empty-state">
            <h1>Rounds unavailable</h1>
            <p>{roundsState.message}</p>
          </section>
        </main>
      )
    }

    return (
      <main className="app-shell">
        <section className="panel empty-state">
          <h1>Loading rounds</h1>
        </section>
      </main>
    )
  }

  if (statsPages.includes(activePage)) {
    if (statsState.status === 'ready') {
      return (
        <>
          {activePage === 'sync-quality' ? null : renderSyncPanel()}
          <main className="app-shell">
            <ProductNav activePage={activePage} onNavigate={navigate} />
            {renderStatsContent(statsState.data)}
            <HistoryDrilldownPanel state={drilldownState} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
            {holeEvidenceState.status === 'idle' ? null : <HoleEvidencePanel state={holeEvidenceState} />}
          </main>
        </>
      )
    }

    if (statsState.status === 'error') {
      return (
        <main className="app-shell">
          <ProductNav activePage={activePage} onNavigate={navigate} />
          <section className="panel empty-state">
            <h1>History stats unavailable</h1>
            <p>{statsState.message}</p>
          </section>
        </main>
      )
    }

    return (
      <main className="app-shell">
        <ProductNav activePage={activePage} onNavigate={navigate} />
        <section className="panel empty-state">
          <h1>Loading history stats</h1>
        </section>
      </main>
    )
  }

  if (activePage === 'caddie') {
    return (
      <>
        {renderSyncPanel()}
        <main className="app-shell">
          <ProductNav activePage={activePage} onNavigate={navigate} />
          <CaddiePage
            decisionState={decisionState}
            auditState={decisionAuditState}
            weatherState={weatherState}
            contextState={caddieContextState}
            mediaState={mediaState}
            onRequestDecision={(request) => void handleRequestCaddieDecision(request)}
            onCreateAudit={(decision, actualShot) => void handleCreateDecisionAudit(decision, actualShot)}
            onLoadWeather={() => void handleLoadWeather()}
            onLoadCaddieContext={(params) => void handleLoadCaddieContext(params)}
            onLoadMediaContext={(target) => void handleLoadMediaContext(target)}
            onAttachMedia={handleAttachMedia}
            onAnalyzeMedia={(mediaId) => void handleAnalyzeMedia(mediaId)}
          />
        </main>
      </>
    )
  }

  if (activePage === 'settings') {
    return (
      <>
        {renderSyncPanel()}
        <main className="app-shell">
          <ProductNav activePage={activePage} onNavigate={navigate} />
          <SettingsPage onNavigate={navigate} />
        </main>
      </>
    )
  }

  if (activePage === 'corrections') {
    if (annotationsState.status === 'ready') {
      return (
        <>
          {renderSyncPanel()}
          <main className="app-shell">
            <ProductNav activePage="settings" onNavigate={navigate} />
            <CorrectionsPage data={annotationsState.data} onCreateAnnotation={handleCreateAnnotation} />
          </main>
        </>
      )
    }

    if (annotationsState.status === 'error') {
      return (
        <main className="app-shell">
          <ProductNav activePage="settings" onNavigate={navigate} />
          <section className="panel empty-state">
            <h1>Corrections unavailable</h1>
            <p>{annotationsState.message}</p>
          </section>
        </main>
      )
    }

    return (
      <main className="app-shell">
        <ProductNav activePage="settings" onNavigate={navigate} />
        <section className="panel empty-state">
          <h1>Loading corrections</h1>
        </section>
      </main>
    )
  }

  return (
    <>
      {renderSyncPanel()}
      <HistoryOverview data={overviewState.data} onNavigate={navigate} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
      {renderDrilldownPanels()}
    </>
  )
}

function decisionIdFromDecision(decision: CaddieDecisionResponse): string {
  const context = decision.context ?? {}
  const courseName = typeof context.courseName === 'string' ? context.courseName : 'fixture'
  const hole = typeof context.hole === 'number' || typeof context.hole === 'string' ? String(context.hole) : 'unknown'
  return [slug(courseName), hole, decision.shotType].join('-')
}

function holeGeometryTargetFromDrilldown(
  sourceRef: string,
  drilldown: HistoryDrilldownResponse,
): { globalId: number; localHole: number } | null {
  const globalId = numericField(drilldown.round, 'globalId')
  const localHole = numericField(drilldown.hole, 'number') ?? holeFromSourceRef(sourceRef)
  if (globalId === null || localHole === null) return null
  return { globalId, localHole }
}

function numericField(row: Record<string, unknown> | null, key: string): number | null {
  const value = row?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function holeFromSourceRef(sourceRef: string): number | null {
  const part = sourceRef.split(':')[1]
  if (!part) return null
  const value = Number(part)
  return Number.isFinite(value) ? value : null
}

function slug(value: string): string {
  const normalized = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  return normalized || 'fixture'
}
