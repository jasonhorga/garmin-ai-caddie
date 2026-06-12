// W4a big-data truncation: long stats lists cap their visible rows and expand
// on demand. Pure display state — the data itself is never sliced upstream.
interface ShowAllToggleProps {
  total: number
  expanded: boolean
  onToggle: () => void
}

export function ShowAllToggle({ total, expanded, onToggle }: ShowAllToggleProps) {
  return (
    <button type="button" className="w4-expand-toggle" aria-expanded={expanded} onClick={onToggle}>
      {expanded ? '收起' : `展开全部(共 ${total})`}
    </button>
  )
}
