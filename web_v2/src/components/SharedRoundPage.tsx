import { useEffect, useState } from 'react'
import { fetchSharedRound } from '../shareApi'
import type { SharedRoundResponse } from '../types'
import { ScorecardGrid } from './ScorecardGrid'

function dateText(value: string | null): string {
  if (!value) return '日期未知'
  const match = value.match(/^(\d{4}-\d{2}-\d{2})/)
  return match?.[1] ?? value
}

function toParText(value: number | null): string {
  if (value === null) return '—'
  if (value === 0) return 'E'
  return value > 0 ? `+${value}` : String(value)
}

export function SharedRoundPage({ token }: { token: string }): React.ReactElement {
  // Keyed by token so a token change shows loading without a synchronous setState in the effect.
  const [state, setState] = useState<
    | { token: string; status: 'ready'; data: SharedRoundResponse }
    | { token: string; status: 'error' }
    | null
  >(null)

  useEffect(() => {
    const meta = document.querySelector('meta[name="robots"]') ?? document.createElement('meta')
    meta.setAttribute('name', 'robots')
    meta.setAttribute('content', 'noindex, nofollow, noarchive')
    document.head.appendChild(meta)
    return () => {
      if (meta.parentNode) meta.parentNode.removeChild(meta)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchSharedRound(token)
      .then((data) => {
        if (!cancelled) setState({ token, status: 'ready', data })
      })
      .catch(() => {
        if (!cancelled) setState({ token, status: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [token])

  if (state === null || state.token !== token) {
    return <main className="shared-round-page"><section className="panel empty-state"><p>正在加载分享记分卡…</p></section></main>
  }
  // A failed fetch and a found:false/round:null response share one neutral expired state.
  if (state.status === 'error' || !state.data.found || state.data.round === null) {
    return (
      <main className="shared-round-page">
        <section className="panel empty-state" aria-live="polite">
          <h1>链接已失效</h1>
          <p>请向分享链接给你的人重新获取。</p>
        </section>
      </main>
    )
  }

  const data = state.data
  const round = state.data.round
  return (
    <main className="shared-round-page">
      <section className="panel shared-round-card" aria-labelledby="shared-round-title">
        <p className="eyebrow">只读分享</p>
        <h1 id="shared-round-title">{round.courseName}</h1>
        <p className="shared-round-date">{dateText(round.date)}</p>
        <div className="shared-round-summary" aria-label="球局成绩">
          <div><span>总杆</span><b>{round.score ?? '—'}</b></div>
          <div><span>标准杆</span><b>{round.par ?? '—'}</b></div>
          <div><span>成绩</span><b>{toParText(round.toPar)}</b></div>
          <div><span>洞数</span><b>{round.holesScored ?? '—'}</b></div>
        </div>
        <ScorecardGrid scorecard={data.scorecard} />
      </section>
    </main>
  )
}
