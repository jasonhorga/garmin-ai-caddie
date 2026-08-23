import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { HistoryTimeline } from './HistoryTimeline'
import { DiagnosticsProvider } from '../diagnosticsContext'
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

  it('renders a clear empty state in zh keyed off emptyState.kind', () => {
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

    expect(screen.getByText('还没有本地球局数据')).toBeInTheDocument()
    expect(screen.getByText('先在 设置·同步 里完成一次同步,球局会出现在这里。')).toBeInTheDocument()
    expect(screen.queryByText('No local Garmin rounds loaded')).not.toBeInTheDocument()
  })

  it('keeps the backend empty-state copy for unknown kinds', () => {
    render(
      <HistoryTimeline
        data={{
          schema: 'ai-caddie-history-rounds-v2',
          total: 0,
          groups: [],
          emptyState: {
            kind: 'filters_too_narrow',
            title: 'No rounds match the filters',
            detail: 'Relax the year or course filter to see rounds again.',
          },
        }}
      />,
    )

    expect(screen.getByText('No rounds match the filters')).toBeInTheDocument()
    expect(screen.getByText('Relax the year or course filter to see rounds again.')).toBeInTheDocument()
  })

  it('tags app-ingested rounds as AI Caddie and leaves Garmin rounds unmarked', () => {
    const mixed: HistoryRoundsResponse = {
      schema: 'ai-caddie-history-rounds-v2',
      total: 2,
      groups: [
        {
          key: '2026-05',
          label: 'May 2026',
          count: 2,
          average18: 88,
          bestScore: 82,
          rounds: [
            { ...payload.groups[0].rounds[0], id: 'g1', source: 'garmin' },
            {
              ...payload.groups[0].rounds[0],
              id: 'm1',
              courseName: '忘带表那场',
              source: 'manual',
            },
          ],
        },
      ],
      emptyState: null,
    }

    render(<HistoryTimeline data={mixed} />)
    // `manual` is the ingest/storage vocabulary shared by phone, Watch, and Web;
    // the product label must not falsely claim that every such round was hand-entered.
    expect(screen.getAllByText('AI Caddie')).toHaveLength(1)
    expect(screen.getByLabelText('AI Caddie 记录的球局')).toBeInTheDocument()
  })

  it('opens timeline round source refs', async () => {
    const onSelectRef = vi.fn()
    const onOpenRoundDetail = vi.fn()

    // The raw 来源 ref chip on a round card is owner-diagnostics-only now.
    render(
      <DiagnosticsProvider value={true}>
        <HistoryTimeline data={payload} onSelectRef={onSelectRef} onOpenRoundDetail={onOpenRoundDetail} />
      </DiagnosticsProvider>,
    )

    await userEvent.click(screen.getByRole('button', { name: '打开球局 Black Knight B，2026-05-20，成绩 82' }))
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

  it('submits text search and clears an evidence period filter', async () => {
    const onFilterChange = vi.fn()
    render(<HistoryTimeline data={filterData} filters={{ period: '2026-Q2' }} onFilterChange={onFilterChange} />)
    await userEvent.type(screen.getByRole('searchbox', { name: '搜索' }), 'Course A')
    await userEvent.click(screen.getByRole('button', { name: '搜索' }))
    expect(onFilterChange).toHaveBeenCalledWith({ period: '2026-Q2', query: 'Course A' })
    await userEvent.click(screen.getByRole('button', { name: '2026-Q2 · 清除' }))
    expect(onFilterChange).toHaveBeenCalledWith({ period: undefined, scoreBand: undefined })
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

  function firstPagePayload(loaded: number, serverTotal: number): HistoryRoundsResponse {
    const rounds = Array.from({ length: loaded }, (_, index) => syntheticRound(index + 1))
    return {
      schema: 'ai-caddie-history-rounds-v2',
      total: serverTotal,
      groups: [{ key: '2026-05', label: 'May 2026', count: loaded, average18: 82, bestScore: 76, rounds }],
      emptyState: null,
    }
  }

  it('counts the full server total and pulls the rest when revealing past the first page', async () => {
    const onLoadAll = vi.fn()
    // First page is 60 loaded; the server holds 200 in total.
    render(<HistoryTimeline data={firstPagePayload(60, 200)} onLoadAll={onLoadAll} />)

    // The count reflects the server truth (200 - 60), not just what is loaded.
    expect(screen.getByRole('button', { name: '加载更多(还有 140 场)' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /加载更多/ }))
    // Window advances 60→120, crossing the fetched 60 → ask the parent for the full archive.
    expect(onLoadAll).toHaveBeenCalledTimes(1)
  })

  it('shows a disabled 加载中 label while the full archive is being fetched', () => {
    render(<HistoryTimeline data={firstPagePayload(60, 200)} onLoadAll={() => undefined} loadingMore />)
    const button = screen.getByRole('button', { name: '加载中…' })
    expect(button).toBeInTheDocument()
    expect(button).toBeDisabled()
  })

  it('does not re-request the server once everything is loaded', async () => {
    const onLoadAll = vi.fn()
    // loaded === serverTotal → purely client-side reveal, no server pull.
    render(<HistoryTimeline data={firstPagePayload(80, 80)} onLoadAll={onLoadAll} />)

    await userEvent.click(screen.getByRole('button', { name: /加载更多/ }))
    expect(onLoadAll).not.toHaveBeenCalled()
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
