import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CurrentPlayerBadge } from './CurrentPlayerBadge'

describe('CurrentPlayerBadge', () => {
  it('shows the current player name with a read-only label and no switcher', () => {
    render(<CurrentPlayerBadge player={{ id: 'p_a1b2', name: '老王', isOwner: false, avatar: null }} />)

    expect(screen.getByText('老王')).toBeInTheDocument()
    expect(screen.getByLabelText('当前球员 老王')).toBeInTheDocument()
    // Read-only: no dropdown / button / combobox to switch player.
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('renders the avatar image when present, falling back to the name initial otherwise', () => {
    const { container, rerender } = render(
      <CurrentPlayerBadge player={{ id: 'p_a1b2', name: '老王', isOwner: false, avatar: null }} />,
    )
    // No avatar → first character placeholder, distinct from the full name.
    expect(screen.getByText('老王')).toBeInTheDocument()
    expect(screen.getByText('老')).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()

    rerender(
      <CurrentPlayerBadge
        player={{ id: 'p_a1b2', name: '老王', isOwner: false, avatar: 'https://example.test/a.png' }}
      />,
    )
    // Decorative avatar (empty alt) → query the element directly, not by role.
    expect(container.querySelector('img')).toHaveAttribute('src', 'https://example.test/a.png')
  })
})
