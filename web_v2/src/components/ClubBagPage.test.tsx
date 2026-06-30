import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ClubBagPage } from './ClubBagPage'
import { fetchAdminPlayers, fetchPlayerClubBag, putPlayerClubBag } from '../api'

vi.mock('../api', () => ({
  fetchAdminPlayers: vi.fn(),
  fetchPlayerClubBag: vi.fn(),
  putPlayerClubBag: vi.fn(),
}))

const owner = { id: 'me', name: '我', isOwner: true, createdAt: '2026-06-01T00:00:00Z', avatar: null, tokenLast4: null }
const friend = {
  id: 'p_a',
  name: '老王',
  isOwner: false,
  createdAt: '2026-06-02T00:00:00Z',
  avatar: null,
  tokenLast4: '77c1',
}

// 七号铁 carries a distance (128m → 140yd in the UI); 一号木 carries none (stays blank).
const bag = {
  schema: 'ai-caddie-effective-club-bag-v1',
  source: 'garmin',
  found: true,
  clubs: [
    { token: 'iron7', zhName: '七号铁', customName: null, clubTypeId: 16, distanceM: 128, distanceSource: null },
    { token: 'driver', zhName: '一号木', customName: null, clubTypeId: 1, distanceM: null, distanceSource: null },
  ],
}

describe('ClubBagPage', () => {
  beforeEach(() => {
    vi.mocked(fetchAdminPlayers).mockResolvedValue({ players: [owner, friend] })
    vi.mocked(fetchPlayerClubBag).mockResolvedValue(bag)
    vi.mocked(putPlayerClubBag).mockResolvedValue(bag)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  // NOTE: queries lean on getByLabelText/getByText rather than getByRole({name}) — the latter
  // recomputes accessible names across all ~30 catalog checkboxes per call, which is slow enough
  // in jsdom to blow the default 5s test timeout on a small box.
  it('lists every player and renders the owner bag (checked clubs + prefilled distance)', async () => {
    render(<ClubBagPage adminToken="admin-secret" />)

    // The owner bag loads on entry (七号铁 checkbox is labelled by its wrapping <label> text).
    const iron7 = await screen.findByLabelText('七号铁')
    expect(fetchAdminPlayers).toHaveBeenCalledWith('admin-secret')
    expect(fetchPlayerClubBag).toHaveBeenCalledWith('me', 'admin-secret')

    // Member picker lists every player — no 本人 vocabulary anymore.
    expect(screen.getByRole('option', { name: '我' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '老王' })).toBeInTheDocument()
    expect(screen.queryByText(/本人/)).not.toBeInTheDocument()

    // Clubs in the bag render checked; catalog clubs not in the bag stay unchecked.
    expect(iron7).toBeChecked()
    expect(screen.getByLabelText('一号木')).toBeChecked()
    expect(screen.getByLabelText('三号木')).not.toBeChecked()

    // 128m prefills as 140yd; a no-distance club stays blank.
    expect(screen.getByLabelText(/七号铁.*距离/)).toHaveValue('140')
    expect(screen.getByLabelText(/一号木.*距离/)).toHaveValue('')
  })

  it('lets a signed-in member edit their OWN bag (session player id, no picker, no admin token)', async () => {
    render(<ClubBagPage isOwner={false} selfPlayerId="p_member" />)
    await screen.findByLabelText('七号铁')

    // The member authorizes with their session bearer (no admin token) and never sees the picker.
    expect(fetchPlayerClubBag).toHaveBeenCalledWith('p_member', undefined)
    expect(fetchAdminPlayers).not.toHaveBeenCalled()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()

    // Drop 一号木 so only 七号铁 remains, then save — to their own id, no admin token.
    await userEvent.click(screen.getByLabelText('一号木'))
    await userEvent.click(screen.getByRole('button', { name: '保存到云端' }))
    expect(putPlayerClubBag).toHaveBeenCalledWith('p_member', { clubs: [{ token: 'iron7', distanceM: 128 }] }, undefined)
  })

  it('saves the manual bag for the selected player (yards → metres, only checked clubs)', async () => {
    render(<ClubBagPage adminToken="admin-secret" />)
    await screen.findByLabelText('七号铁')

    // Drop 一号木 so only 七号铁 remains, then save.
    await userEvent.click(screen.getByLabelText('一号木'))
    await userEvent.click(screen.getByRole('button', { name: '保存到云端' }))

    expect(putPlayerClubBag).toHaveBeenCalledWith('me', { clubs: [{ token: 'iron7', distanceM: 128 }] }, 'admin-secret')
    expect(await screen.findByText(/已保存到云端/)).toBeInTheDocument()
  })

  it('refetches the bag of a member picked from the owner dropdown', async () => {
    render(<ClubBagPage adminToken="admin-secret" />)
    await screen.findByLabelText('七号铁')

    await userEvent.selectOptions(screen.getByRole('combobox'), 'p_a')

    await waitFor(() => expect(fetchPlayerClubBag).toHaveBeenCalledWith('p_a', 'admin-secret'))
  })
})
