import { render, screen } from '@testing-library/react'
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

  it('hides the 球员管理 settings tab unless owner player admin is visible', () => {
    const { rerender } = render(
      <AppShell activePage="sync-quality" onNavigate={() => undefined}>
        <p>settings body</p>
      </AppShell>,
    )
    // Default (e.g. a per-player link): no owner management affordance.
    expect(screen.queryByRole('button', { name: '球员管理' })).not.toBeInTheDocument()
    // The other settings tabs are unaffected.
    expect(screen.getByRole('button', { name: '同步与数据健康' })).toBeInTheDocument()

    rerender(
      <AppShell activePage="sync-quality" onNavigate={() => undefined} playersAdminVisible>
        <p>settings body</p>
      </AppShell>,
    )
    expect(screen.getByRole('button', { name: '球员管理' })).toBeInTheDocument()
  })
})
