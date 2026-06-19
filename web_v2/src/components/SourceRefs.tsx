import { useState } from 'react'
import { useDiagnostics } from '../diagnosticsContext'

interface SourceRefsProps {
  refs: unknown
  maxVisible?: number
  onSelectRef?: (sourceRef: string) => void
}

function normalizeRefs(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item).trim()).filter(Boolean)
}

export function SourceRefs({ refs, maxVisible, onSelectRef }: SourceRefsProps) {
  const diagnostics = useDiagnostics()
  const [expanded, setExpanded] = useState(false)
  // Raw internal refs (round/hole/shot ids) are owner diagnostics only — the
  // product never shows them. One gate here cleans every call site across the app.
  if (!diagnostics) return null
  const normalizedRefs = normalizeRefs(refs)
  if (normalizedRefs.length === 0) return <span className="source-refs-empty">-</span>
  const visibleCount = !expanded && maxVisible && maxVisible > 0 ? maxVisible : normalizedRefs.length
  const visibleRefs = normalizedRefs.slice(0, visibleCount)
  const hiddenCount = Math.max(0, normalizedRefs.length - visibleRefs.length)

  return (
    <span className="source-refs" aria-label="Source refs">
      {visibleRefs.map((sourceRef) =>
        onSelectRef ? (
          <button key={sourceRef} type="button" className="source-ref-button" onClick={() => onSelectRef(sourceRef)} aria-label={`Open source ${sourceRef}`}>
            {sourceRef}
          </button>
        ) : (
          <span key={sourceRef} className="source-ref-token">
            {sourceRef}
          </span>
        ),
      )}
      {hiddenCount > 0 ? (
        <button
          type="button"
          className="source-ref-button source-ref-more"
          onClick={() => setExpanded(true)}
          aria-label={`展开其余 ${hiddenCount} 处来源`}
        >
          等 {hiddenCount} 处
        </button>
      ) : null}
    </span>
  )
}
