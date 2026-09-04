import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BagPage } from './BagPage'
import { fetchPlayerClubBag, putPlayerClubBag } from '../api'
import type { EffectiveClubBagResponse } from '../types'

vi.mock('../api', () => ({
  fetchPlayerClubBag: vi.fn(),
  putPlayerClubBag: vi.fn(),
}))

// Measured per-club stats (metres) from shot records. '1D' → driver, '7I' → iron7.
// 'PW' has no measured row → the pw club shows 数据不足 for the band / sample.
const measuredClubs = [
  { club: '1D', median: 200, p10: 190, p90: 212, sampleCount: 41, confidence: 'high' },
  { club: '7I', median: 140, p10: 132, p90: 150, sampleCount: 64, confidence: 'medium' },
]

// Effective bag: driver carries a synced 205m; iron7 has NO bag distance (falls back
// to its measured median); pw carries a synced 100m but has no measured samples.
const bag: EffectiveClubBagResponse = {
  schema: 'ai-caddie-effective-club-bag-v1',
  source: 'garmin',
  found: true,
  clubs: [
    { token: 'driver', zhName: '一号木', customName: null, clubTypeId: 1, distanceM: 205, distanceSource: null },
    { token: 'iron7', zhName: '七号铁', customName: null, clubTypeId: 16, distanceM: null, distanceSource: null },
    { token: 'pw', zhName: 'P杆', customName: null, clubTypeId: 19, distanceM: 100, distanceSource: null },
  ],
}

const emptyBag: EffectiveClubBagResponse = {
  schema: 'ai-caddie-effective-club-bag-v1',
  source: 'none',
  found: false,
  clubs: [],
}

describe('BagPage', () => {
  beforeEach(() => {
    vi.mocked(fetchPlayerClubBag).mockResolvedValue(bag)
    vi.mocked(putPlayerClubBag).mockResolvedValue(bag)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders the ladder + table from real bag/measured data, sorted long→short', async () => {
    render(<BagPage measuredClubs={measuredClubs} adminToken="admin-secret" onNavigate={vi.fn()} />)
    await screen.findByRole('button', { name: '一号木 距离条' })
    expect(fetchPlayerClubBag).toHaveBeenCalledWith('me', 'admin-secret')

    // Table renders every club; carry P50 = bag distance (driver 205m→224y), and iron7
    // (no bag distance) falls back to its measured median (140m→153y).
    const table = screen.getByRole('table')
    const driverRow = within(table).getByRole('row', { name: /一号木/ })
    expect(within(driverRow).getByText('224')).toBeInTheDocument()
    expect(within(driverRow).getByText('208–232')).toBeInTheDocument() // P10–P90 (190/212m)
    expect(within(driverRow).getByText('41')).toBeInTheDocument() // sample
    const iron7Row = within(table).getByRole('row', { name: /七号铁/ })
    expect(within(iron7Row).getByText('153')).toBeInTheDocument()
  })

  it('shows 数据不足 for a club with no measured samples and never invents Total / 左右', async () => {
    render(<BagPage measuredClubs={measuredClubs} adminToken="admin-secret" onNavigate={vi.fn()} />)
    await screen.findByRole('button', { name: 'P杆 距离条' })

    // The mockup's Total & 左右偏差 aren't in either payload → those columns are omitted.
    const headerRow = within(screen.getByRole('table')).getAllByRole('row')[0]
    expect(within(headerRow).queryByText('Total')).not.toBeInTheDocument()
    expect(within(headerRow).queryByText('左右')).not.toBeInTheDocument()
    expect(within(headerRow).getByText('P10–P90')).toBeInTheDocument()

    // pw has no measured row → its band cell reads 数据不足 (honest, not fabricated).
    const pwRow = within(screen.getByRole('table')).getByRole('row', { name: /P杆/ })
    expect(within(pwRow).getByText('数据不足')).toBeInTheDocument()
  })

  it('selects a club from the table and saves a manual distance (yards → metres)', async () => {
    render(<BagPage measuredClubs={measuredClubs} adminToken="admin-secret" onNavigate={vi.fn()} />)
    await screen.findByRole('button', { name: '一号木 距离条' })

    const iron7Row = within(screen.getByRole('table')).getByRole('row', { name: /七号铁/ })
    await userEvent.click(within(iron7Row).getByRole('button', { name: '编辑' }))

    const field = await screen.findByLabelText('七号铁 手动距离(码)')
    await userEvent.clear(field)
    await userEvent.type(field, '150')
    await userEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(putPlayerClubBag).toHaveBeenCalled())
    const [pid, body, tok] = vi.mocked(putPlayerClubBag).mock.calls[0]
    expect(pid).toBe('me')
    expect(tok).toBe('admin-secret')
    // 150y → 137m for iron7; every other club keeps its existing distance.
    expect(body.clubs.find((c) => c.token === 'iron7')?.distanceM).toBe(137)
    expect(body.clubs.find((c) => c.token === 'driver')?.distanceM).toBe(205)
    expect(body.clubs.find((c) => c.token === 'pw')?.distanceM).toBe(100)
  })

  it('从记录重算 pushes each matched measured median into the bag', async () => {
    render(<BagPage measuredClubs={measuredClubs} adminToken="admin-secret" onNavigate={vi.fn()} />)
    await screen.findByRole('button', { name: '一号木 距离条' })

    await userEvent.click(screen.getByRole('button', { name: '从记录重算' }))

    await waitFor(() => expect(putPlayerClubBag).toHaveBeenCalled())
    const body = vi.mocked(putPlayerClubBag).mock.calls[0][1]
    expect(body.clubs.find((c) => c.token === 'driver')?.distanceM).toBe(200) // measured median
    expect(body.clubs.find((c) => c.token === 'iron7')?.distanceM).toBe(140)
    expect(body.clubs.find((c) => c.token === 'pw')?.distanceM).toBe(100) // no measured → unchanged
  })

  it('routes 添加球杆 to the club-bag manager', async () => {
    const onNavigate = vi.fn()
    render(<BagPage measuredClubs={measuredClubs} adminToken="admin-secret" onNavigate={onNavigate} />)
    await screen.findByRole('button', { name: '一号木 距离条' })

    await userEvent.click(screen.getByRole('button', { name: '+ 添加球杆' }))
    expect(onNavigate).toHaveBeenCalledWith('club-bag')
  })

  it('signed-in member edits their OWN bag (session id, no admin token)', async () => {
    render(<BagPage measuredClubs={measuredClubs} isOwner={false} selfPlayerId="p_member" onNavigate={vi.fn()} />)
    await screen.findByRole('button', { name: '一号木 距离条' })
    expect(fetchPlayerClubBag).toHaveBeenCalledWith('p_member', undefined)
  })

  it('shows a clean onboarding state when the bag has no clubs', async () => {
    vi.mocked(fetchPlayerClubBag).mockResolvedValue(emptyBag)
    render(<BagPage measuredClubs={[]} adminToken="admin-secret" onNavigate={vi.fn()} />)
    expect(await screen.findByText('你的球包还没有球杆')).toBeInTheDocument()
  })
})
