import { useEffect, useState } from 'react'
import {
  createAnnotation,
  fetchAnnotations,
  fetchHistoryOverview,
  fetchHistoryRounds,
  fetchHistoryStats,
  fetchSyncStatus,
} from './api'
import { ClubStats } from './components/ClubStats'
import { CorrectionsPage } from './components/CorrectionsPage'
import { CourseStats } from './components/CourseStats'
import { DataQualityPage } from './components/DataQualityPage'
import { HistoryOverview } from './components/HistoryOverview'
import { HistoryTimeline } from './components/HistoryTimeline'
import { HoleStats } from './components/HoleStats'
import { IssueStats } from './components/IssueStats'
import { ProductNav } from './components/ProductNav'
import { StatsOverview } from './components/StatsOverview'
import { SyncStatusPanel } from './components/SyncStatusPanel'
import type { ProductPage } from './components/ProductNav'
import type {
  AnnotationCreateRequest,
  AnnotationCreateResponse,
  AnnotationListResponse,
  HistoryOverviewResponse,
  HistoryRoundsResponse,
  HistoryStatsResponse,
  SyncStatusResponse,
} from './types'

type LoadState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }

type DeferredLoadState<T> = { status: 'idle' } | LoadState<T>

const statsPages: ProductPage[] = ['stats', 'courses', 'holes', 'clubs', 'issues', 'quality']

export default function App() {
  const [activePage, setActivePage] = useState<ProductPage>('overview')
  const [overviewState, setOverviewState] = useState<LoadState<HistoryOverviewResponse>>({ status: 'loading' })
  const [roundsState, setRoundsState] = useState<DeferredLoadState<HistoryRoundsResponse>>({ status: 'idle' })
  const [statsState, setStatsState] = useState<DeferredLoadState<HistoryStatsResponse>>({ status: 'idle' })
  const [annotationsState, setAnnotationsState] = useState<DeferredLoadState<AnnotationListResponse>>({ status: 'idle' })
  const [syncStatus, setSyncStatus] = useState<SyncStatusResponse | null>(null)

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
    if (page === 'history' && roundsState.status === 'idle') {
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

  function renderSyncPanel() {
    return syncStatus ? (
      <div className="app-shell sync-panel-shell">
        <SyncStatusPanel status={syncStatus} />
      </div>
    ) : null
  }

  function renderStatsContent(data: HistoryStatsResponse) {
    if (activePage === 'courses') return <CourseStats data={data} />
    if (activePage === 'holes') return <HoleStats data={data} />
    if (activePage === 'clubs') return <ClubStats data={data} />
    if (activePage === 'issues') return <IssueStats data={data} />
    if (activePage === 'quality') return <DataQualityPage data={data} />
    return <StatsOverview data={data} />
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

  if (activePage === 'history') {
    if (roundsState.status === 'ready') {
      return (
        <>
          {renderSyncPanel()}
          <HistoryTimeline data={roundsState.data} onNavigate={navigate} />
        </>
      )
    }

    if (roundsState.status === 'error') {
      return (
        <main className="app-shell">
          <section className="panel empty-state">
            <h1>History timeline unavailable</h1>
            <p>{roundsState.message}</p>
          </section>
        </main>
      )
    }

    return (
      <main className="app-shell">
        <section className="panel empty-state">
          <h1>Loading history timeline</h1>
        </section>
      </main>
    )
  }

  if (statsPages.includes(activePage)) {
    if (statsState.status === 'ready') {
      return (
        <>
          {renderSyncPanel()}
          <main className="app-shell">
            <ProductNav activePage={activePage} onNavigate={navigate} />
            {renderStatsContent(statsState.data)}
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

  if (activePage === 'corrections') {
    if (annotationsState.status === 'ready') {
      return (
        <>
          {renderSyncPanel()}
          <main className="app-shell">
            <ProductNav activePage={activePage} onNavigate={navigate} />
            <CorrectionsPage data={annotationsState.data} onCreateAnnotation={handleCreateAnnotation} />
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
      <HistoryOverview data={overviewState.data} onNavigate={navigate} />
    </>
  )
}
