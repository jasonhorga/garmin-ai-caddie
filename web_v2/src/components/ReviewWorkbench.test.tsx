import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ReviewWorkbench } from './ReviewWorkbench'
import type { RoundCard, RoundHoleShotMapResponse, ScoreStripCell } from '../types'

const apiMocks = vi.hoisted(() => ({ prefetchTopoImage: vi.fn() }))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, prefetchTopoImage: apiMocks.prefetchTopoImage }
})

function cell(hole: number, par: number, score: number): ScoreStripCell {
  const toPar = score - par
  const className = toPar <= -1 ? 'birdie' : toPar === 0 ? 'par' : toPar === 1 ? 'bogey' : 'double'
  return { hole, par, score, toPar, className }
}

function round(overrides: Partial<RoundCard> = {}): RoundCard {
  return {
    id: '900001',
    date: '2026-05-20T08:00:00',
    courseName: 'Black Knight B',
    courseKey: 'black_knight',
    holesCompleted: 5,
    score: 84,
    par: 72,
    toPar: 12,
    primaryIssue: null,
    badges: [],
    scoreStrip: [
      cell(1, 5, 6), // +1 bogey (square)
      cell(2, 4, 4), // par (no frame)
      cell(3, 3, 5), // +2 double (double square)
      cell(4, 5, 4), // -1 birdie (circle)
      cell(5, 4, 7), // +3 triple (triangle)
    ],
    ...overrides,
  }
}

function shotMap(hole: number): RoundHoleShotMapResponse {
  return {
    schema: 'ai-caddie-round-hole-shotmap-v1',
    found: true,
    roundRef: '900001',
    hole,
    par: 5,
    map: {
      image: 'data:image/png;base64,AAAA',
      overlay: { w: 300, h: 470, ppm: 1, ln: 400, route: [[150, 455, 0], [150, 72, 400]] },
    },
    shots: [
      { start: [150, 455], end: [128, 270], club: '一号木', lie: 'TeeBox', endLie: 'Fairway', shotType: 'TEE', order: 1, synthetic: false },
      { start: [128, 270], end: [182, 120], club: '五号木', lie: 'Fairway', endLie: 'Bunker', shotType: 'APPROACH', order: 2, synthetic: false },
      { start: [182, 120], end: [150, 72], club: '推杆', lie: 'Green', endLie: 'Green', shotType: 'PUTT', order: 3, synthetic: false },
    ],
    missingData: [],
  }
}

