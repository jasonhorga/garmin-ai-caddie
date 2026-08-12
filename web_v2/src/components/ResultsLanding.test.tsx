import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { HistoryOverviewResponse, HistoryStatsSummaryResponse, MobileStatsResponse } from '../types'
import { ResultsLanding } from './ResultsLanding'

const overview = {
  schema: 'ai-caddie-history-overview-v2',
  metrics: { totalRounds: 2, eighteenHoleRounds: 2, nineHoleRounds: 0, courseCount: 1, shotCount: 20, average18: 85, recent10Average: 85, bestScore: 82 },
  recentRounds: [{ id: 'r2', date: '2026-06-01', courseName: 'Course A', courseKey: 'a', holesCompleted: 18, score: 82, par: 72, toPar: 10, primaryIssue: null, badges: [], scoreStrip: [] }],
  distribution: { total: 2, average: 85, best: 82, worst: 88, families: [], histogram: [] },
  dataQuality: [], emptyState: null,
} as HistoryOverviewResponse

const summary = { schema: 'ai-caddie-history-summary-v1', summary: { totalRounds: 2, eighteenHoleRounds: 2, courseCount: 1, average18: 85, recent10Average: 85, recent20Average: 86, bestScore: 82 }, topIssue: null } as HistoryStatsSummaryResponse
const stats = { schema: 'ai-caddie-mobile-stats-v1', dataMode: 'fixture', summary: {}, time: { byYear: [{ key: '2026', roundCount: 2 }] }, scoring: { phaseStats: [] }, records: {}, courses: [{ courseKey: 'a' }], clubs: [{ club: '7I' }], dataQuality: [] } as MobileStatsResponse

describe('ResultsLanding', () => {
  it('is answer-first and routes archive, trends, analysis, courses and result-clubs', async () => {
    const onNavigate = vi.fn()
    const onOpenRound = vi.fn()
    render(<ResultsLanding overview={overview} summary={summary} recentStats={stats} onNavigate={onNavigate} onOpenRound={onOpenRound} />)
    expect(screen.getByRole('heading', { name: '成绩' })).toBeInTheDocument()
    expect(screen.getByText('近 10 场 85 · 近 20 场 86')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /全部球局/ }))
    expect(onNavigate).toHaveBeenCalledWith('rounds')
    await userEvent.click(screen.getByRole('button', { name: /^时间趋势/ }))
    expect(onNavigate).toHaveBeenCalledWith('history')
    await userEvent.click(screen.getByRole('button', { name: /表现分析/ }))
    expect(onNavigate).toHaveBeenCalledWith('holes')
    await userEvent.click(screen.getByRole('button', { name: /球杆/ }))
    expect(onNavigate).toHaveBeenCalledWith('result-clubs')
    await userEvent.click(screen.getByRole('button', { name: /Course A/ }))
    expect(onOpenRound).toHaveBeenCalledWith('r2')
  })
})
