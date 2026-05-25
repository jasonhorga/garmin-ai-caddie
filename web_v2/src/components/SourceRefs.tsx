interface SourceRefsProps {
  refs: unknown
  onSelectRef?: (sourceRef: string) => void
}

function normalizeRefs(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item).trim()).filter(Boolean)
}

export function SourceRefs({ refs, onSelectRef }: SourceRefsProps) {
  const normalizedRefs = normalizeRefs(refs)
  if (normalizedRefs.length === 0) return <span className="source-refs-empty">-</span>

  return (
    <span className="source-refs" aria-label="Source refs">
      {normalizedRefs.map((sourceRef) =>
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
    </span>
  )
}
