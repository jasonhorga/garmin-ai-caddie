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
  return (
    <div className="current-player" aria-label={`当前球员 ${name}`}>
      <span className="current-player-avatar" aria-hidden="true">
        {player.avatar ? <img src={player.avatar} alt="" /> : initial}
      </span>
      <span className="current-player-name">{name}</span>
    </div>
  )
}
