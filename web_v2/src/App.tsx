import { useEffect, useRef, useState } from 'react'
import {
  analyzeMedia,
  confirmVisionFinding,
  createCaddieDecisionAudit,
  createAnnotation,
  createMedia,
  ensureHoleGeometry,
  fetchCaddieContext,
  fetchCaddieDecision,
  fetchLatestCaddieDecisionAudit,
  fetchAnnotations,
  fetchMediaForTarget,
  fetchHoleGeometryEvidence,
  fetchHoleMap,
  fetchHistoryDrilldown,
  fetchHistoryOverview,
  fetchHistoryRoundDetail,
  fetchHistoryRounds,
  fetchHistoryStats,
  fetchReadiness,
  fetchMobileCoursePackage,
  fetchMobileCourseOptions,
  fetchMobileReconciliation,
  fetchMobileRoundPackage,
  fetchProductSettings,
  fetchCourseReport,
  fetchReportIndex,
  fetchRoundReport,
  fetchHoleReport,
  fetchClubReport,
  fetchTrendReport,
  fetchVisionFindingsForTarget,
  fetchWeatherSnapshot,
  generateCourseReport,
  generateRoundReport,
  generateHoleReport,
  generateClubReport,
  generateTrendReport,
  applyMobileReconciliationSuggestions,
  fetchSyncStatus,
  redactMedia,
  runGarminSync,
  saveGarminSession,
} from './api'
import { CaddiePage, type MediaContextState } from './components/CaddiePage'
import { ClubStats } from './components/ClubStats'
import { CorrectionsPage, type CorrectionTarget } from './components/CorrectionsPage'
import { CourseStats } from './components/CourseStats'
import { DataQualityPage } from './components/DataQualityPage'
import { HistoryOverview } from './components/HistoryOverview'
import { HistoryDrilldownPanel, type HistoryDrilldownPanelState } from './components/HistoryDrilldownPanel'
import { HistoryRoundDetailPanel, type HistoryRoundDetailPanelState } from './components/HistoryRoundDetailPanel'
import { HistoryTimeline } from './components/HistoryTimeline'
import { HoleEvidencePanel, type GeometryEnsureState, type HoleEvidenceState } from './components/HoleEvidencePanel'
import { HoleStats } from './components/HoleStats'
import { IssueStats } from './components/IssueStats'
import {
  MobileReconciliationPanel,
  type MobileReconciliationApplyState,
  type MobileReconciliationPanelState,
} from './components/MobileReconciliationPanel'
import {
  MobilePackagePrepPanel,
  type MobilePackagePrepState,
} from './components/MobilePackagePrepPanel'
import { ProductNav } from './components/ProductNav'
import { CoursePrepPanel } from './components/CoursePrepPanel'
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
  HistoryRoundDetailResponse,
  HistoryRoundsResponse,
  HistoryStatsResponse,
  LiveRoundPackageResponse,
  MobileCourseOptionsResponse,
  MobileCoursePackageParams,
  MobileRoundPackageParams,
  MediaCreateRequest,
  MediaTargetType,
  ReadinessResponse,
  ReviewReportIndexResponse,
  ReviewReportResponse,
  GarminSessionImportRequest,
  MobileReconciliationApplyResponse,
  MobileReconciliationResponse,
  ProductSettingsResponse,
  SyncStatusResponse,
  WeatherSnapshotParams,
  WeatherSnapshotResponse,
  VisionConfirmationState,
} from './types'

type LoadState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }

type DeferredLoadState<T> = { status: 'idle' } | LoadState<T>
type HoleGeometryTarget = { globalId: number; localHole: number; sourceRef: string }

const statsPages: ProductPage[] = ['history', 'courses', 'holes', 'clubs', 'issues', 'reports', 'sync-quality']

