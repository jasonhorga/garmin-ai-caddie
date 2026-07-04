import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AppSidebar } from './AppSidebar'

describe('AppSidebar', () => {
  it('renders the five redesign sections and marks the active one', () => {
    render(<AppSidebar activePage="clubs" onNavigate={() => undefined} />)
    ;['复盘', '备战', '统计', '球包', '设置'].forEach((label) =>
      expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    // 球包 (clubs) is the active section.
    expect(screen.getByRole('button', { name: '球包' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: '复盘' })).not.toHaveAttribute('aria-current')
    // The old 实战 section is gone from the rail.
    expect(screen.queryByRole('button', { name: '实战' })).not.toBeInTheDocument()
    expect(screen.getByText('AI Caddie')).toBeInTheDocument()
  })

  it('navigates to each section default page', async () => {
    const onNavigate = vi.fn()
    render(<AppSidebar activePage="overview" onNavigate={onNavigate} />)
    await userEvent.click(screen.getByRole('button', { name: '复盘' }))
    expect(onNavigate).toHaveBeenCalledWith('overview')
    await userEvent.click(screen.getByRole('button', { name: '备战' }))
    expect(onNavigate).toHaveBeenCalledWith('prep')
    await userEvent.click(screen.getByRole('button', { name: '统计' }))
    expect(onNavigate).toHaveBeenCalledWith('history')
    await userEvent.click(screen.getByRole('button', { name: '球包' }))
    expect(onNavigate).toHaveBeenCalledWith('clubs')
    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    expect(onNavigate).toHaveBeenCalledWith('sync-quality')
  })

  it('keeps the caddie sandbox + phone scorer as off-rail utilities', async () => {
    const onNavigate = vi.fn()
    render(<AppSidebar activePage="caddie" onNavigate={onNavigate} />)
    // On an off-rail page no primary section is highlighted…
    expect(screen.getByRole('button', { name: '备战' })).not.toHaveAttribute('aria-current')
    // …but its own utility entry is.
    expect(screen.getByRole('button', { name: '球童沙盘' })).toHaveAttribute('aria-current', 'page')
    await userEvent.click(screen.getByRole('button', { name: '手机记分' }))
    expect(onNavigate).toHaveBeenCalledWith('record')
  })

  it('shows the rail identity chip only when a current player is provided', () => {
    const { rerender } = render(<AppSidebar activePage="overview" onNavigate={() => undefined} />)
    expect(screen.queryByLabelText(/^当前球员/)).not.toBeInTheDocument()
    rerender(
      <AppSidebar
        activePage="overview"
        onNavigate={() => undefined}
        currentPlayer={{ id: 'p_a1b2', name: '老王', isOwner: false, avatar: null }}
      />,
    )
    expect(screen.getByLabelText('当前球员 老王')).toBeInTheDocument()
  })
})
