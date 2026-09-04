import { fireEvent, render, screen } from '@testing-library/react'
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

  it('does not duplicate a single-character name as both avatar and label (owner "我")', () => {
    // The avatar placeholder is the name's first character; for a one-character name
    // it equals the full name, so showing both read as "我 我". The redundant
    // initial-avatar is dropped — the name renders exactly once.
    const { container } = render(
      <CurrentPlayerBadge player={{ id: 'me', name: '我', isOwner: true, avatar: null }} />,
    )

    expect(screen.getAllByText('我')).toHaveLength(1)
    expect(container.querySelector('.current-player-avatar')).toBeNull()
    expect(screen.getByLabelText('当前球员 我')).toBeInTheDocument()
  })

  it('falls back to the name initial when a remote avatar cannot load', () => {
    const { container } = render(
      <CurrentPlayerBadge
        player={{ id: 'p_a1b2', name: '测试球员', isOwner: false, avatar: 'https://example.test/missing.png' }}
      />,
    )

    const image = container.querySelector('img')
    expect(image).not.toBeNull()
    fireEvent.error(image!)

    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('测')).toBeInTheDocument()
  })
})
