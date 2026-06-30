import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders sidebar, section title, history subnav, and children for a history page', async () => {
    const onNavigate = vi.fn()
    render(
      <AppShell activePage="clubs" onNavigate={onNavigate}>
        <p>stats body</p>
      </AppShell>,
    )
    expect(screen.getByRole('button', { name: '历史' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('heading', { name: '历史' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '强弱分析' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('stats body')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '球局' }))
    expect(onNavigate).toHaveBeenCalledWith('rounds')
  })

  it('renders no subnav for sections without one', () => {
    render(
      <AppShell activePage="overview" onNavigate={() => undefined}>
        <p>home body</p>
      </AppShell>,
    )
    expect(screen.getByRole('heading', { name: '概览' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '趋势总览' })).not.toBeInTheDocument()
  })

  it('shows a read-only current-player badge in the top bar only when provided', () => {
    const { rerender } = render(
      <AppShell activePage="overview" onNavigate={() => undefined}>
        <p>home body</p>
      </AppShell>,
    )
    // No current player resolved yet → no badge.
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

  it('renders the consumer settings subnav with no owner/diagnostic tabs', () => {
    render(
      <AppShell activePage="settings" onNavigate={() => undefined}>
        <p>settings body</p>
      </AppShell>,
    )
    // Consumer tabs only: 账号 + 球包管理 + 数据更正(订正).
    expect(screen.getByRole('button', { name: '账号' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '球包管理' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '订正' })).toBeInTheDocument()
    // The owner diagnostics console and the obsolete player-link manager are gone.
    expect(screen.queryByRole('button', { name: '球员管理' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '同步与数据健康' })).not.toBeInTheDocument()
  })
})
