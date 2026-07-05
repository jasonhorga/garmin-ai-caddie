import { useState } from 'react'

interface HoleBaseImageProps {
  // The realistic server-rendered topo PNG (present only for real courses with CourseView
  // geometry). Undefined → only the fallback layer renders.
  topoSrc?: string
  // The always-available fallback: the legacy flat-geometry render (a data URI) or the shared
  // '/hole-sample.png' placeholder. Rendered as the base layer so a hole ALWAYS shows something
  // instantly; the topo cross-fades in on top once it loads (and if it 404s / errors, the flat
  // layer simply stays). Because the topo shares the flat render's overlay frame, they align.
  fallbackSrc: string
  alt: string
  className?: string
}

// The base image layer of a hole canvas. The flat/placeholder render is ALWAYS painted underneath
// so switching holes shows the flat map with zero delay; the realistic topo bitmap fades in on top
// the moment it decodes, sharpening the picture without a blank/spinner gap. A topo that never
// loads (undefined src, or a mesh that 404s at load time) leaves the flat layer showing. The vector
// overlays are drawn on top by the parent canvas — this owns only the base image.
export function HoleBaseImage({ topoSrc, fallbackSrc, alt, className }: HoleBaseImageProps): React.ReactElement {
  // The exact topo src that failed to load, and the exact topo src that finished loading. Deriving
  // useTopo/topoReady from the CURRENT topoSrc (rather than an effect reset) means switching to a
  // new hole's topoSrc automatically retries and re-fades: a prior hole's failure never pins a later
  // hole to the fallback, and a prior hole's "ready" never suppresses the new hole's fade-in.
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null)

  const useTopo = Boolean(topoSrc) && topoSrc !== failedSrc
  const topoReady = useTopo && topoSrc === loadedSrc

  return (
    <div className={className ? `hole-base ${className}` : 'hole-base'}>
      <img className="hole-base-flat" src={fallbackSrc} alt={alt} />
      {useTopo ? (
        <img
          className={topoReady ? 'hole-base-topo is-ready' : 'hole-base-topo'}
          src={topoSrc as string}
          alt=""
          aria-hidden="true"
          onLoad={() => setLoadedSrc(topoSrc ?? null)}
          onError={() => setFailedSrc(topoSrc ?? null)}
        />
      ) : null}
    </div>
  )
}
