import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { HistoryTimeline } from './HistoryTimeline'
import type { HistoryRoundsResponse, RoundCard } from '../types'

const payload: HistoryRoundsResponse = {
  schema: 'ai-caddie-history-rounds-v2',
  total: 2,
  groups: [
    {
      key: '2026-05',
      label: 'May 2026',
      count: 2,
      average18: 82,
      bestScore: 82,
      rounds: [
        {
          id: '1',
          date: '2026-05-20T08:00:00',
          courseName: 'Black Knight B',
          courseKey: 'c_black',
          holesCompleted: 18,
          score: 82,
          par: 72,
          toPar: 10,
          primaryIssue: null,
          badges: [{ label: 'shots', state: 'good', value: 'ready', reason: 'ready' }],
          scoreStrip: [{ hole: 1, par: 4, score: 4, toPar: 0, className: 'par' }],
        },
      ],
    },
  ],
  emptyState: null,
}

describe('HistoryTimeline', () => {
  it('renders month-grouped round cards and month summary stats', () => {
    render(<HistoryTimeline data={payload} />)

    expect(screen.getByRole('heading', { name: '球局', level: 1 })).toBeInTheDocument()
    expect(screen.queryByText('AI Caddie v2')).not.toBeInTheDocument()
    expect(screen.getByText('2026年5月')).toBeInTheDocument()
    expect(screen.getByText('2 场')).toBeInTheDocument()
    expect(screen.getByText('均 82')).toBeInTheDocument()
    expect(screen.getByText('最佳 82')).toBeInTheDocument()
    expect(screen.getByText('Black Knight B')).toBeInTheDocument()
  })

  it('renders a clear empty state', () => {
    render(
      <HistoryTimeline
        data={{
          schema: 'ai-caddie-history-rounds-v2',
          total: 0,
          groups: [],
          emptyState: {
            kind: 'no_rounds',
            title: 'No local Garmin rounds loaded',
            detail: 'The History timeline is ready, but this remote workspace has 0 rounds.',
          },
        }}
      />,
    )

    expect(screen.getByText('No local Garmin rounds loaded')).toBeInTheDocument()
    expect(screen.getByText(/this remote workspace has 0 rounds/i)).toBeInTheDocument()
  })

  it('opens timeline round source refs', async () => {
    const onSelectRef = vi.fn()
    const onOpenRoundDetail = vi.fn()

    render(<HistoryTimeline data={payload} onSelectRef={onSelectRef} onOpenRoundDetail={onOpenRoundDetail} />)

    await userEvent.click(screen.getByRole('button', { name: '打开球局 Black Knight B, 2026-05-20T08:00:00, score 82, ref 1' }))
    await userEvent.click(screen.getByRole('button', { name: 'Open source 1' }))

    expect(onOpenRoundDetail).toHaveBeenCalledWith('1')
    expect(onSelectRef).toHaveBeenCalledWith('1')
    expect(onSelectRef).toHaveBeenCalledTimes(1)
  })

  const filterData: HistoryRoundsResponse = {
    ...payload,
    availableYears: ['2026', '2025'],
    availableCourses: [
      { key: 'ca', label: 'Course A' },
      { key: 'cb', label: 'Course B' },
    ],
    appliedFilters: {},
  }

  it('renders year and course filter options when filtering is enabled', () => {
    render(<HistoryTimeline data={filterData} filters={{}} onFilterChange={() => undefined} />)

    expect(screen.getByRole('option', { name: '2026' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Course A' })).toBeInTheDocument()
  })

  it('emits filter changes for the year select and the has-shots toggle', async () => {
    const onFilterChange = vi.fn()
    render(<HistoryTimeline data={filterData} filters={{}} onFilterChange={onFilterChange} />)

    await userEvent.selectOptions(screen.getByLabelText('年份'), '2026')
    expect(onFilterChange).toHaveBeenCalledWith({ year: '2026' })

    await userEvent.click(screen.getByLabelText('有击球'))
    expect(onFilterChange).toHaveBeenCalledWith({ hasShots: true })
  })

  it('omits the filter bar when filtering is not enabled', () => {
    render(<HistoryTimeline data={filterData} />)
    expect(screen.queryByLabelText('年份')).toBeNull()
  })
})

// 435 real rounds rendered every card at once and froze the page — display
// truncation only: first 60 cards, 加载更多 appends batches, any filter change
// resets the visible window. Data stays untouched.
describe('HistoryTimeline 截断与加载更多', () => {
  function syntheticRound(id: number): RoundCard {
    return {
      id: String(id),
      date: '2026-05-01T08:00:00',
      courseName: `Course ${id}`,
      courseKey: 'ck',
      holesCompleted: 18,
      score: 82,
      par: 72,
      toPar: 10,
      primaryIssue: null,
      badges: [],
      scoreStrip: [],
    }
  }

  function bigPayload(): HistoryRoundsResponse {
    const first = Array.from({ length: 40 }, (_, index) => syntheticRound(index + 1))
    const second = Array.from({ length: 40 }, (_, index) => syntheticRound(index + 41))
    return {
      schema: 'ai-caddie-history-rounds-v2',
      total: 80,
      groups: [
        { key: '2026-05', label: 'May 2026', count: 40, average18: 82, bestScore: 76, rounds: first },
        { key: '2026-04', label: 'April 2026', count: 40, average18: 83, bestScore: 78, rounds: second },
      ],
      emptyState: null,
      availableYears: ['2026'],
      availableCourses: [{ key: 'ck', label: 'Course' }],
      appliedFilters: {},
    }
  }

  function visibleRoundCards(container: HTMLElement): number {
    return container.querySelectorAll('.round-card').length
  }

  it('renders only the first 60 rounds initially with a zh 加载更多 button', () => {
    const { container } = render(<HistoryTimeline data={bigPayload()} />)

    expect(visibleRoundCards(container)).toBe(60)
    expect(screen.getByRole('button', { name: '加载更多(还有 20 场)' })).toBeInTheDocument()
    // the truncation cuts inside April — May stays complete
    expect(screen.getByText('Course 60')).toBeInTheDocument()
    expect(screen.queryByText('Course 61')).not.toBeInTheDocument()
  })

  it('加载更多 appends the next batch and disappears once everything is visible', async () => {
    const { container } = render(<HistoryTimeline data={bigPayload()} />)

    await userEvent.click(screen.getByRole('button', { name: /加载更多/ }))

    expect(visibleRoundCards(container)).toBe(80)
    expect(screen.getByText('Course 80')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /加载更多/ })).not.toBeInTheDocument()
  })

  it('renders no 加载更多 button when the payload is under the cap', () => {
    render(<HistoryTimeline data={payload} />)
    expect(screen.queryByRole('button', { name: /加载更多/ })).not.toBeInTheDocument()
  })

  it('resets the visible window when any filter changes', async () => {
    const data = bigPayload()
    const { container, rerender } = render(<HistoryTimeline data={data} filters={{}} onFilterChange={() => undefined} />)

    await userEvent.click(screen.getByRole('button', { name: /加载更多/ }))
    expect(visibleRoundCards(container)).toBe(80)

    rerender(<HistoryTimeline data={data} filters={{ year: '2026' }} onFilterChange={() => undefined} />)

    expect(visibleRoundCards(container)).toBe(60)
    expect(screen.getByRole('button', { name: '加载更多(还有 20 场)' })).toBeInTheDocument()
  })
})
