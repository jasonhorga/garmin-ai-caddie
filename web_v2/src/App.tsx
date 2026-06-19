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
  fetchHistorySummary,
  ingestPlayerRound,
  ROUNDS_FULL_LIMIT,
  fetchReadiness,
  fetchMobileCoursePackage,
  fetchMobileCourseOptions,
  fetchMobileReconciliation,
  fetchMobileRoundPackage,
  fetchProductSettings,
  fetchCourseSearch,
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
import type { MediaContextState } from './components/CaddiePage'
import { CorrectionsPage, type CorrectionTarget } from './components/CorrectionsPage'
import { CourseStats } from './components/CourseStats'
import { DataQualityPage } from './components/DataQualityPage'
import { HomeOverview } from './components/HomeOverview'
import { InvalidLinkPage } from './components/InvalidLinkPage'
import { HistoryDrilldownPanel, type HistoryDrilldownPanelState } from './components/HistoryDrilldownPanel'
import { HistoryRoundDetailPanel, type HistoryRoundDetailPanelState } from './components/HistoryRoundDetailPanel'
import { HistoryTimeline } from './components/HistoryTimeline'
import { RecordRoundPage } from './components/RecordRoundPage'
import { HoleEvidencePanel, type GeometryEnsureState, type HoleEvidenceState } from './components/HoleEvidencePanel'
import {
  MobileReconciliationPanel,
  type MobileReconciliationApplyState,
  type MobileReconciliationPanelState,
} from './components/MobileReconciliationPanel'
import {
  MobilePackagePrepPanel,
  type MobilePackagePrepState,
} from './components/MobilePackagePrepPanel'
import { AppShell } from './components/AppShell'
import { LivePage } from './components/LivePage'
import { PlayerAdminPage } from './components/PlayerAdminPage'
import { PrepPage } from './components/PrepPage'
import { ReadinessPanel } from './components/ReadinessPanel'
import { ReportsPage } from './components/ReportsPage'
import { SettingsPage } from './components/SettingsPage'
import { StrengthsPage } from './components/StrengthsPage'
import { SyncStatusPanel } from './components/SyncStatusPanel'
import { TrendsOverview } from './components/TrendsOverview'
import { isOwnerOnlyPage, type ProductPage } from './navigation'
import { readAdminTokenFromUrl, readBakedAdminToken, readStoredAdminToken, writeStoredAdminToken } from './adminTokenStore'
import { readStoredDiagnostics, writeStoredDiagnostics } from './diagnosticsStore'
import { DiagnosticsProvider } from './diagnosticsContext'
import { isLinkRequired, readPlayerToken } from './playerContext'
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
  HistoryStatsSummaryResponse,
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
  StatsWindow,
  SyncStatusResponse,
  WeatherSnapshotParams,
  WeatherSnapshotResponse,
  VisionConfirmationState,
  RoundsFilters,
} from './types'

type LoadState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }

type DeferredLoadState<T> = { status: 'idle' } | LoadState<T>
type HoleGeometryTarget = { globalId: number; localHole: number; sourceRef: string }

const statsPages: ProductPage[] = ['history', 'courses', 'holes', 'clubs', 'issues', 'reports', 'sync-quality']

