import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AppSidebar } from './AppSidebar'

describe('AppSidebar', () => {
  it('renders the five Chinese sections and marks the active one', () => {
    render(<AppSidebar activePage="clubs" onNavigate={() => undefined} />)
    ;['概览', '历史', '备战', '实战', '设置'].forEach((label) =>
      expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    expect(screen.getByRole('button', { name: '历史' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: '概览' })).not.toHaveAttribute('aria-current')
    expect(screen.getByText('AI Caddie')).toBeInTheDocument()
  })

  it('navigates to each section default page', async () => {
    const onNavigate = vi.fn()
    render(<AppSidebar activePage="overview" onNavigate={onNavigate} />)
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    expect(onNavigate).toHaveBeenCalledWith('history')
    await userEvent.click(screen.getByRole('button', { name: '备战' }))
    expect(onNavigate).toHaveBeenCalledWith('prep')
    await userEvent.click(screen.getByRole('button', { name: '实战' }))
    expect(onNavigate).toHaveBeenCalledWith('caddie')
    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    expect(onNavigate).toHaveBeenCalledWith('settings')
  })

  it('navigates back to 概览 from another section', async () => {
    const onNavigate = vi.fn()
    render(<AppSidebar activePage="clubs" onNavigate={onNavigate} />)
    await userEvent.click(screen.getByRole('button', { name: '概览' }))
    expect(onNavigate).toHaveBeenCalledWith('overview')
  })
})
