import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PlayerAdminPage } from './PlayerAdminPage'
import {
  fetchAdminPlayers,
  createAdminPlayer,
  rotateAdminPlayerToken,
  deleteAdminPlayer,
} from '../api'

vi.mock('../api', () => ({
  fetchAdminPlayers: vi.fn(),
  createAdminPlayer: vi.fn(),
  rotateAdminPlayerToken: vi.fn(),
  deleteAdminPlayer: vi.fn(),
}))

const owner = { id: 'me', name: '我', isOwner: true, createdAt: '2026-06-01T00:00:00Z', avatar: null, tokenLast4: null }
const friend = {
  id: 'p_a1b2',
  name: '老王',
  isOwner: false,
  createdAt: '2026-06-02T00:00:00Z',
  avatar: null,
  tokenLast4: '77c1',
  roundCount: 3,
  sources: { garmin: 2, manual: 1 },
}

function clipboardMock() {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  return writeText
}

describe('PlayerAdminPage', () => {
  beforeEach(() => {
    vi.mocked(fetchAdminPlayers).mockResolvedValue({ players: [owner, friend] })
    vi.mocked(createAdminPlayer).mockResolvedValue({ id: 'p_new', name: '小李', token: 'tok-new', url: 'http://host/p/tok-new' })
    vi.mocked(rotateAdminPlayerToken).mockResolvedValue({ id: 'p_a1b2', token: 'tok-rot', url: 'http://host/p/tok-rot' })
    vi.mocked(deleteAdminPlayer).mockResolvedValue({ ok: true, id: 'p_a1b2' })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('gates behind an admin token and sends no request without one', () => {
    render(<PlayerAdminPage adminToken={undefined} />)
    expect(screen.getByRole('heading', { name: '球员管理' })).toBeInTheDocument()
    expect(screen.getByText(/管理令牌/)).toBeInTheDocument()
    expect(fetchAdminPlayers).not.toHaveBeenCalled()
  })

  it('lists players with name, token last4, and round/source aggregate', async () => {
    render(<PlayerAdminPage adminToken="admin-secret" />)
    expect(await screen.findByText('老王')).toBeInTheDocument()
    expect(fetchAdminPlayers).toHaveBeenCalledWith('admin-secret')
    expect(screen.getByText(/77c1/)).toBeInTheDocument()
    expect(screen.getByText(/3 局/)).toBeInTheDocument()
    expect(screen.getByText(/Garmin/)).toBeInTheDocument()
    expect(screen.getByText(/手动/)).toBeInTheDocument()
  })

  it('renders no score analysis surfaces', async () => {
    render(<PlayerAdminPage adminToken="admin-secret" />)
    await screen.findByText('老王')
    expect(screen.queryByText(/平均杆|强弱分析|趋势总览|成绩分析|杆数分布/)).not.toBeInTheDocument()
  })

  it('creates a player then reveals the one-time link with a copy button', async () => {
    const writeText = clipboardMock()
    render(<PlayerAdminPage adminToken="admin-secret" />)
    await screen.findByText('老王')

    await userEvent.type(screen.getByLabelText('球员名字'), '小李')
    await userEvent.click(screen.getByRole('button', { name: '新建球员' }))

    expect(createAdminPlayer).toHaveBeenCalledWith({ name: '小李' }, 'admin-secret')
    const banner = await screen.findByLabelText('一次性专属链接')
    expect(within(banner).getByText('http://host/p/tok-new')).toBeInTheDocument()

    await userEvent.click(within(banner).getByRole('button', { name: '复制链接' }))
    expect(writeText).toHaveBeenCalledWith('http://host/p/tok-new')
    expect(await within(banner).findByText('已复制')).toBeInTheDocument()
  })

  it('rotates a token and shows the fresh link', async () => {
    render(<PlayerAdminPage adminToken="admin-secret" />)
    await screen.findByText('老王')

    await userEvent.click(screen.getByRole('button', { name: '重发 老王 的专属链接' }))

    expect(rotateAdminPlayerToken).toHaveBeenCalledWith('p_a1b2', 'admin-secret')
    const banner = await screen.findByLabelText('一次性专属链接')
    expect(within(banner).getByText('http://host/p/tok-rot')).toBeInTheDocument()
  })

  it('disables delete for the owner and confirms before deleting others', async () => {
    render(<PlayerAdminPage adminToken="admin-secret" />)
    await screen.findByText('老王')

    expect(screen.getByRole('button', { name: '删除球员 我' })).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: '删除球员 老王' }))
    expect(deleteAdminPlayer).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: '确认删除球员 老王' }))
    expect(deleteAdminPlayer).toHaveBeenCalledWith('p_a1b2', 'admin-secret')
  })

  it('shows a placeholder when a player has no round aggregate', async () => {
    vi.mocked(fetchAdminPlayers).mockResolvedValue({ players: [owner] })
    render(<PlayerAdminPage adminToken="admin-secret" />)
    await screen.findByText('我')
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
  })

  it('surfaces a load error', async () => {
    vi.mocked(fetchAdminPlayers).mockRejectedValue(new Error('GET /api/v2/admin/players failed: 401 Unauthorized'))
    render(<PlayerAdminPage adminToken="bad" />)
    await waitFor(() => expect(screen.getByText(/加载球员失败/)).toBeInTheDocument())
  })
})
