import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { HistoryTimeline } from './HistoryTimeline'
import type { HistoryRoundsResponse } from '../types'

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

    expect(screen.getByRole('heading', { name: 'Rounds' })).toBeInTheDocument()
    expect(screen.queryByText('AI Caddie v2')).not.toBeInTheDocument()
    expect(screen.getByText('May 2026')).toBeInTheDocument()
    expect(screen.getByText('2 rounds')).toBeInTheDocument()
    expect(screen.getByText('avg 82')).toBeInTheDocument()
    expect(screen.getByText('best 82')).toBeInTheDocument()
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

    await userEvent.click(screen.getByRole('button', { name: 'Open round Black Knight B, 2026-05-20T08:00:00, score 82, ref 1' }))
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

    await userEvent.selectOptions(screen.getByLabelText('Year'), '2026')
    expect(onFilterChange).toHaveBeenCalledWith({ year: '2026' })

    await userEvent.click(screen.getByLabelText('Has shots'))
    expect(onFilterChange).toHaveBeenCalledWith({ hasShots: true })
  })

  it('omits the filter bar when filtering is not enabled', () => {
    render(<HistoryTimeline data={filterData} />)
    expect(screen.queryByLabelText('Year')).toBeNull()
  })
})
