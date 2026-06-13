import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { InvalidLinkPage } from './InvalidLinkPage'

describe('InvalidLinkPage', () => {
  it('renders a clean "needs a valid link" message', () => {
    render(<InvalidLinkPage />)
    expect(screen.getByRole('heading', { name: '需要有效链接' })).toBeInTheDocument()
    expect(screen.getByText('请使用你收到的专属链接打开本页面。')).toBeInTheDocument()
  })

  it('exposes no player identity, owner controls, or navigation', () => {
    render(<InvalidLinkPage />)
    // A locked-out visitor must not see any actionable owner/player affordances.
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    // No copy that reveals whether players exist or hints at owner/admin tooling.
    expect(screen.queryByText(/球员|owner|管理|令牌/i)).not.toBeInTheDocument()
  })
})
