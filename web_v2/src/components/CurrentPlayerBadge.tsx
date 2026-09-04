import { useState } from 'react'
import type { CurrentPlayer } from '../types'

interface CurrentPlayerBadgeProps {
  player: CurrentPlayer
}

// Read-only "当前是谁" badge in the top bar. The whole app is scoped to one
// player by the URL token (see playerContext), so this deliberately renders NO
// switcher / dropdown and never references any other player — just the name and
// (optional) avatar of whoever this link belongs to.
export function CurrentPlayerBadge({ player }: CurrentPlayerBadgeProps) {
  const name = player.name?.trim() || '未命名球员'
  const initial = name.charAt(0)
  const avatar = player.avatar?.trim() || null
  const [failedAvatar, setFailedAvatar] = useState<string | null>(null)
  const visibleAvatar = avatar && failedAvatar !== avatar ? avatar : null
  // The avatar placeholder is the name's first character. For a single-character
  // name (e.g. the owner's "我") that initial is identical to the full name, so the
  // badge would read "我 我". Render the avatar only when it adds information beyond
  // the name: a real image, or a name longer than one character.
  const showAvatar = Boolean(visibleAvatar) || name.length > 1
  return (
    <div className="current-player" aria-label={`当前球员 ${name}`}>
      {showAvatar ? (
        <span className="current-player-avatar" aria-hidden="true">
          {visibleAvatar ? <img src={visibleAvatar} alt="" onError={() => setFailedAvatar(visibleAvatar)} /> : initial}
        </span>
      ) : null}
      <span className="current-player-name">{name}</span>
    </div>
  )
}
