import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { MobileStatsResponse } from '../types'
import { TimeTrends } from './TimeTrends'

const stats = {
  schema: 'ai-caddie-mobile-stats-v1', dataMode: 'fixture', summary: { totalRounds: 2, average18: 85, bestScore: 82, median18: 85 },
  trend: { points: [{ date: '2026-05-01', score: 88, roundId: 'r1' }, { date: '2026-06-01', score: 82, roundId: 'r2' }] },
  time: {
    byMonth: [{ key: '2026-06', roundCount: 1, average18: 82, bestScore: 82 }, { key: '2026-05', roundCount: 1, average18: 88, bestScore: 88 }],
    byQuarter: [{ key: '2026-Q2', roundCount: 2, average18: 85, bestScore: 82 }],
    byYear: [{ key: '2026', roundCount: 2, average18: 85, bestScore: 82 }],
    byDay: [{ key: '2026-06-01', roundCount: 1 }],
    playFrequency: { totalMonths: 2, roundsPerMonth: 1, mostActiveMonth: { key: '2026-06', roundCount: 1 } },
  }, scoring: {}, records: {}, courses: [], clubs: [], dataQuality: [],
} as MobileStatsResponse

describe('TimeTrends', () => {
  it('separates range from granularity and enforces valid combinations', async () => {
    const onWindowChange = vi.fn()
    render(<TimeTrends stats={stats} allStats={stats} window="last10" onWindowChange={onWindowChange} onOpenRound={() => undefined} onOpenPeriod={() => undefined} />)
    expect(screen.getByRole('button', { name: '逐场' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '月' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '年' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: '近 12 月' }))
    expect(onWindowChange).toHaveBeenCalledWith('12m')
  })

  it('opens chart evidence, period rows and active calendar days', async () => {
    const onOpenRound = vi.fn()
    const onOpenPeriod = vi.fn()
    render(<TimeTrends stats={stats} allStats={stats} window="last10" onWindowChange={() => undefined} onOpenRound={onOpenRound} onOpenPeriod={onOpenPeriod} />)
    await userEvent.click(screen.getByRole('button', { name: /2026-06-01，82 杆/ }))
    expect(onOpenRound).toHaveBeenCalledWith('r2')
    await userEvent.click(screen.getByRole('button', { name: /2026 年/ }))
    expect(onOpenPeriod).toHaveBeenCalledWith('2026')
    await userEvent.click(screen.getByRole('button', { name: /2026-06-01，1 场/ }))
    expect(onOpenPeriod).toHaveBeenCalledWith('2026-06-01')
  })

  it('plots a lower golf score below a higher score on the numeric y-axis', () => {
    render(<TimeTrends stats={stats} allStats={stats} window="last10" onWindowChange={() => undefined} onOpenRound={() => undefined} onOpenPeriod={() => undefined} />)
    const higherScoreY = Number(screen.getByRole('button', { name: /2026-05-01，88 杆/ }).getAttribute('cy'))
    const lowerScoreY = Number(screen.getByRole('button', { name: /2026-06-01，82 杆/ }).getAttribute('cy'))
    expect(higherScoreY).toBeLessThan(lowerScoreY)
  })
})