export default function App() {
  // Access model: a per-player bearer token in the URL scopes the whole app to
  // one player; otherwise the existing owner/admin-token behavior applies. On a
  // player-facing deployment (isLinkRequired) a visitor with neither a player
  // token nor an admin token is locked out behind InvalidLinkPage, and an
  // invalid/expired player link (first auth 401) flips accessDenied below.
  const playerToken = readPlayerToken()
  const linkRequired = isLinkRequired()
  // Owner mode = bare URL (no per-player token). Players never get owner ops or
  // the diagnostics switch. Diagnostics defaults OFF so the owner sees a clean
  // product; it is only ever true in owner mode with the switch flipped on.
  const isOwnerMode = !playerToken
  const [accessDenied, setAccessDenied] = useState(false)
  const [diagnostics, setDiagnostics] = useState(() => isOwnerMode && readStoredDiagnostics())
  const [activePage, setActivePage] = useState<ProductPage>('overview')
  const [overviewState, setOverviewState] = useState<LoadState<HistoryOverviewResponse>>({ status: 'loading' })
  const [roundsState, setRoundsState] = useState<DeferredLoadState<HistoryRoundsResponse>>({ status: 'idle' })
  const [roundsFilters, setRoundsFilters] = useState<RoundsFilters>({})
  // Two-tier 球局 loading: first page on entry, full archive on demand. The seq
  // ref discards a stale fetch (e.g. a filter change mid-flight) and fullLoaded
  // lets refreshes re-pull at the same depth the visitor had reached.
  const [roundsLoadingMore, setRoundsLoadingMore] = useState(false)
  const roundsSeq = useRef(0)
  const roundsFullLoaded = useRef(false)
  const [statsState, setStatsState] = useState<DeferredLoadState<HistoryStatsResponse>>({ status: 'idle' })
  // 概览 landing uses this slim summary (handicap/均杆/本周该练) instead of the
  // ~20MB full statsState, which now loads lazily only on the analysis pages.
  const [homeSummaryState, setHomeSummaryState] = useState<DeferredLoadState<HistoryStatsSummaryResponse>>({ status: 'idle' })
  const [trendsWindow, setTrendsWindow] = useState<StatsWindow>('last10')
  const [trendsState, setTrendsState] = useState<DeferredLoadState<HistoryStatsResponse>>({ status: 'idle' })
  // Mirrors HomeOverview's searchSeq guard: stale trends responses are discarded,
  // and refreshes always read the window the user most recently selected.
  const trendsSeq = useRef(0)
  const trendsWindowRef = useRef<StatsWindow>('last10')
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
  const [prepGlobalId, setPrepGlobalId] = useState<number | null>(null)
  // The finder's course name rides along with the gid so searched courses that
  // have no courseOptions row still show a real name in the prep header.
  const [prepCourseName, setPrepCourseName] = useState<string | null>(null)
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
  // Hydrate the owner's admin token. Prefer a token carried in the URL
  // (`?admin=<token>`, like the player `/p/<token>` link) so the owner can
  // bookmark ONE URL and never retype — durable even if iOS Safari clears
  // localStorage. Fall back to the persisted token. A URL token is also persisted
  // so SPA navigation that drops the query keeps working within the session.
  const [adminToken, setAdminToken] = useState(() => {
    const fromUrl = readAdminTokenFromUrl()
    if (fromUrl) {
      writeStoredAdminToken(fromUrl)
      return fromUrl
    }
    // URL → previously entered → build-time baked default (owner's private homeserver
    // build only). The baked default lets the bare URL auto-load the owner profile.
    return readStoredAdminToken() || readBakedAdminToken()
  })

  useEffect(() => {
    // Locked out: a link is required, the URL carries no player token, and no
    // admin token can exist yet at mount. Send no requests and expose nothing.
    if (isLinkRequired() && !readPlayerToken()) {
      return
    }

    let cancelled = false
    const bootPlayerToken = readPlayerToken()
    // currentAdminToken() reads the hydrated admin-token state, so the owner's
    // first boot fetch carries it (api.ts still auto-injects the player bearer
    // from /p/<token> on top, so player links keep working). With neither token
    // present this is undefined and behavior is unchanged.
    const bootAdminToken = currentAdminToken()

    fetchHistoryOverview(bootAdminToken)
      .then((data) => {
        if (!cancelled) setOverviewState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        // An invalid/expired player link must not surface the owner recovery
        // panel — show the clean invalid-link page instead.
        if (bootPlayerToken && isUnauthorized(error)) {
          setAccessDenied(true)
          return
        }
        setOverviewState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
      })

    // The landing 概览 reads the slim summary (近期状态/本周该练) for a fast first
    // paint instead of the ~20MB full stats. The full statsState still loads in
    // the background below so the analysis pages stay warm/instant; only the
    // home's blocking dependency on that 20MB payload is removed.
    setHomeSummaryState({ status: 'loading' })
    fetchHistorySummary(bootAdminToken)
      .then((data) => {
        if (!cancelled) setHomeSummaryState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (!cancelled) setHomeSummaryState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
      })

    setStatsState({ status: 'loading' })
    fetchHistoryStats(bootAdminToken)
      .then((data) => {
        if (!cancelled) setStatsState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (!cancelled) setStatsState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
      })

    setMobileCourseOptionsState({ status: 'loading' })
    fetchMobileCourseOptions(bootAdminToken)
      .then((data) => {
        if (!cancelled) setMobileCourseOptionsState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (!cancelled) setMobileCourseOptionsState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
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
    // Boot-once: deliberately empty deps. currentAdminToken() reads the token
    // hydrated at mount; we do not want this effect to re-run as it changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function currentAdminToken(): string | undefined {
    const trimmed = adminToken.trim()
    return trimmed.length ? trimmed : undefined
  }

  function errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : 'Unknown error'
  }

  // zh surfaces (W1b 概览/趋势) fall back to a Chinese string; legacy English panels keep errorMessage.
  function zhErrorMessage(error: unknown): string {
    return error instanceof Error ? error.message : '未知错误'
  }

  async function refreshOverviewState(adminTokenOverride: string | undefined = currentAdminToken()) {
    try {
      const data = await fetchHistoryOverview(adminTokenOverride)
      setOverviewState({ status: 'ready', data })
    } catch (error: unknown) {
      setOverviewState((current) => (current.status === 'ready' ? current : { status: 'error', message: errorMessage(error) }))
    }
  }

  async function loadRoundsState(filters: RoundsFilters = roundsFilters, adminTokenOverride: string | undefined = currentAdminToken()) {
    const seq = ++roundsSeq.current
    roundsFullLoaded.current = false
    setRoundsLoadingMore(false)
    setRoundsState({ status: 'loading' })
    try {
      const data = await fetchHistoryRounds(adminTokenOverride, filters)
      if (roundsSeq.current !== seq) return
      setRoundsState({ status: 'ready', data })
    } catch (error: unknown) {
      if (roundsSeq.current !== seq) return
      setRoundsState({ status: 'error', message: errorMessage(error) })
    }
  }

  // Pull the full archive once the visitor reveals past the first page. Swaps
  // the data in place (keep-ready) so the timeline never drops to a skeleton,
  // and the seq guard means a filter change mid-flight wins.
  async function loadAllRounds(adminTokenOverride: string | undefined = currentAdminToken()) {
    if (roundsLoadingMore || roundsFullLoaded.current) return
    const seq = ++roundsSeq.current
    setRoundsLoadingMore(true)
    try {
      const data = await fetchHistoryRounds(adminTokenOverride, roundsFilters, ROUNDS_FULL_LIMIT)
      if (roundsSeq.current !== seq) return
      roundsFullLoaded.current = true
      setRoundsState((current) => (current.status === 'ready' ? { status: 'ready', data } : current))
    } catch {
      // Keep the first page on failure; the 加载更多 button stays available to retry.
    } finally {
      if (roundsSeq.current === seq) setRoundsLoadingMore(false)
    }
  }

  async function refreshRoundsState(adminTokenOverride: string | undefined = currentAdminToken()) {
    // Re-pull at the depth the visitor had reached so a background refresh never
    // silently re-collapses an already-expanded archive back to the first page.
    const limit = roundsFullLoaded.current ? ROUNDS_FULL_LIMIT : undefined
    try {
      const data = await fetchHistoryRounds(adminTokenOverride, roundsFilters, limit)
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

  async function loadHomeSummary(adminTokenOverride: string | undefined = currentAdminToken()) {
    setHomeSummaryState({ status: 'loading' })
    try {
      const data = await fetchHistorySummary(adminTokenOverride)
      setHomeSummaryState({ status: 'ready', data })
    } catch (error: unknown) {
      setHomeSummaryState({ status: 'error', message: errorMessage(error) })
    }
  }

  async function refreshHomeSummary(adminTokenOverride: string | undefined = currentAdminToken()) {
    try {
      const data = await fetchHistorySummary(adminTokenOverride)
      setHomeSummaryState({ status: 'ready', data })
    } catch (error: unknown) {
      setHomeSummaryState((current) => (current.status === 'ready' ? current : { status: 'error', message: errorMessage(error) }))
    }
  }

  async function loadTrendsState(window: StatsWindow = trendsWindowRef.current, adminTokenOverride: string | undefined = currentAdminToken()) {
    const seq = ++trendsSeq.current
    setTrendsState({ status: 'loading' })
    try {
      const data = await fetchHistoryStats(adminTokenOverride, window)
      if (trendsSeq.current !== seq) return
      setTrendsState({ status: 'ready', data })
    } catch (error: unknown) {
      if (trendsSeq.current !== seq) return
      setTrendsState({ status: 'error', message: zhErrorMessage(error) })
    }
  }

  async function refreshTrendsState(adminTokenOverride: string | undefined = currentAdminToken()) {
    const seq = ++trendsSeq.current
    try {
      const data = await fetchHistoryStats(adminTokenOverride, trendsWindowRef.current)
      if (trendsSeq.current !== seq) return
      setTrendsState({ status: 'ready', data })
    } catch (error: unknown) {
      if (trendsSeq.current !== seq) return
      setTrendsState((current) => (current.status === 'ready' ? current : { status: 'error', message: zhErrorMessage(error) }))
    }
  }

  function handleTrendsWindowChange(window: StatsWindow) {
    trendsWindowRef.current = window
    setTrendsWindow(window)
    void loadTrendsState(window)
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

  async function refreshMobileCourseOptionsState(adminTokenOverride: string | undefined = currentAdminToken()) {
    try {
      const data = await fetchMobileCourseOptions(adminTokenOverride)
      setMobileCourseOptionsState({ status: 'ready', data })
    } catch (error: unknown) {
      setMobileCourseOptionsState((current) => (current.status === 'ready' ? current : { status: 'error', message: errorMessage(error) }))
    }
  }

  function refreshLoadedHistorySurfaces(adminTokenOverride: string | undefined = currentAdminToken()) {
    void refreshOverviewState(adminTokenOverride)
    if (homeSummaryState.status !== 'idle') void refreshHomeSummary(adminTokenOverride)
    if (roundsState.status !== 'idle') void refreshRoundsState(adminTokenOverride)
    if (statsState.status !== 'idle') void refreshStatsState(adminTokenOverride)
    if (trendsState.status !== 'idle') void refreshTrendsState(adminTokenOverride)
    if (readinessState.status !== 'idle') void refreshReadinessState()
    if (mobileCourseOptionsState.status !== 'idle') void refreshMobileCourseOptionsState(adminTokenOverride)
    if (reportIndexState.status !== 'idle') loadReportIndex()
  }

  // Re-fetch only the history surfaces that errored on the token-less boot, using
  // the keep-ready refreshers so a still-broken backend cannot clobber ready
  // payloads. Gating on 'error' means a healthy app issues no extra loads.
  function recoverErroredHistorySurfaces(adminTokenOverride: string | undefined = currentAdminToken()) {
    if (overviewState.status === 'error') void refreshOverviewState(adminTokenOverride)
    if (homeSummaryState.status === 'error') void refreshHomeSummary(adminTokenOverride)
    if (roundsState.status === 'error') void refreshRoundsState(adminTokenOverride)
    if (statsState.status === 'error') void refreshStatsState(adminTokenOverride)
    if (trendsState.status === 'error') void refreshTrendsState(adminTokenOverride)
    if (mobileCourseOptionsState.status === 'error') void refreshMobileCourseOptionsState(adminTokenOverride)
  }

  function handleAdminTokenChange(value: string) {
    setAdminToken(value)
    // Persist immediately so the next page load hydrates it; clearing removes it.
    writeStoredAdminToken(value)
    if (adminTokenRefreshTimer.current !== null) {
      window.clearTimeout(adminTokenRefreshTimer.current)
      adminTokenRefreshTimer.current = null
    }
    const nextToken = value.trim()
    // The owner just supplied a token: re-fetch any surface that 401'd on the
    // token-less boot so their data appears without a manual 重试. Debounced so
    // typing the token char-by-char fires a single refetch with the full value.
    if (nextToken) {
      adminTokenRefreshTimer.current = window.setTimeout(() => {
        recoverErroredHistorySurfaces(nextToken)
        adminTokenRefreshTimer.current = null
      }, 250)
    }
  }

  function toggleDiagnostics() {
    setDiagnostics((on) => {
      const next = !on
      writeStoredDiagnostics(next)
      return next
    })
  }

  function navigate(page: ProductPage) {
    // Player links can't reach owner ops even if a stale state points there.
    if (!isOwnerMode && isOwnerOnlyPage(page)) {
      setActivePage('overview')
      return
    }
    if (page !== 'corrections') {
      setCorrectionTarget(null)
    }
    setActivePage(page)
    if (page === 'overview' || page === 'prep') {
      // 概览/备战 compose stats + course options on boot; if either failed at
      // boot (e.g. backend briefly down), returning here retries instead of
      // leaving the joined cards stuck on the stale error forever. 概览 also
      // retries its slim summary (the card it actually renders from).
      if (page === 'overview' && (homeSummaryState.status === 'idle' || homeSummaryState.status === 'error')) void loadHomeSummary()
      if (statsState.status === 'idle' || statsState.status === 'error') void loadStatsState()
      if (mobileCourseOptionsState.status === 'idle' || mobileCourseOptionsState.status === 'error') void loadMobileCourseOptionsState()
    }
    if (page === 'caddie') {
      // 实战 composes course options (沙盘 course pick) + overview recentRounds
      // (回放 rows AND the sandbox advice sourceRef chain) — same lazy retry as
      // 概览/备战 above; overview goes through the keep-ready refresh helper so
      // a still-broken backend cannot clobber an already-ready payload.
      if (mobileCourseOptionsState.status === 'idle' || mobileCourseOptionsState.status === 'error') void loadMobileCourseOptionsState()
      if (overviewState.status === 'error') void refreshOverviewState()
    }
    if (page === 'courses') {
      // 球场表现 shows 去备战 buttons keyed on globalId from courseOptions;
      // retry the load when it is idle or previously errored (mirrors 概览/备战).
      if (mobileCourseOptionsState.status === 'idle' || mobileCourseOptionsState.status === 'error') void loadMobileCourseOptionsState()
    }
    if (page === 'record') {
      // 手机记分 offers a 常打球场 dropdown sourced from courseOptions.
      if (mobileCourseOptionsState.status === 'idle' || mobileCourseOptionsState.status === 'error') void loadMobileCourseOptionsState()
    }
    if (page === 'rounds' && roundsState.status === 'idle') {
      void loadRoundsState()
    }
    if (statsPages.includes(page) && statsState.status === 'idle') {
      void loadStatsState()
    }
    if (page === 'history' && trendsState.status === 'idle') {
      void loadTrendsState()
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

  function handlePrepCourse(globalId: number, name?: string) {
    setPrepGlobalId(globalId)
    setPrepCourseName(name ?? null)
    navigate('prep')
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

  function renderDrilldownPanels() {
    if (roundDetailState.status === 'idle' && drilldownState.status === 'idle' && holeEvidenceState.status === 'idle') return null
    return (
      <>
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
      </>
    )
  }

  function renderStatsContent(data: HistoryStatsResponse) {
    if (activePage === 'courses') return (
      <CourseStats
        data={data}
        onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
        courseOptions={mobileCourseOptionsState.status === 'ready' ? mobileCourseOptionsState.data : null}
        onPrepCourse={handlePrepCourse}
      />
    )
    if (activePage === 'holes' || activePage === 'clubs' || activePage === 'issues') {
      return <StrengthsPage data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
    }
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
    return null
  }

  function renderSyncQualityWorkspace() {
    return (
      <section className="sync-quality-workspace" aria-label="同步与数据健康工作区">
        <div className="section-head stats-head">
          <div>
            <p className="eyebrow">证据覆盖</p>
            <h1>同步与数据健康</h1>
            <p>Garmin 连接器状态、本地快照覆盖与影响置信度的缺口。</p>
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
        {statsState.status === 'ready' ? (
          <DataQualityPage data={statsState.data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
        ) : null}
        {statsState.status === 'loading' ? (
          <section className="panel empty-state">
            <h2>数据健康加载中</h2>
          </section>
        ) : null}
        {statsState.status === 'error' ? (
          <section className="panel empty-state">
            <h2>数据健康不可用</h2>
            <p>{statsState.message}</p>
            <button type="button" onClick={() => void loadStatsState()}>
              重试历史统计
            </button>
          </section>
        ) : null}
      </section>
    )
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

  function renderActivePage() {
    if (activePage === 'rounds') {
      if (roundsState.status === 'ready') {
        return (
          <>
            <HistoryTimeline
              data={roundsState.data}
              filters={roundsFilters}
              onFilterChange={(next) => {
                setRoundsFilters(next)
                void loadRoundsState(next)
              }}
              onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
              onOpenRoundDetail={(roundRef) => void handleSelectRoundDetail(roundRef)}
              onLoadAll={() => void loadAllRounds()}
              loadingMore={roundsLoadingMore}
            />
            {renderDrilldownPanels()}
          </>
        )
      }
      if (roundsState.status === 'error') {
        return (
          <section className="panel empty-state">
            <h1>球局数据不可用</h1>
            <p>{roundsState.message}</p>
            <button type="button" onClick={() => void loadRoundsState()}>
              重试
            </button>
            <p className="empty-state-hint">如需配置访问密钥，请前往 设置 → 同步与数据健康。</p>
            <button type="button" onClick={() => navigate('sync-quality')}>
              去设置
            </button>
          </section>
        )
      }
      return (
        <section className="panel empty-state">
          <h1>球局加载中</h1>
        </section>
      )
    }

    if (activePage === 'sync-quality') {
      return (
        <>
          {renderSyncQualityWorkspace()}
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
        </>
      )
    }

    if (activePage === 'history') {
      // The trends page gates on its own windowed trendsState so it is usable as
      // soon as trends data arrives; the app-wide statsState (window=all) only
      // feeds the optional vs-全部 deltas and may lag without blocking the page.
      if (trendsState.status === 'ready') {
        return (
          <>
            <TrendsOverview
              stats={trendsState.data}
              allStats={statsState.status === 'ready' ? statsState.data : null}
              window={trendsWindow}
              onWindowChange={handleTrendsWindowChange}
              recentRounds={overviewState.status === 'ready' ? overviewState.data.recentRounds : []}
              onOpenRoundDetail={(roundRef) => void handleSelectRoundDetail(roundRef)}
            />
            {renderDrilldownPanels()}
          </>
        )
      }
      if (trendsState.status === 'error') {
        return (
          <section className="panel empty-state">
            <h2>趋势总览加载失败</h2>
            <p>{trendsState.message}</p>
            <button type="button" onClick={() => void loadTrendsState()}>
              重试
            </button>
          </section>
        )
      }
      return (
        <section className="panel empty-state">
          <h2>趋势总览加载中</h2>
        </section>
      )
    }

    if (statsPages.includes(activePage)) {
      if (statsState.status === 'ready') {
        return (
          <>
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
          </>
        )
      }
      if (statsState.status === 'error') {
        return (
          <section className="panel empty-state">
            <h1>历史数据加载失败</h1>
            <p>{statsState.message}</p>
            <button type="button" onClick={() => void loadStatsState()}>
              重试
            </button>
            <p className="empty-state-hint">如需配置访问密钥，请前往 设置 → 同步与数据健康。</p>
            <button type="button" onClick={() => navigate('sync-quality')}>
              去设置
            </button>
          </section>
        )
      }
      return (
        <section className="panel empty-state">
          <h1>历史数据加载中</h1>
        </section>
      )
    }

    if (activePage === 'prep') {
      return (
        <PrepPage
          globalId={prepGlobalId}
          selectedCourseName={prepCourseName}
          courseOptions={mobileCourseOptionsState.status === 'ready' ? mobileCourseOptionsState.data : null}
          allStats={statsState.status === 'ready' ? statsState.data : null}
          adminToken={currentAdminToken()}
          onSearchCourses={(name) => fetchCourseSearch(name, currentAdminToken())}
          onSelectCourse={handlePrepCourse}
          onChangeCourse={() => {
            setPrepGlobalId(null)
            setPrepCourseName(null)
          }}
        />
      )
    }

    if (activePage === 'caddie') {
      // 实战 renders the LivePage shell; the old CaddiePage props bundle moves
      // VERBATIM into caddieProps for the 完整工具 tab (zero tooling deleted).
      // The 最近回放 detail panel gets the SAME drilldown/annotation/AI-review
      // handlers the history pages give HistoryRoundDetailPanel; the panels
      // those handlers open render below LivePage exactly like the
      // sync-quality page (drilldown + hole evidence only — the App-level
      // round detail panel stays off this page because 最近回放 owns its own).
      return (
        <>
          <LivePage
            courseOptions={mobileCourseOptionsState.status === 'ready' ? mobileCourseOptionsState.data : null}
            adminToken={currentAdminToken()}
            onSearchCourses={(name) => fetchCourseSearch(name, currentAdminToken())}
            recentRounds={overviewState.status === 'ready' ? overviewState.data.recentRounds : []}
            reportState={reportState}
            onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
            onCreateAnnotationForRound={handleCreateAnnotationForSource}
            onLoadRoundReport={handleLoadRoundReport}
            onGenerateRoundReport={handleGenerateRoundReport}
            caddieProps={{
              decisionState,
              auditState: decisionAuditState,
              weatherState,
              contextState: caddieContextState,
              mediaState,
              onRequestDecision: (request) => void handleRequestCaddieDecision(request),
              onCreateAudit: (decision, actualShot) => void handleCreateDecisionAudit(decision, actualShot),
              onLoadWeather: (params) => void handleLoadWeather(params),
              onLoadCaddieContext: (params) => void handleLoadCaddieContext(params),
              onLoadMediaContext: (target) => void handleLoadMediaContext(target),
              onAttachMedia: handleAttachMedia,
              onAnalyzeMedia: (mediaId) => void handleAnalyzeMedia(mediaId),
              onRedactMedia: (mediaId) => void handleRedactMedia(mediaId),
              onConfirmVisionFinding: (findingId, confirmationState) => void handleConfirmVisionFinding(findingId, confirmationState),
              onSelectRef: (sourceRef) => void handleSelectSourceRef(sourceRef),
              selectedSourceRef: selectedCaddieSourceRef,
            }}
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
        </>
      )
    }

    if (activePage === 'record') {
      // 手机记分: browser-Geolocation per-shot GPS recorder that posts a manual
      // round to /api/v2/players/{id}/rounds. Player id comes from the boot
      // overview (owner = "me"); the api wrapper injects the bearer/admin token.
      const currentPlayer = overviewState.status === 'ready' ? overviewState.data.currentPlayer ?? null : null
      return (
        <RecordRoundPage
          playerId={currentPlayer?.id ?? 'me'}
          playerName={currentPlayer?.name ?? null}
          courseOptions={mobileCourseOptionsState.status === 'ready' ? mobileCourseOptionsState.data : null}
          onIngest={(playerId, body) => ingestPlayerRound(playerId, body, currentAdminToken())}
          onExit={() => navigate('overview')}
        />
      )
    }

    if (activePage === 'players') {
      // Owner-only management surface; reuses the admin token entered in the
      // sync panel. Never renders any player's score analysis.
      return <PlayerAdminPage adminToken={currentAdminToken()} onNavigate={navigate} />
    }

    if (activePage === 'settings') {
      return (
        <SettingsPage
          onNavigate={navigate}
          settings={productSettingsState.status === 'ready' ? productSettingsState.data : null}
          settingsError={productSettingsState.status === 'error' ? productSettingsState.message : null}
        />
      )
    }

    if (activePage === 'corrections') {
      if (annotationsState.status === 'ready') {
        return (
          <CorrectionsPage
            key={correctionTarget ? `${correctionTarget.targetType}:${correctionTarget.targetId}` : 'manual-corrections'}
            data={annotationsState.data}
            initialTarget={correctionTarget ?? undefined}
            onCreateAnnotation={handleCreateAnnotation}
          />
        )
      }
      if (annotationsState.status === 'error') {
        return (
          <section className="panel empty-state">
            <h1>订正数据不可用</h1>
            <p>{annotationsState.message}</p>
          </section>
        )
      }
      return (
        <section className="panel empty-state">
          <h1>订正加载中</h1>
        </section>
      )
    }

    if (overviewState.status === 'loading') {
      return (
        <section className="panel empty-state">
          <h1>历史数据加载中</h1>
        </section>
      )
    }

    if (overviewState.status === 'error') {
      // The home never shows the Garmin connector diagnostic / 管理令牌 input /
      // 立即同步 — those engineering surfaces live ONLY in 设置 → 同步. A token-less
      // owner (or a stale/bad link) just gets a clean prompt pointing them there.
      return (
        <section className="panel empty-state">
          <h1>还看不到你的数据</h1>
          <p>请到 设置 → 同步 填入管理令牌，或用你收到的专属链接打开本页。</p>
          <button type="button" onClick={() => navigate('sync-quality')}>
            去设置
          </button>
          <button type="button" onClick={() => void refreshOverviewState()}>
            重试
          </button>
        </section>
      )
    }

    return (
      <>
        <HomeOverview
          overview={overviewState.data}
          statsSummary={homeSummaryState.status === 'ready' ? homeSummaryState.data : null}
          statsLoading={homeSummaryState.status === 'loading' || homeSummaryState.status === 'idle'}
          courseOptions={mobileCourseOptionsState.status === 'ready' ? mobileCourseOptionsState.data : null}
          onSearchCourses={(name) => fetchCourseSearch(name, currentAdminToken())}
          onPrepCourse={handlePrepCourse}
          onOpenRoundDetail={(roundRef) => void handleSelectRoundDetail(roundRef)}
          onNavigateHistory={() => navigate('history')}
          onNavigateAnalysis={() => navigate('holes')}
          onStartRecord={() => navigate('record')}
        />
        {renderDrilldownPanels()}
      </>
    )
  }

  const lockedOut = linkRequired && !playerToken && !currentAdminToken()
  if (lockedOut || accessDenied) {
    return <InvalidLinkPage />
  }

  return (
    <DiagnosticsProvider value={diagnostics}>
      <AppShell
        activePage={activePage}
        onNavigate={navigate}
        isOwnerMode={isOwnerMode}
        playersAdminVisible={!playerToken && Boolean(currentAdminToken())}
        diagnostics={diagnostics}
        onToggleDiagnostics={toggleDiagnostics}
        currentPlayer={overviewState.status === 'ready' ? overviewState.data.currentPlayer ?? null : null}
      >
        {renderActivePage()}
      </AppShell>
    </DiagnosticsProvider>
  )
}

function isUnauthorized(error: unknown): boolean {
  return error instanceof Error && /\b401\b/.test(error.message)
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
