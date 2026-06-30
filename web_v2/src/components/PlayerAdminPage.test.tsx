import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PlayerAdminPage } from './PlayerAdminPage'
import { fetchFamilyUsers } from '../api'

vi.mock('../api', () => ({
  fetchFamilyUsers: vi.fn(),
}))

const roster = {
  schema: 'ai-caddie-family-users-v1' as const,
  total: 3,
  users: [
    { id: 'u_me', displayName: '我', role: 'admin', createdAt: '2026-05-01T00:00:00Z', deletedAt: null, playerId: 'me' },
    { id: 'u_wang', displayName: '老王', role: 'member', createdAt: '2026-05-02T00:00:00Z', deletedAt: null, playerId: 'p_a1b2' },
    { id: 'u_gone', displayName: '退群的', role: 'member', createdAt: '2026-05-03T00:00:00Z', deletedAt: '2026-05-09T00:00:00Z', playerId: null },
  ],
}

describe('PlayerAdminPage', () => {
  beforeEach(() => {
    vi.mocked(fetchFamilyUsers).mockResolvedValue(roster)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lists active family members with role + join date from /admin/family/users', async () => {
    render(<PlayerAdminPage adminToken="admin-secret" />)
    expect(await screen.findByText('老王')).toBeInTheDocument()
    expect(fetchFamilyUsers).toHaveBeenCalledWith('admin-secret')
    expect(screen.getByText('我')).toBeInTheDocument()
    expect(screen.getByText('主理人')).toBeInTheDocument()
    expect(screen.getByText('家人')).toBeInTheDocument()
    expect(screen.getByText('2026-05-02 加入')).toBeInTheDocument()
  })

  it('hides soft-deleted members', async () => {
    render(<PlayerAdminPage adminToken="admin-secret" />)
    await screen.findByText('老王')
    expect(screen.queryByText('退群的')).not.toBeInTheDocument()
  })

  it('renders no link-issuance / token / score-analysis surfaces', async () => {
    render(<PlayerAdminPage adminToken="admin-secret" />)
    await screen.findByText('老王')
    // The link-issuance model is gone: no link/token vocabulary, no 本人, no inputs.
    expect(screen.queryByText(/专属链接|链接尾号|新建球员|重发链接|本人/)).not.toBeInTheDocument()
    expect(screen.queryByText(/平均杆|强弱分析|趋势总览|成绩分析|杆数分布/)).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('shows an empty state when no active member remains', async () => {
    vi.mocked(fetchFamilyUsers).mockResolvedValue({
      schema: 'ai-caddie-family-users-v1',
      total: 1,
      users: [
        { id: 'u_gone', displayName: '走了', role: 'member', createdAt: '2026-05-03T00:00:00Z', deletedAt: '2026-05-09T00:00:00Z', playerId: null },
      ],
    })
    render(<PlayerAdminPage adminToken="admin-secret" />)
    expect(await screen.findByText('还没有家人加入')).toBeInTheDocument()
  })

  it('surfaces a load error', async () => {
    vi.mocked(fetchFamilyUsers).mockRejectedValue(new Error('GET /api/v2/admin/family/users failed: 401 Unauthorized'))
    render(<PlayerAdminPage adminToken="bad" />)
    await waitFor(() => expect(screen.getByText(/加载成员失败/)).toBeInTheDocument())
  })
})
