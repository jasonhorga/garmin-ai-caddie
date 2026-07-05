import { useState } from 'react'

interface HoleBaseImageProps {
  // The realistic server-rendered topo PNG (present only for real courses with CourseView
  // geometry). Undefined → render the fallback directly.
  topoSrc?: string
  // The always-available fallback: the legacy flat-geometry render (a data URI) or the shared
  // '/hole-sample.png' placeholder. Shown when there is no topo, or if the topo 404s / errors.
  fallbackSrc: string
  alt: string
  className?: string
}

// The base <img> layer of a hole canvas. Prefers the realistic topo bitmap, but degrades
// gracefully to the fallback if the course has no topo geometry (topoSrc undefined) OR the
// topo request fails at load time (e.g. a hole whose mesh is present but unrenderable). The
// vector overlays are drawn on top by the parent canvas — this only owns the base image.
export function HoleBaseImage({ topoSrc, fallbackSrc, alt, className }: HoleBaseImageProps): React.ReactElement {
  // Track the exact topo src that failed to load. Deriving `useTopo` from this (rather than a
  // boolean reset in an effect) means switching to a new hole's topoSrc automatically retries —
  // a previous hole's failure never pins later holes to the fallback.
  const [failedSrc, setFailedSrc] = useState<string | null>(null)

  const useTopo = Boolean(topoSrc) && topoSrc !== failedSrc
  const src = useTopo ? (topoSrc as string) : fallbackSrc

  return (
    <img
      className={className}
      src={src}
      alt={alt}
      onError={useTopo ? () => setFailedSrc(topoSrc ?? null) : undefined}
    />
  )
}