export default function App() {
  const [activePage, setActivePage] = useState<ProductPage>('overview')
  const [overviewState, setOverviewState] = useState<LoadState<HistoryOverviewResponse>>({ status: 'loading' })
  const [roundsState, setRoundsState] = useState<DeferredLoadState<HistoryRoundsResponse>>({ status: 'idle' })
  const [statsState, setStatsState] = useState<DeferredLoadState<HistoryStatsResponse>>({ status: 'idle' })
  const [annotationsState, setAnnotationsState] = useState<DeferredLoadState<AnnotationListResponse>>({ status: 'idle' })
  const [reportState, setReportState] = useState<DeferredLoadState<ReviewReportResponse>>({ status: 'idle' })
  const [reportIndexState, setReportIndexState] = useState<DeferredLoadState<ReviewReportIndexResponse>>({ status: 'idle' })
  const [readinessState, setReadinessState] = useState<DeferredLoadState<ReadinessResponse>>({ status: 'idle' })
  const [productSettingsState, setProductSettingsState] = useState<DeferredLoadState<ProductSettingsResponse>>({ status: 'idle' })
  const [mobilePackagePrepState, setMobilePackagePrepState] = useState<MobilePackagePrepState>({ status: 'idle' })
  const [mobileCourseOptionsState, setMobileCourseOptionsState] = useState<DeferredLoadState<MobileCourseOptionsResponse>>({ status: 'idle' })
  const [mobileReconciliationState, setMobileReconciliationState] = useState<MobileReconciliationPanelState>({ status: 'idle' })
  const [mobileReconciliationApplyState, setMobileReconciliationApplyState] = useState<MobileReconciliationApplyState>({ status: 'idle' })
  const [decisionState, setDecisionState] = useState<DeferredLoadState<CaddieDecisionResponse>>({ status: 'idle' })
  const [decisionAuditState, setDecisionAuditState] = useState<DeferredLoadState<CaddieDecisionAuditRecord | null>>({ status: 'idle' })
  const [weatherState, setWeatherState] = useState<DeferredLoadState<WeatherSnapshotResponse>>({ status: 'idle' })
  const [caddieContextState, setCaddieContextState] = useState<DeferredLoadState<CaddieContextResponse>>({ status: 'idle' })
  const [mediaState, setMediaState] = useState<MediaContextState>({ status: 'idle' })
  const [selectedCaddieSourceRef, setSelectedCaddieSourceRef] = useState('900001:7')
  const [correctionTarget, setCorrectionTarget] = useState<CorrectionTarget | null>(null)
  const [roundDetailState, setRoundDetailState] = useState<HistoryRoundDetailPanelState>({ status: 'idle' })
  const [drilldownState, setDrilldownState] = useState<HistoryDrilldownPanelState>({ status: 'idle' })
  const [holeEvidenceState, setHoleEvidenceState] = useState<HoleEvidenceState>({ status: 'idle' })
  const [geometryEnsureState, setGeometryEnsureState] = useState<GeometryEnsureState>('idle')
  const activeHoleGeometryTarget = useRef<HoleGeometryTarget | null>(null)
  const activeDecisionAuditLookup = useRef<string | null>(null)
  const adminTokenRefreshTimer = useRef<number | null>(null)
  const [syncStatus, setSyncStatus] = useState<SyncStatusResponse | null>(null)
  const [syncRunState, setSyncRunState] = useState<'idle' | 'running' | 'error'>('idle')
  const [sessionSaveState, setSessionSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [sessionSaveError, setSessionSaveError] = useState<string | null>(null)
  const [adminToken, setAdminToken] = useState('')

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
      if (adminTokenRefreshTimer.current !== null) {
        window.clearTimeout(adminTokenRefreshTimer.current)
        adminTokenRefreshTimer.current = null
      }
    }
  }, [])

  function currentAdminToken(): string | undefined {
    const trimmed = adminToken.trim()
    return trimmed.length ? trimmed : undefined
  }

  function errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : 'Unknown error'
  }

  async function refreshOverviewState(adminTokenOverride: string | undefined = currentAdminToken()) {
    try {
      const data = await fetchHistoryOverview(adminTokenOverride)
      setOverviewState({ status: 'ready', data })
    } catch (error: unknown) {
      setOverviewState((current) => (current.status === 'ready' ? current : { status: 'error', message: errorMessage(error) }))
    }
  }

  async function loadRoundsState(adminTokenOverride: string | undefined = currentAdminToken()) {
    setRoundsState({ status: 'loading' })
    try {
      const data = await fetchHistoryRounds(adminTokenOverride)
      setRoundsState({ status: 'ready', data })
    } catch (error: unknown) {
      setRoundsState({ status: 'error', message: errorMessage(error) })
    }
  }

  async function refreshRoundsState(adminTokenOverride: string | undefined = currentAdminToken()) {
    try {
      const data = await fetchHistoryRounds(adminTokenOverride)
      setRoundsState({ status: 'ready', data })
    } catch (error: unknown) {
      setRoundsState((current) => (current.status === 'ready' ? current : { status: 'error', message: errorMessage(error) }))
    }
  }

  async function loadStatsState(adminTokenOverride: string | undefined = currentAdminToken()) {
    setStatsState({ status: 'loading' })
    try {
      const data = await fetchHistoryStats(adminTokenOverride)
      setStatsState({ status: 'ready', data })
    } catch (error: unknown) {
      setStatsState({ status: 'error', message: errorMessage(error) })
    }
  }

  async function refreshStatsState(adminTokenOverride: string | undefined = currentAdminToken()) {
    try {
      const data = await fetchHistoryStats(adminTokenOverride)
      setStatsState({ status: 'ready', data })
    } catch (error: unknown) {
      setStatsState((current) => (current.status === 'ready' ? current : { status: 'error', message: errorMessage(error) }))
    }
  }

  async function loadReadinessState() {
    setReadinessState({ status: 'loading' })
    try {
      const data = await fetchReadiness()
      setReadinessState({ status: 'ready', data })
    } catch (error: unknown) {
      setReadinessState({ status: 'error', message: errorMessage(error) })
    }
  }

  async function loadProductSettingsState() {
    setProductSettingsState({ status: 'loading' })
    try {
      const data = await fetchProductSettings()
      setProductSettingsState({ status: 'ready', data })
    } catch (error: unknown) {
      setProductSettingsState({ status: 'error', message: errorMessage(error) })
    }
  }

  async function refreshReadinessState() {
    try {
      const data = await fetchReadiness()
      setReadinessState({ status: 'ready', data })
    } catch (error: unknown) {
      setReadinessState((current) => (current.status === 'ready' ? current : { status: 'error', message: errorMessage(error) }))
    }
  }

  async function loadMobileCourseOptionsState(adminTokenOverride: string | undefined = currentAdminToken()) {
    setMobileCourseOptionsState({ status: 'loading' })
    try {
      const data = await fetchMobileCourseOptions(adminTokenOverride)
      setMobileCourseOptionsState({ status: 'ready', data })
    } catch (error: unknown) {
      setMobileCourseOptionsState({ status: 'error', message: errorMessage(error) })
    }
  }

  function refreshLoadedHistorySurfaces(adminTokenOverride: string | undefined = currentAdminToken()) {
    void refreshOverviewState(adminTokenOverride)
    if (roundsState.status !== 'idle') void refreshRoundsState(adminTokenOverride)
    if (statsState.status !== 'idle') void refreshStatsState(adminTokenOverride)
    if (readinessState.status !== 'idle') void refreshReadinessState()
    if (mobileCourseOptionsState.status !== 'idle') void loadMobileCourseOptionsState(adminTokenOverride)
    if (reportIndexState.status !== 'idle') loadReportIndex()
  }

  function handleAdminTokenChange(value: string) {
    setAdminToken(value)
    if (adminTokenRefreshTimer.current !== null) {
      window.clearTimeout(adminTokenRefreshTimer.current)
      adminTokenRefreshTimer.current = null
    }
    const nextToken = value.trim()
    if (nextToken && activePage === 'sync-quality' && mobileCourseOptionsState.status === 'error') {
      adminTokenRefreshTimer.current = window.setTimeout(() => {
        void loadMobileCourseOptionsState(nextToken)
        adminTokenRefreshTimer.current = null
      }, 250)
    }
  }

  function navigate(page: ProductPage) {
    if (page !== 'corrections') {
      setCorrectionTarget(null)
    }
    setActivePage(page)
    if (page === 'rounds' && roundsState.status === 'idle') {
      void loadRoundsState()
    }
    if (statsPages.includes(page) && statsState.status === 'idle') {
      void loadStatsState()
    }
    if (page === 'sync-quality' && readinessState.status === 'idle') {
      void loadReadinessState()
    }
    if (page === 'sync-quality' && mobileCourseOptionsState.status === 'idle') {
      void loadMobileCourseOptionsState()
    }
    if (page === 'settings' && productSettingsState.status === 'idle') {
      void loadProductSettingsState()
    }
    if (page === 'corrections' && annotationsState.status === 'idle') {
      setAnnotationsState({ status: 'loading' })
      fetchAnnotations(currentAdminToken())
        .then((data) => setAnnotationsState({ status: 'ready', data }))
        .catch((error: unknown) =>
          setAnnotationsState({ status: 'error', message: errorMessage(error) }),
        )
    }
    if (page === 'reports' && reportIndexState.status === 'idle') {
      loadReportIndex()
    }
  }

  function loadReportIndex() {
    setReportIndexState({ status: 'loading' })
    fetchReportIndex(currentAdminToken())
      .then((data) => setReportIndexState({ status: 'ready', data }))
      .catch((error: unknown) =>
        setReportIndexState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' }),
      )
  }

  async function handleCreateAnnotation(request: AnnotationCreateRequest): Promise<AnnotationCreateResponse> {
    const response = await createAnnotation(request, currentAdminToken())
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
    refreshLoadedHistorySurfaces()
    return response
  }

  function handleCreateAnnotationForSource(target: CorrectionTarget) {
    setCorrectionTarget(target)
    navigate('corrections')
  }

  async function handleSelectSourceRef(sourceRef: string): Promise<HistoryDrilldownResponse | null> {
    setSelectedCaddieSourceRef(sourceRef)
    setCaddieContextState((current) => (loadedCaddieContextSourceRef(current) === sourceRef.trim() ? current : { status: 'idle' }))
    setDrilldownState({ status: 'loading', sourceRef })
    setHoleEvidenceState({ status: 'idle' })
    setGeometryEnsureState('idle')
    activeHoleGeometryTarget.current = null
    try {
      const data = await fetchHistoryDrilldown(sourceRef, currentAdminToken())
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
      setGeometryEnsureState('idle')
      activeHoleGeometryTarget.current = null
      return null
    }
  }

  async function handleSelectRoundDetail(roundRef: string): Promise<HistoryRoundDetailResponse | null> {
    const cleanRef = roundRef.trim()
    setSelectedCaddieSourceRef(cleanRef)
    setCaddieContextState((current) => (loadedCaddieContextSourceRef(current) === cleanRef ? current : { status: 'idle' }))
    setRoundDetailState({ status: 'loading', roundRef: cleanRef })
    setDrilldownState({ status: 'idle' })
    setHoleEvidenceState({ status: 'idle' })
    setGeometryEnsureState('idle')
    activeHoleGeometryTarget.current = null
    try {
      const data = await fetchHistoryRoundDetail(cleanRef, currentAdminToken())
      setRoundDetailState({ status: 'ready', data })
      return data
    } catch (error: unknown) {
      setRoundDetailState({
        status: 'error',
        roundRef: cleanRef,
        message: error instanceof Error ? error.message : 'Unknown error',
      })
      return null
    }
  }

  async function loadHoleEvidenceForDrilldown(sourceRef: string, drilldown: HistoryDrilldownResponse) {
    const target = holeGeometryTargetFromDrilldown(sourceRef, drilldown)
    if (!target) {
      setHoleEvidenceState({ status: 'idle' })
      setGeometryEnsureState('idle')
      activeHoleGeometryTarget.current = null
      return
    }
    await loadHoleEvidenceForTarget({ ...target, sourceRef })
  }

  async function loadHoleEvidenceForTarget(target: HoleGeometryTarget) {
    activeHoleGeometryTarget.current = target
    setHoleEvidenceState({ status: 'loading', sourceRef: target.sourceRef })
    try {
      const [evidence, map] = await Promise.all([
        fetchHoleGeometryEvidence(target.globalId, target.localHole, target.sourceRef),
        fetchHoleMap(target.globalId, target.localHole, 'esri_world_imagery', target.sourceRef),
      ])
      if (!sameHoleGeometryTarget(activeHoleGeometryTarget.current, target)) return
      setHoleEvidenceState({ status: 'ready', sourceRef: target.sourceRef, evidence, map })
    } catch (error: unknown) {
      if (!sameHoleGeometryTarget(activeHoleGeometryTarget.current, target)) return
      setHoleEvidenceState({
        status: 'error',
        sourceRef: target.sourceRef,
        message: error instanceof Error ? error.message : 'Unknown error',
      })
    }
  }

  async function handleEnsureHoleGeometry(target: { globalId: number; localHole: number; sourceRef: string }) {
    setGeometryEnsureState('running')
    try {
      await ensureHoleGeometry(target.globalId, target.localHole, {}, currentAdminToken())
      if (!sameHoleGeometryTarget(activeHoleGeometryTarget.current, target)) return
      await loadHoleEvidenceForTarget(target)
      if (readinessState.status !== 'idle') void refreshReadinessState()
      if (statsState.status !== 'idle') void refreshStatsState()
      setGeometryEnsureState('ready')
    } catch {
      setGeometryEnsureState('error')
    }
  }

  async function handleRunSync(adminToken?: string) {
    setSyncRunState('running')
    try {
      await runGarminSync({ withShots: true, forceRefreshAuth: false, adminToken: adminToken ?? currentAdminToken() })
      const status = await fetchSyncStatus()
      setSyncStatus(status)
      refreshLoadedHistorySurfaces()
      setSyncRunState('idle')
    } catch {
      const status = await fetchSyncStatus().catch(() => null)
      if (status) setSyncStatus(status)
      setSyncRunState('error')
    }
  }

  async function handleSaveGarminSession(request: GarminSessionImportRequest, adminToken?: string) {
    setSessionSaveState('saving')
    setSessionSaveError(null)
    try {
      await saveGarminSession(request, adminToken ?? currentAdminToken())
      const status = await fetchSyncStatus()
      setSyncStatus(status)
      refreshLoadedHistorySurfaces()
      setSessionSaveState('saved')
    } catch (error: unknown) {
      setSessionSaveError(error instanceof Error ? error.message : 'Unknown error')
      setSessionSaveState('error')
      throw error
    }
  }

  function renderSyncPanel() {
    return syncStatus ? (
      <div className="app-shell sync-panel-shell">
        <SyncStatusPanel
          status={syncStatus}
          onSync={handleRunSync}
          syncState={syncRunState}
          onSaveSession={handleSaveGarminSession}
          sessionSaveState={sessionSaveState}
          sessionSaveError={sessionSaveError}
          adminTokenValue={adminToken}
          onAdminTokenChange={handleAdminTokenChange}
        />
      </div>
    ) : null
  }

  function renderDrilldownPanels() {
    if (roundDetailState.status === 'idle' && drilldownState.status === 'idle' && holeEvidenceState.status === 'idle') return null
    return (
      <div className="app-shell">
        <HistoryRoundDetailPanel
          state={roundDetailState}
          reportState={reportState}
          onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
          onRetryRound={(roundRef) => void handleSelectRoundDetail(roundRef)}
          onCreateAnnotationForRound={handleCreateAnnotationForSource}
          onLoadRoundReport={handleLoadRoundReport}
          onGenerateRoundReport={handleGenerateRoundReport}
        />
        <HistoryDrilldownPanel
          state={drilldownState}
          onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
          onRetrySource={(sourceRef) => void handleSelectSourceRef(sourceRef)}
          onCreateAnnotationForSource={handleCreateAnnotationForSource}
        />
        {holeEvidenceState.status === 'idle' ? null : (
          <HoleEvidencePanel
            state={holeEvidenceState}
            ensureState={geometryEnsureState}
            onEnsureGeometry={(target) => void handleEnsureHoleGeometry(target)}
          />
        )}
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
          reportIndexState={reportIndexState}
          onLoadTrend={handleLoadTrendReport}
          onGenerateTrend={handleGenerateTrendReport}
          onLoadRound={handleLoadRoundReport}
          onGenerateRound={handleGenerateRoundReport}
          onLoadCourse={handleLoadCourseReport}
          onGenerateCourse={handleGenerateCourseReport}
          onLoadHole={handleLoadHoleReport}
          onGenerateHole={handleGenerateHoleReport}
          onLoadClub={handleLoadClubReport}
          onGenerateClub={handleGenerateClubReport}
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
          {syncStatus ? (
            <SyncStatusPanel
              status={syncStatus}
              onSync={handleRunSync}
              syncState={syncRunState}
              onSaveSession={handleSaveGarminSession}
              sessionSaveState={sessionSaveState}
              sessionSaveError={sessionSaveError}
              adminTokenValue={adminToken}
              onAdminTokenChange={handleAdminTokenChange}
            />
          ) : null}
          <MobilePackagePrepPanel
            state={mobilePackagePrepState}
            courseOptionsState={mobileCourseOptionsState}
            onPrepareRound={(roundId, params) => void handlePrepareMobileRoundPackage(roundId, params)}
            onPrepareCourse={(globalId, params) => void handlePrepareMobileCoursePackage(globalId, params)}
            showAdminTokenInput={!syncStatus}
            adminTokenValue={adminToken}
            onAdminTokenChange={handleAdminTokenChange}
          />
          <MobileReconciliationPanel
            state={mobileReconciliationState}
            applyState={mobileReconciliationApplyState}
            onLoad={(roundId) => void handleLoadMobileReconciliation(roundId)}
            onApply={(roundId, suggestionIds) => void handleApplyMobileReconciliation(roundId, suggestionIds)}
          />
          {readinessState.status === 'ready' ? <ReadinessPanel readiness={readinessState.data} /> : null}
          {readinessState.status === 'error' ? <ReadinessPanel readiness={null} error={readinessState.message} /> : null}
          <DataQualityPage data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
        </section>
      )
    }
    return <StatsOverview data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
  }

  async function loadReport(loader: () => Promise<ReviewReportResponse>, refreshIndex = false) {
    setReportState({ status: 'loading' })
    try {
      const data = await loader()
      setReportState({ status: 'ready', data })
      if (refreshIndex) loadReportIndex()
    } catch (error: unknown) {
      setReportState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
    }
  }

  function handleLoadTrendReport(period: string) {
    void loadReport(() => fetchTrendReport(period, currentAdminToken()))
  }

  function handleGenerateTrendReport(period: string) {
    void loadReport(() => generateTrendReport(period, currentAdminToken()), true)
  }

  function handleLoadRoundReport(roundId: string) {
    void loadReport(() => fetchRoundReport(roundId, currentAdminToken()))
  }

  function handleGenerateRoundReport(roundId: string) {
    void loadReport(() => generateRoundReport(roundId, currentAdminToken()), true)
  }

  function handleLoadCourseReport(courseKey: string) {
    void loadReport(() => fetchCourseReport(courseKey, currentAdminToken()))
  }

  function handleGenerateCourseReport(courseKey: string) {
    void loadReport(() => generateCourseReport(courseKey, currentAdminToken()), true)
  }

  function handleLoadHoleReport(courseKey: string, hole: number) {
    void loadReport(() => fetchHoleReport(courseKey, hole, currentAdminToken()))
  }

  function handleGenerateHoleReport(courseKey: string, hole: number) {
    void loadReport(() => generateHoleReport(courseKey, hole, currentAdminToken()), true)
  }

  function handleLoadClubReport(clubName: string) {
    void loadReport(() => fetchClubReport(clubName, currentAdminToken()))
  }

  function handleGenerateClubReport(clubName: string) {
    void loadReport(() => generateClubReport(clubName, currentAdminToken()), true)
  }

  async function handlePrepareMobileRoundPackage(
    roundId: string,
    params: MobileRoundPackageParams,
  ): Promise<LiveRoundPackageResponse | null> {
    setMobilePackagePrepState({ status: 'loading', mode: 'round', target: roundId })
    try {
      const data = await fetchMobileRoundPackage(roundId, params, currentAdminToken())
      setMobilePackagePrepState({ status: 'ready', data })
      if (readinessState.status !== 'idle') void refreshReadinessState()
      return data
    } catch (error: unknown) {
      setMobilePackagePrepState({
        status: 'error',
        mode: 'round',
        target: roundId,
        message: error instanceof Error ? error.message : 'Unknown error',
      })
      return null
    }
  }

  async function handlePrepareMobileCoursePackage(
    globalId: number,
    params: MobileCoursePackageParams,
  ): Promise<LiveRoundPackageResponse | null> {
    setMobilePackagePrepState({ status: 'loading', mode: 'course', target: String(globalId) })
    try {
      const data = await fetchMobileCoursePackage(globalId, params, currentAdminToken())
      setMobilePackagePrepState({ status: 'ready', data })
      if (readinessState.status !== 'idle') void refreshReadinessState()
      return data
    } catch (error: unknown) {
      setMobilePackagePrepState({
        status: 'error',
        mode: 'course',
        target: String(globalId),
        message: error instanceof Error ? error.message : 'Unknown error',
      })
      return null
    }
  }

  async function handleLoadMobileReconciliation(roundId: string): Promise<MobileReconciliationResponse | null> {
    setMobileReconciliationState({ status: 'loading', roundId })
    setMobileReconciliationApplyState({ status: 'idle' })
    try {
      const data = await fetchMobileReconciliation(roundId, currentAdminToken())
      setMobileReconciliationState({ status: 'ready', data })
      return data
    } catch (error: unknown) {
      setMobileReconciliationState({
        status: 'error',
        roundId,
        message: error instanceof Error ? error.message : 'Unknown error',
      })
      return null
    }
  }

  async function handleApplyMobileReconciliation(
    roundId: string,
    suggestionIds: string[],
  ): Promise<MobileReconciliationApplyResponse | null> {
    setMobileReconciliationApplyState({ status: 'applying' })
    try {
      const data = await applyMobileReconciliationSuggestions(roundId, suggestionIds, currentAdminToken())
      setMobileReconciliationApplyState({ status: 'ready', data })
      refreshLoadedHistorySurfaces()
      return data
    } catch (error: unknown) {
      setMobileReconciliationApplyState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
      return null
    }
  }

  async function handleRequestCaddieDecision(request: CaddieDecisionRequest) {
    setDecisionState({ status: 'loading' })
    setDecisionAuditState({ status: 'idle' })
    try {
      const data = await fetchCaddieDecision(request, currentAdminToken())
      setDecisionState({ status: 'ready', data })
      void loadLatestDecisionAudit(data)
    } catch (error: unknown) {
      setDecisionState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
    }
  }

  async function loadLatestDecisionAudit(decision: CaddieDecisionResponse) {
    const decisionId = decisionIdFromDecision(decision)
    activeDecisionAuditLookup.current = decisionId
    setDecisionAuditState({ status: 'loading' })
    try {
      const response = await fetchLatestCaddieDecisionAudit(decisionId, currentAdminToken())
      if (activeDecisionAuditLookup.current !== decisionId) return
      setDecisionAuditState({ status: 'ready', data: response.record ?? null })
    } catch (error: unknown) {
      if (activeDecisionAuditLookup.current !== decisionId) return
      setDecisionAuditState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
    }
  }

  async function handleCreateDecisionAudit(decision: CaddieDecisionResponse, actualShot: Record<string, unknown>) {
    const decisionId = decisionIdFromDecision(decision)
    activeDecisionAuditLookup.current = decisionId
    setDecisionAuditState({ status: 'loading' })
    try {
      const response = await createCaddieDecisionAudit(
        decisionId,
        decisionAuditRequest(decision, actualShot),
        currentAdminToken(),
      )
      setDecisionAuditState({ status: 'ready', data: response.record })
    } catch (error: unknown) {
      setDecisionAuditState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
    }
  }

  async function handleLoadWeather(params: WeatherSnapshotParams = {}) {
    setWeatherState({ status: 'loading' })
    try {
      const snapshot = await fetchWeatherSnapshot(
        params,
        currentAdminToken(),
      )
      setWeatherState({ status: 'ready', data: snapshot })
    } catch (error: unknown) {
      setWeatherState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
    }
  }

  async function handleLoadCaddieContext(params: CaddieContextParams) {
    setCaddieContextState({ status: 'loading' })
    try {
      const context = await fetchCaddieContext(params, currentAdminToken())
      setCaddieContextState({ status: 'ready', data: context })
    } catch (error: unknown) {
      setCaddieContextState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
    }
  }

  async function handleLoadMediaContext(target: { targetType: MediaTargetType; targetId: string }) {
    setMediaState({ status: 'loading', ...target })
    try {
      const [media, findings] = await Promise.all([
        fetchMediaForTarget(target.targetType, target.targetId, currentAdminToken()),
        fetchVisionFindingsForTarget(target.targetType, target.targetId, currentAdminToken()),
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
    const response = await createMedia(request, currentAdminToken())
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
    await analyzeMedia(mediaId, currentAdminToken())
    if (!target) return
    try {
      const findings = await fetchVisionFindingsForTarget(target.targetType, target.targetId, currentAdminToken())
      setMediaState((current) => {
        if (current.status !== 'ready' || current.targetType !== target.targetType || current.targetId !== target.targetId) return current
        return { ...current, findings: findings.findings }
      })
    } catch {
      return
    }
  }

  async function handleRedactMedia(mediaId: string) {
    const response = await redactMedia(mediaId, currentAdminToken())
    setMediaState((current) => {
      if (current.status !== 'ready') return current
      return {
        ...current,
        media: current.media.map((item) => (item.id === mediaId ? response.media : item)),
        findings: current.findings.filter((finding) => finding.mediaId !== mediaId),
      }
    })
  }

  async function handleConfirmVisionFinding(
    findingId: string,
    confirmationState: Extract<VisionConfirmationState, 'manual_confirmed' | 'rejected'>,
  ) {
    const target = mediaState.status === 'ready' ? { targetType: mediaState.targetType, targetId: mediaState.targetId } : null
    const response = await confirmVisionFinding(findingId, { confirmationState, confirmedBy: 'web' }, currentAdminToken())
    if (!target) {
      setMediaState((current) => {
        if (current.status !== 'ready') return current
        return {
          ...current,
          findings: current.findings.map((finding) => (finding.id === findingId ? response.finding : finding)),
        }
      })
      return
    }
    try {
      const findings = await fetchVisionFindingsForTarget(target.targetType, target.targetId, currentAdminToken())
      setMediaState((current) => {
        if (current.status !== 'ready' || current.targetType !== target.targetType || current.targetId !== target.targetId) return current
        return { ...current, findings: findings.findings }
      })
    } catch {
      setMediaState((current) => {
        if (current.status !== 'ready') return current
        return {
          ...current,
          findings: current.findings.map((finding) => (finding.id === findingId ? response.finding : finding)),
        }
      })
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
      <>
        {renderSyncPanel()}
        <main className="app-shell">
          <section className="panel empty-state">
            <h1>History API unavailable</h1>
            <p>{overviewState.message}</p>
            <button type="button" onClick={() => void refreshOverviewState()}>
              Retry history
            </button>
          </section>
        </main>
      </>
    )
  }

  if (activePage === 'rounds') {
    if (roundsState.status === 'ready') {
      return (
        <>
          {renderSyncPanel()}
          <HistoryTimeline
            data={roundsState.data}
            onNavigate={navigate}
            onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
            onOpenRoundDetail={(roundRef) => void handleSelectRoundDetail(roundRef)}
          />
          {renderDrilldownPanels()}
        </>
      )
    }

    if (roundsState.status === 'error') {
      return (
        <>
          {renderSyncPanel()}
          <main className="app-shell">
            <section className="panel empty-state">
              <h1>Rounds unavailable</h1>
              <p>{roundsState.message}</p>
              <button type="button" onClick={() => void loadRoundsState()}>
                Retry rounds
              </button>
            </section>
          </main>
        </>
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
            <HistoryDrilldownPanel
              state={drilldownState}
              onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
              onRetrySource={(sourceRef) => void handleSelectSourceRef(sourceRef)}
              onCreateAnnotationForSource={handleCreateAnnotationForSource}
            />
            {holeEvidenceState.status === 'idle' ? null : (
              <HoleEvidencePanel
                state={holeEvidenceState}
                ensureState={geometryEnsureState}
                onEnsureGeometry={(target) => void handleEnsureHoleGeometry(target)}
              />
            )}
          </main>
        </>
      )
    }

    if (statsState.status === 'error') {
      return (
        <>
          {renderSyncPanel()}
          <main className="app-shell">
            <ProductNav activePage={activePage} onNavigate={navigate} />
            <section className="panel empty-state">
              <h1>History stats unavailable</h1>
              <p>{statsState.message}</p>
              <button type="button" onClick={() => void loadStatsState()}>
                Retry history stats
              </button>
            </section>
          </main>
        </>
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
            onLoadWeather={(params) => void handleLoadWeather(params)}
            onLoadCaddieContext={(params) => void handleLoadCaddieContext(params)}
            onLoadMediaContext={(target) => void handleLoadMediaContext(target)}
            onAttachMedia={handleAttachMedia}
            onAnalyzeMedia={(mediaId) => void handleAnalyzeMedia(mediaId)}
            onRedactMedia={(mediaId) => void handleRedactMedia(mediaId)}
            onConfirmVisionFinding={(findingId, confirmationState) => void handleConfirmVisionFinding(findingId, confirmationState)}
            onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
            selectedSourceRef={selectedCaddieSourceRef}
          />
          <CoursePrepPanel />
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
          <SettingsPage
            onNavigate={navigate}
            settings={productSettingsState.status === 'ready' ? productSettingsState.data : null}
            settingsError={productSettingsState.status === 'error' ? productSettingsState.message : null}
          />
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
            <ProductNav activePage={activePage} onNavigate={navigate} />
            <CorrectionsPage
              key={correctionTarget ? `${correctionTarget.targetType}:${correctionTarget.targetId}` : 'manual-corrections'}
              data={annotationsState.data}
              initialTarget={correctionTarget ?? undefined}
              onCreateAnnotation={handleCreateAnnotation}
            />
          </main>
        </>
      )
    }

    if (annotationsState.status === 'error') {
      return (
        <main className="app-shell">
          <ProductNav activePage={activePage} onNavigate={navigate} />
          <section className="panel empty-state">
            <h1>Corrections unavailable</h1>
            <p>{annotationsState.message}</p>
          </section>
        </main>
      )
    }

    return (
      <main className="app-shell">
        <ProductNav activePage={activePage} onNavigate={navigate} />
        <section className="panel empty-state">
          <h1>Loading corrections</h1>
        </section>
      </main>
    )
  }

  return (
    <>
      {renderSyncPanel()}
      <HistoryOverview
        data={overviewState.data}
        onNavigate={navigate}
        onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
        onOpenRoundDetail={(roundRef) => void handleSelectRoundDetail(roundRef)}
      />
      {renderDrilldownPanels()}
    </>
  )
}

function sameHoleGeometryTarget(left: HoleGeometryTarget | null, right: HoleGeometryTarget): boolean {
  return Boolean(
    left &&
      left.globalId === right.globalId &&
      left.localHole === right.localHole &&
      left.sourceRef === right.sourceRef,
  )
}

function decisionIdFromDecision(decision: CaddieDecisionResponse): string {
  if (decision.decisionId) return decision.decisionId
  const context = decision.context ?? {}
  const courseName = typeof context.courseName === 'string' ? context.courseName : 'fixture'
  const hole = typeof context.hole === 'number' || typeof context.hole === 'string' ? String(context.hole) : 'unknown'
  return [slug(courseName), hole, decision.shotType].join('-')
}

function decisionAuditRequest(
  decision: CaddieDecisionResponse,
  actualOutcome: Record<string, unknown>,
): {
  decision: CaddieDecisionResponse
  actualShot: Record<string, unknown> | null
  actualShots?: Array<Record<string, unknown>>
  actualScoreToPar?: number | null
  penalty?: boolean | null
} {
  if ('actualShot' in actualOutcome || 'actualShots' in actualOutcome || 'actualScoreToPar' in actualOutcome || 'penalty' in actualOutcome) {
    return {
      decision,
      actualShot: recordOrNull(actualOutcome.actualShot),
      ...(Array.isArray(actualOutcome.actualShots) ? { actualShots: actualOutcome.actualShots as Array<Record<string, unknown>> } : {}),
      ...(typeof actualOutcome.actualScoreToPar === 'number' || actualOutcome.actualScoreToPar === null
        ? { actualScoreToPar: actualOutcome.actualScoreToPar as number | null }
        : {}),
      ...(typeof actualOutcome.penalty === 'boolean' || actualOutcome.penalty === null ? { penalty: actualOutcome.penalty as boolean | null } : {}),
    }
  }
  return { decision, actualShot: actualOutcome }
}

function recordOrNull(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null
}

function holeGeometryTargetFromDrilldown(
  sourceRef: string,
  drilldown: HistoryDrilldownResponse,
): { globalId: number; localHole: number } | null {
  const globalId =
    numericField(drilldown.hole, 'globalId') ??
    numericField(drilldown.shot, 'globalId') ??
    numericField(drilldown.round, 'globalId')
  const localHole =
    numericField(drilldown.hole, 'localHole') ??
    numericField(drilldown.shot, 'localHole') ??
    numericField(drilldown.hole, 'number') ??
    holeFromSourceRef(sourceRef)
  if (globalId === null || localHole === null) return null
  return { globalId, localHole }
}

function numericField(row: Record<string, unknown> | null, key: string): number | null {
  const value = row?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function loadedCaddieContextSourceRef(state: DeferredLoadState<CaddieContextResponse>): string {
  if (state.status !== 'ready') return ''
  const direct = typeof state.data.sourceRef === 'string' ? state.data.sourceRef.trim() : ''
  if (direct) return direct
  return typeof state.data.context?.sourceRef === 'string' ? state.data.context.sourceRef.trim() : ''
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
