import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { REVIEW_SUBNAV } from '../navigation'
import { SubNav } from './SubNav'

describe('SubNav', () => {
  it('renders tabs and marks the active page, including activeFor aliases', () => {
    render(<SubNav items={REVIEW_SUBNAV} activePage="issues" onNavigate={() => undefined} />)
    ;['总览', '全部球局', '时间趋势', '表现分析', '球场'].forEach((label) =>
      expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    // 表现分析 is active for holes/issues and its result-club child route.
    expect(screen.getByRole('button', { name: '表现分析' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: '全部球局' })).not.toHaveAttribute('aria-current')
  })

  it('fires onNavigate with the tab page id', async () => {
    const onNavigate = vi.fn()
    render(<SubNav items={REVIEW_SUBNAV} activePage="rounds" onNavigate={onNavigate} />)
    await userEvent.click(screen.getByRole('button', { name: '表现分析' }))
    expect(onNavigate).toHaveBeenCalledWith('holes')
  })

  it('applies the inner variant class', () => {
    const { container } = render(<SubNav items={REVIEW_SUBNAV} activePage="rounds" onNavigate={() => undefined} variant="inner" />)
    expect(container.firstChild).toHaveClass('subnav--inner')
  })
})
