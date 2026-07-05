import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ReviewWorkbench } from './ReviewWorkbench'
import type { RoundCard, RoundHoleShotMapResponse, ScoreStripCell } from '../types'

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
  })

  it('loads the selected hole shot map and renders the 杆序 timeline (club + distance + putts)', async () => {
    const fetchShotMap = vi.fn(async (_ref: string, hole: number) => shotMap(hole))
    render(<ReviewWorkbench rounds={[round()]} fetchShotMap={fetchShotMap} />)

    // Hole 1 auto-selects → its shot map loads.
    await waitFor(() => expect(fetchShotMap).toHaveBeenCalledWith('900001', 1))
    // Club now appears BOTH on the map (review-canvas-chip) and in the 杆序 timeline, so
    // scope the timeline assertions to the 杆序 aside to disambiguate.
    const timeline = await screen.findByRole('complementary', { name: '杆序' })
    expect(await within(timeline).findByText('一号木')).toBeInTheDocument()
    expect(within(timeline).getByText('五号木')).toBeInTheDocument()
    // The two-shot trajectory yardage is derived from the overlay ppm scale.
    expect(screen.getByText('→ 沙坑')).toBeInTheDocument()
    // The recorded putt collapses to a ×1 row.
    expect(screen.getByText('×1')).toBeInTheDocument()
    // The落点图 canvas renders on the real geometry.
    expect(screen.getByLabelText('第1洞落点图')).toBeInTheDocument()
  })

  it('re-fetches the shot map when a different hole is selected', async () => {
    const fetchShotMap = vi.fn(async (_ref: string, hole: number) => shotMap(hole))
    render(<ReviewWorkbench rounds={[round()]} fetchShotMap={fetchShotMap} />)
    await waitFor(() => expect(fetchShotMap).toHaveBeenCalledWith('900001', 1))

    await userEvent.click(screen.getByRole('button', { name: '第3洞 标准杆3 成绩5' }))
    await waitFor(() => expect(fetchShotMap).toHaveBeenCalledWith('900001', 3))
    expect(await screen.findByLabelText('第3洞落点图')).toBeInTheDocument()
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
