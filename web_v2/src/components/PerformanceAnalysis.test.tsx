import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { MobileStatsResponse } from '../types'
import { PerformanceAnalysis } from './PerformanceAnalysis'

const stats = {
  schema: 'ai-caddie-mobile-stats-v1', dataMode: 'fixture',
  summary: { totalRounds: 10 }, time: {}, records: {}, courses: [], clubs: [], dataQuality: [],
  scoring: {
    phaseStats: [
      { phase: 'Tee', fairwaysHit: 6, fairwaysRecorded: 10, fairwayMissLeft: 2, fairwayMissRight: 2 },
      { phase: 'Approach', gir: 4, girRecorded: 9 },
    ],
    putting: { averagePuttsPerRound: 32.5, roundsWithPutts: 7, totalPutts: 228 },
    outcomes: { birdie: 2, par: 8, bogey: 6, doubleOrWorse: 2 },
    byPar: [{ par: 4, holeCount: 12, parOrBetter: 5, parOrBetterPct: 41.7, averageToPar: .7 }],
    scoreBands: [{ label: '80s', count: 4, roundIds: ['r1'] }],
  },
} as MobileStatsResponse

describe('PerformanceAnalysis', () => {
  it('shows real numerators/denominators and honest unknown penalty coverage', () => {
    render(<PerformanceAnalysis stats={stats} window="last10" onWindowChange={() => undefined} />)
    expect(within(screen.getByText('开球').closest('article')!).getByText(/6\/10/)).toBeInTheDocument()
    expect(within(screen.getByText('攻果岭').closest('article')!).getByText(/4\/9/)).toBeInTheDocument()
    expect(within(screen.getByText('推杆').closest('article')!).getByText(/7\/10/)).toBeInTheDocument()
    expect(within(screen.getByText('罚杆').closest('article')!).getByText(/可靠分母/)).toBeInTheDocument()
    expect(screen.getByText(/保帕 5\/12/)).toBeInTheDocument()
  })

  it('drills score bands and keeps result-club navigation distinct from bag configuration', async () => {
    const onOpenScoreBand = vi.fn()
    const onNavigateClubs = vi.fn()
    render(<PerformanceAnalysis stats={stats} window="last10" onWindowChange={() => undefined} onOpenScoreBand={onOpenScoreBand} onNavigateClubs={onNavigateClubs} />)
    await userEvent.click(screen.getByRole('button', { name: /80–89/ }))
    expect(onOpenScoreBand).toHaveBeenCalledWith('80s')
    await userEvent.click(screen.getByRole('button', { name: /球杆表现/ }))
    expect(onNavigateClubs).toHaveBeenCalled()
    expect(screen.queryByText(/估算失杆/)).not.toBeInTheDocument()
  })
})
