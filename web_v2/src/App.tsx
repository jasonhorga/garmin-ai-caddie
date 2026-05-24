import { useEffect, useState } from 'react'
import { fetchHistoryOverview } from './api'
import { HistoryOverview } from './components/HistoryOverview'
import type { HistoryOverviewResponse } from './types'

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; data: HistoryOverviewResponse }
  | { status: 'error'; message: string }

export default function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false

    fetchHistoryOverview()
      .then((data) => {
        if (!cancelled) setState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
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

  return <HistoryOverview data={state.data} />
}