describe('ReviewWorkbench', () => {
  beforeEach(() => apiMocks.prefetchTopoImage.mockClear())

  it('renders the round selector, total and shape-coded score chips reflecting to-par', async () => {
    const fetchShotMap = vi.fn(async (_ref: string, hole: number) => shotMap(hole))
    render(<ReviewWorkbench rounds={[round()]} fetchShotMap={fetchShotMap} />)

    // Top bar: selector + total.
    expect(screen.getByLabelText('选择球局')).toBeInTheDocument()
    const total = screen.getByText('总杆').closest('.review-total') as HTMLElement
    expect(within(total).getByText('84')).toBeInTheDocument()
    expect(within(total).getByText('· +12')).toBeInTheDocument()

    // Shape families come straight from the real to-par.
    expect(screen.getByLabelText('柏忌 6')).toBeInTheDocument() // hole 1: +1 square
    expect(screen.getByLabelText('标准杆 4')).toBeInTheDocument() // hole 2: par, no frame
    expect(screen.getByLabelText('双柏忌 5')).toBeInTheDocument() // hole 3: +2
    expect(screen.getByLabelText('小鸟 4')).toBeInTheDocument() // hole 4: -1 circle
    expect(screen.getByLabelText('三柏忌以上 7')).toBeInTheDocument() // hole 5: +3 triangle
    const canvas = await screen.findByLabelText('第1洞落点图')
    expect(within(canvas).getByText(/一号木/)).toBeInTheDocument()
  })

  it('uses a celebratory under-par tone for a negative round total', async () => {
    const fetchShotMap = vi.fn(async (_ref: string, hole: number) => shotMap(hole))
    render(<ReviewWorkbench rounds={[round({ toPar: -2 })]} fetchShotMap={fetchShotMap} />)
    expect(screen.getByText('· -2')).toHaveClass('score-under')
    const canvas = await screen.findByLabelText('第1洞落点图')
    expect(within(canvas).getByText(/一号木/)).toBeInTheDocument()
  })

  it('loads the selected hole shot map and overlays club, distance, and result on each landing', async () => {
    const fetchShotMap = vi.fn(async (_ref: string, hole: number) => shotMap(hole))
    render(<ReviewWorkbench rounds={[round()]} fetchShotMap={fetchShotMap} />)

    // Hole 1 auto-selects → its shot map loads.
    await waitFor(() => expect(fetchShotMap).toHaveBeenCalledWith('900001', 1))
    const canvas = await screen.findByLabelText('第1洞落点图')
    expect(within(canvas).getByText(/一号木 · \d+码 · →球道/)).toBeInTheDocument()
    expect(within(canvas).getByText(/五号木 · \d+码 · →沙坑/)).toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: '杆序' })).not.toBeInTheDocument()
  })

  it('shows read-only corrections and penalty directly on the map', async () => {
    const corrected: RoundHoleShotMapResponse = {
      ...shotMap(1),
      manualPenalty: 2,
      shots: [
        { start: [150, 455], end: [128, 270], club: '一号木', lie: 'TeeBox', endLie: 'Fairway', shotType: 'TEE', order: 1, synthetic: false },
        // The player corrected this approach's club → backend tags it clubSource:"manual".
        { start: [128, 270], end: [182, 120], club: '九号铁', lie: 'Fairway', endLie: 'Bunker', shotType: 'APPROACH', order: 2, synthetic: false, clubSource: 'manual' },
        { start: [182, 120], end: [150, 72], club: '推杆', lie: 'Green', endLie: 'Green', shotType: 'PUTT', order: 3, synthetic: false },
      ],
    }
    const fetchShotMap = vi.fn(async () => corrected)
    render(<ReviewWorkbench rounds={[round()]} fetchShotMap={fetchShotMap} />)

    const canvas = await screen.findByLabelText('第1洞落点图')
    expect(within(canvas).getByText('罚杆 +2')).toBeInTheDocument()
    expect(within(canvas).getByText(/九号铁 · .*已修正/)).toBeInTheDocument()
    expect(within(canvas).getByText(/推杆 ×1/)).toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: '杆序' })).not.toBeInTheDocument()
  })

  it('does not show a penalty badge when none was hand-added', async () => {
    const fetchShotMap = vi.fn(async (_ref: string, hole: number) => shotMap(hole))
    render(<ReviewWorkbench rounds={[round()]} fetchShotMap={fetchShotMap} />)
    await screen.findByLabelText('第1洞落点图')
    expect(screen.queryByRole('complementary', { name: '杆序' })).not.toBeInTheDocument()
    expect(screen.queryByText(/本洞手填罚杆/)).toBeNull()
  })

  it('re-fetches the shot map when a different hole is selected', async () => {
    const fetchShotMap = vi.fn(async (_ref: string, hole: number) => shotMap(hole))
    render(<ReviewWorkbench rounds={[round()]} fetchShotMap={fetchShotMap} />)
    await waitFor(() => expect(fetchShotMap).toHaveBeenCalledWith('900001', 1))

    await userEvent.click(screen.getByRole('button', { name: '第3洞 标准杆3 成绩5' }))
    await waitFor(() => expect(fetchShotMap).toHaveBeenCalledWith('900001', 3))
    expect(await screen.findByLabelText('第3洞落点图')).toBeInTheDocument()
  })

  it('never reuses the selected hole revision when warming adjacent topo images', async () => {
    const currentHole = {
      ...shotMap(2),
      globalId: 3881,
      localHole: 2,
      geometryRevision: 'current-hole-only-revision',
    }
    render(<ReviewWorkbench rounds={[round({ scoreStrip: [cell(2, 4, 4)] })]} fetchShotMap={vi.fn(async () => currentHole)} />)

    await waitFor(() => expect(apiMocks.prefetchTopoImage).toHaveBeenCalledTimes(2))
    const urls = apiMocks.prefetchTopoImage.mock.calls.map(([url]) => String(url))
    expect(urls).toEqual([
      '/api/v2/courses/3881/holes/1/topo.png?v=topo-v8',
      '/api/v2/courses/3881/holes/3/topo.png?v=topo-v8',
    ])
    expect(urls.join('\n')).not.toContain('current-hole-only-revision')
    expect(urls.join('\n')).not.toContain('&r=')
  })

  it('shows a graceful empty state with no rounds', () => {
    render(<ReviewWorkbench rounds={[]} fetchShotMap={vi.fn()} />)
    expect(screen.getByText('还没有可复盘的球局')).toBeInTheDocument()
  })

  it('falls back gracefully when a hole has no geometry', async () => {
    const fetchShotMap = vi.fn(async (): Promise<RoundHoleShotMapResponse> => ({
      schema: 'ai-caddie-round-hole-shotmap-v1',
      found: true,
      roundRef: '900001',
      hole: 1,
      par: 5,
      map: null,
      shots: [],
      missingData: [{ label: 'geometry', reason: '这一洞暂无球场几何,画不了落点图' }],
    }))
    render(<ReviewWorkbench rounds={[round()]} fetchShotMap={fetchShotMap} />)
    expect(await screen.findByText('这一洞暂无球场几何,画不了落点图')).toBeInTheDocument()
  })
})
