import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SharedRoundPage } from './SharedRoundPage'

const fetchSharedRound = vi.fn()
vi.mock('../shareApi', () => ({ fetchSharedRound }))

const scorecard = Array.from({ length: 18 }, (_, index) => ({
  hole: index + 1,
  par: 4,
  score: 4,
  toPar: 0,
  putts: 2,
  penalties: 0,
  gir: true,
  fairway: 'hit',
}))

describe('SharedRoundPage', () => {
  beforeEach(() => fetchSharedRound.mockReset())

  it('renders the fixed read-only scorecard without diagnostics or mutation controls', async () => {
    fetchSharedRound.mockResolvedValue({
      schema: 'ai-caddie-shared-round-v1',
      found: true,
      expiresAt: '2026-06-19T00:00:00Z',
      round: { id: 'fixture-18-par', date: '2026-05-20T08:00:00Z', courseName: 'Fixture Orchard', score: 72, par: 72, toPar: 0, holesScored: 18 },
      scorecard,
    })
    render(<SharedRoundPage token="A-token" />)
    expect(await screen.findByRole('heading', { name: 'Fixture Orchard' })).toBeInTheDocument()
    expect(screen.getByText('72')).toBeInTheDocument()
    expect(screen.getByLabelText('前九记分卡')).toBeInTheDocument()
    expect(screen.getByLabelText('后九记分卡')).toBeInTheDocument()
    expect(screen.queryByText('相关来源')).not.toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(document.querySelector('meta[name="robots"]')?.getAttribute('content')).toBe('noindex, nofollow, noarchive')
  })

  it('shows one neutral expired-link state for a failed fetch', async () => {
    fetchSharedRound.mockRejectedValue(new Error('404'))
    render(<SharedRoundPage token="expired-token" />)
    await waitFor(() => expect(screen.getByRole('heading', { name: '链接已失效' })).toBeInTheDocument())
    expect(screen.queryByText(/Fixture/)).not.toBeInTheDocument()
  })
})
