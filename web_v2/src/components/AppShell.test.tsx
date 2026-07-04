import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders sidebar, section title, review subnav, and children for a review page', async () => {
    const onNavigate = vi.fn()
    render(
      <AppShell activePage="holes" onNavigate={onNavigate}>
        <p>review body</p>
      </AppShell>,
    )
    expect(screen.getByRole('button', { name: '复盘' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('heading', { name: '复盘' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '强弱分析' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('review body')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '球局' }))
    expect(onNavigate).toHaveBeenCalledWith('rounds')
  })

  it('renders no subnav for sections without one', () => {
    render(
      <AppShell activePage="prep" onNavigate={() => undefined}>
        <p>prep body</p>
      </AppShell>,
    )
    expect(screen.getByRole('heading', { name: '备战' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '趋势总览' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '球局' })).not.toBeInTheDocument()
  })

  it('shows a read-only current-player chip in the rail only when provided', () => {
    const { rerender } = render(
      <AppShell activePage="overview" onNavigate={() => undefined}>
        <p>home body</p>
      </AppShell>,
    )
    // No current player resolved yet → no chip.
    expect(screen.queryByLabelText(/^当前球员/)).not.toBeInTheDocument()

    rerender(
      <AppShell
        activePage="overview"
        onNavigate={() => undefined}
        currentPlayer={{ id: 'p_a1b2', name: '老王', isOwner: false, avatar: null }}
      >
        <p>home body</p>
      </AppShell>,
    )
    const badge = screen.getByLabelText('当前球员 老王')
    expect(badge).toBeInTheDocument()
    expect(within(badge).getByText('老王')).toBeInTheDocument()
  })

  it('access-gates the settings subnav: locked → owner-only → member', () => {
    const { rerender } = render(
      <AppShell activePage="sync-quality" onNavigate={() => undefined}>
        <p>settings body</p>
      </AppShell>,
    )
    // Default (locked / fresh or per-player-link visitor): no owner tabs, no member tabs.
    expect(screen.queryByRole('button', { name: '球员管理' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '后端配置' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '账户' })).not.toBeInTheDocument()
    // The always-on connector + 订正 tabs are unaffected.
    expect(screen.getByRole('button', { name: '连接 Garmin' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '订正' })).toBeInTheDocument()

    // A signed-in member sees the consumer tabs (连接 Garmin / 球包管理 / 账户 / 订正), no owner tabs.
    rerender(
      <AppShell activePage="sync-quality" onNavigate={() => undefined} settingsAccess={{ isOwner: false, hasSession: true }}>
        <p>settings body</p>
      </AppShell>,
    )
    expect(screen.getByRole('button', { name: '球包管理' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '账户' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '球员管理' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '后端配置' })).not.toBeInTheDocument()

    // The owner sees everything, including 球员管理 + 后端配置.
    rerender(
      <AppShell activePage="sync-quality" onNavigate={() => undefined} settingsAccess={{ isOwner: true, hasSession: false }}>
        <p>settings body</p>
      </AppShell>,
    )
    expect(screen.getByRole('button', { name: '球员管理' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '后端配置' })).toBeInTheDocument()
  })
})
