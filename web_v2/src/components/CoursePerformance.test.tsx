import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { MobileCourseOptionsResponse, MobileStatsResponse } from '../types'
import { CoursePerformance } from './CoursePerformance'

const stats = {
  schema: 'ai-caddie-mobile-stats-v1', dataMode: 'fixture', summary: {}, time: {}, scoring: {}, records: {}, clubs: [], dataQuality: [],
  courses: [{
    courseKey: 'hmb', courseName: 'Half Moon Bay', roundCount: 3, average18: 86.3, bestScore: 82, recentRoundId: 'r3',
    nineBreakdown: [{ label: 'Ocean / Old', roundCount: 2, average: 43, bestScore: 40 }],
    rounds: [{ roundId: 'r3', date: '2026-08-12', holesCompleted: 18, score: 82, toPar: 10 }],
  }],
} as MobileStatsResponse

const options = {
  schema: 'ai-caddie-mobile-course-options-v1', dataMode: 'fixture', total: 1, emptyState: null, generatedAt: '2026-08-12T00:00:00Z',
  courses: [{ globalId: 123, courseKey: 'hmb', name: 'Half Moon Bay', roundCount: 3, holes: 18, geometryCoverage: 'ready', sourceRefs: [] }],
} as MobileCourseOptionsResponse

describe('CoursePerformance', () => {
  it('shows evidence-backed course metrics and drills into a round or prep', async () => {
    const onOpenRound = vi.fn()
    const onPrepCourse = vi.fn()
    render(<CoursePerformance stats={stats} courseOptions={options} window="all" onWindowChange={() => undefined} onOpenRound={onOpenRound} onPrepCourse={onPrepCourse} />)
    expect(screen.getByText(/3 场 · 均杆 86.3 · 最佳 82/)).toBeInTheDocument()
    await userEvent.click(screen.getByText('Half Moon Bay'))
    await userEvent.click(screen.getByRole('button', { name: /2026-08-12/ }))
    expect(onOpenRound).toHaveBeenCalledWith('r3')
    await userEvent.click(screen.getByRole('button', { name: /去备战/ }))
    expect(onPrepCourse).toHaveBeenCalledWith(123, 'Half Moon Bay')
    expect(screen.queryByText(/风险/)).not.toBeInTheDocument()
  })
})
