import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { HISTORY_SUBNAV } from '../navigation'
import { SubNav } from './SubNav'

describe('SubNav', () => {
  it('renders tabs and marks the active page, including activeFor aliases', () => {
    render(<SubNav items={HISTORY_SUBNAV} activePage="clubs" onNavigate={() => undefined} />)
    ;['趋势总览', '球局', '强弱分析', '球场', '报告'].forEach((label) =>
      expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    expect(screen.getByRole('button', { name: '强弱分析' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: '球局' })).not.toHaveAttribute('aria-current')
  })

  it('fires onNavigate with the tab page id', async () => {
    const onNavigate = vi.fn()
    render(<SubNav items={HISTORY_SUBNAV} activePage="history" onNavigate={onNavigate} />)
    await userEvent.click(screen.getByRole('button', { name: '报告' }))
    expect(onNavigate).toHaveBeenCalledWith('reports')
  })
})
