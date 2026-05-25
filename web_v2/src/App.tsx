import { useEffect, useState } from 'react'
import { fetchHistoryOverview, fetchSyncStatus } from './api'
import { HistoryOverview } from './components/HistoryOverview'
import { SyncStatusPanel } from './components/SyncStatusPanel'
import type { HistoryOverviewResponse, SyncStatusResponse } from './types'

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; data: HistoryOverviewResponse }
  | { status: 'error'; message: string }

export default function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [syncStatus, setSyncStatus] = useState<SyncStatusResponse | null>(null)

  useEffect(() => {
    let cancelled = false

    fetchHistoryOverview()
      .then((data) => {
        if (!cancelled) setState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
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

  if (state.status === 'loading') {
    return (
      <main className="app-shell">
        <section className="panel empty-state">
          <h1>Loading history</h1>
        </section>
      </main>
    )
  }

  if (state.status === 'error') {
    return (
      <main className="app-shell">
        <section className="panel empty-state">
          <h1>History API unavailable</h1>
          <p>{state.message}</p>
        </section>
      </main>
    )
  }

  return (
    <>
      {syncStatus ? (
        <div className="app-shell sync-panel-shell">
          <SyncStatusPanel status={syncStatus} />
        </div>
      ) : null}
      <HistoryOverview data={state.data} />
    </>
  )
}
