import type { GeoJsonFeature, GeometryEvidenceResponse, HoleMapResponse } from '../types'
import { asString, semanticClass } from './statsValues'

export type HoleEvidenceState =
  | { status: 'idle' }
  | { status: 'loading'; sourceRef: string }
  | { status: 'error'; sourceRef: string; message: string }
  | { status: 'ready'; sourceRef: string; evidence: GeometryEvidenceResponse; map: HoleMapResponse }

export type GeometryEnsureState = 'idle' | 'running' | 'ready' | 'error'

interface HoleEvidencePanelProps {
  state: HoleEvidenceState
  ensureState?: GeometryEnsureState
  onEnsureGeometry?: (target: { globalId: number; localHole: number; sourceRef: string }) => void
}

export function HoleEvidencePanel({ state, ensureState = 'idle', onEnsureGeometry }: HoleEvidencePanelProps) {
  if (state.status === 'idle') {
    return (
      <section className="hole-evidence-panel" aria-label="Hole geometry evidence">
        <h2>Hole Evidence</h2>
        <p>Select a hole or shot source to load geometry evidence.</p>
      </section>
    )
  }

  if (state.status === 'loading') {
    return (
      <section className="hole-evidence-panel" aria-label="Hole geometry evidence">
        <h2>Hole Evidence</h2>
        <p>Loading geometry evidence for {state.sourceRef}</p>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="hole-evidence-panel" aria-label="Hole geometry evidence">
        <h2>Hole Evidence</h2>
        <p>{state.message}</p>
      </section>
    )
  }

  const providerLabel = asString(state.map.provider.label) ?? asString(state.map.provider.name) ?? 'Map provider'
  const coordinateSystem = asString(state.map.provider.coordinateSystem) ?? 'unknown'
  const features = state.map.featureCollection.features
  const shotRoutes = asRecordArray(state.evidence.shotRoutes)
  const surfaceClassifications = asRecordArray(state.evidence.surfaceClassifications)
  const routeEvidence = asRecord(state.evidence.routeEvidence)
  const canEnsureGeometry = Boolean(onEnsureGeometry) && state.evidence.coverage !== 'ready'
  const ensureLabel = `${ensureState === 'running' ? 'Fetching' : 'Fetch'} geometry for ${state.evidence.globalId} H${state.evidence.localHole}`

  return (
    <section className="hole-evidence-panel" aria-label="Hole geometry evidence">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">Geometry Evidence</p>
          <h2>Hole Evidence</h2>
          <p>
            {state.evidence.globalId} H{state.evidence.localHole}
          </p>
        </div>
        <span className={`semantic-chip ${geometryCoverageClass(state.evidence.coverage)}`}>
          {state.evidence.coverage} coverage
        </span>
        {canEnsureGeometry ? (
          <button
            type="button"
            className="hole-evidence-action"
            disabled={ensureState === 'running'}
            onClick={() => onEnsureGeometry?.({ globalId: state.evidence.globalId, localHole: state.evidence.localHole, sourceRef: state.sourceRef })}
            aria-label={ensureLabel}
          >
            {ensureState === 'running' ? 'Fetching Geometry' : 'Fetch Geometry'}
          </button>
        ) : null}
      </div>

      <div className="hole-evidence-layout">
        <GeometryMiniMap features={features} />
        <div className="hole-evidence-facts">
          <div className="hole-evidence-provider">
            <strong>{providerLabel}</strong>
            <span>{coordinateSystem}</span>
          </div>
          <div className="hole-evidence-layers" aria-label="Geometry layers">
            {state.map.layers.map((layer) => (
              <span key={layer}>{layer}</span>
            ))}
            <span>{features.length} features</span>
          </div>
          <FeatureList features={features} />
          <ShotRoutes rows={shotRoutes} />
          <SurfaceClassifications rows={surfaceClassifications} />
          <RouteEvidence route={routeEvidence} />
          <EvidenceRows title="Evidence Files" rows={state.evidence.evidence} />
          <EvidenceRows title="Missing Data" rows={[...state.evidence.missingData, ...state.map.missingData]} />
        </div>
      </div>
    </section>
  )
}

function RouteEvidence({ route }: { route: Record<string, unknown> | null }) {
  if (!route) return null
  const clearances = asRecordArray(route.hazardClearances)
  const landingRisks = asRecordArray(route.landingWindowRisks)
  const avoidZones = asRecordArray(route.avoidZones)
  const landingWindow = asRecord(route.landingWindowLocal)
  return (
    <section aria-label="Route Evidence" className="hole-evidence-rows">
      <h3>Route Evidence</h3>
      <div className="report-row">
        <strong>route</strong>
        <span>{routeLengthLabel(route.routeLength_m)}</span>
      </div>
      {landingWindow ? (
        <div className="report-row">
          <strong>landing</strong>
          <span>{landingWindowLabel(landingWindow)}</span>
        </div>
      ) : null}
      {clearances.slice(0, 5).map((row, index) => (
        <div className="report-row" key={`clearance-${asString(row.hazardId) ?? asString(row.id) ?? index}`}>
          <strong>{asString(row.hazardId) ?? asString(row.id) ?? `hazard-${index + 1}`}</strong>
          <span>{riskClearanceLabel(row)}</span>
        </div>
      ))}
      {landingRisks.length ? <h4>Landing Risks</h4> : null}
      {landingRisks.slice(0, 5).map((row, index) => {
        const id = asString(row.hazardId) ?? asString(row.id) ?? `landing-risk-${index + 1}`
        return (
          <div className="report-row" key={`landing-risk-${id}-${index}`}>
            <strong>{id} landing</strong>
            <span>{landingRiskLabel(row)}</span>
          </div>
        )
      })}
      {avoidZones.slice(0, 5).map((row, index) => (
        <div className="report-row" key={`avoid-${asString(row.id) ?? index}`}>
          <strong>{asString(row.id) ?? `avoid-${index + 1}`}</strong>
          <span>{riskClearanceLabel(row)}</span>
        </div>
      ))}
    </section>
  )
}

function ShotRoutes({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return null
  return (
    <section aria-label="Shot routes" className="hole-evidence-rows">
      <h3>Shot Routes</h3>
      {rows.slice(0, 8).map((row, index) => {
        const ref = asString(row.shotRef) ?? asString(row.ref) ?? `shot-${index + 1}`
        return (
          <div className="report-row" key={`${ref}-${index}`}>
            <strong>{ref}</strong>
            <span>{shotRouteLabel(row)}</span>
          </div>
        )
      })}
    </section>
  )
}

function SurfaceClassifications({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return null
  return (
    <section aria-label="Surface classifications" className="hole-evidence-rows">
      <h3>Surface Classifications</h3>
      {rows.slice(0, 8).map((row, index) => {
        const ref = asString(row.shotRef) ?? `shot-${index + 1}`
        const surface = asRecord(row.surface)
        const kind = asString(surface?.kind) ?? 'unknown'
        const source = asString(surface?.source) ?? 'none'
        return (
          <div className="report-row" key={`${ref}-${index}`}>
            <strong>{ref}</strong>
            <span>{kind} / {source}</span>
          </div>
        )
      })}
    </section>
  )
}

function FeatureList({ features }: { features: GeoJsonFeature[] }) {
  if (!features.length) return <p>No map features available.</p>
  return (
    <section aria-label="Map feature list" className="hole-evidence-feature-list">
      <h3>Map Features</h3>
      {features.slice(0, 8).map((feature, index) => {
        const id = asString(feature.properties.id) ?? `feature-${index + 1}`
        const layer = asString(feature.properties.layer) ?? 'unknown'
        const kind = asString(feature.properties.kind)
        return (
          <div className="report-row" key={`${layer}-${id}-${index}`}>
            <strong>{id}</strong>
            <span>{kind ? `${layer} / ${kind}` : layer}</span>
          </div>
        )
      })}
    </section>
  )
}

function routeLengthLabel(value: unknown): string {
  return `route length ${formatMeters(value)}`
}

function landingWindowLabel(row: Record<string, unknown>): string {
  const center = Array.isArray(row.center) ? row.center.map((value) => Number(value)).filter(Number.isFinite) : []
  const centerLabel = center.length >= 2 ? `[${center[0]}, ${center[1]}]` : 'unknown'
  return `landing window ${centerLabel} r=${formatMeters(row.radius_m)}`
}

function riskClearanceLabel(row: Record<string, unknown>): string {
  const kind = asString(row.kind) ?? 'risk'
  if (Number.isFinite(Number(row.distanceToCenter_m))) {
    return `${kind} landing ${formatMeters(row.distanceToCenter_m)} from center`
  }
  return `${kind} clear ${formatMeters(row.carryToClear_m)}`
}

function landingRiskLabel(row: Record<string, unknown>): string {
  const kind = asString(row.kind) ?? 'risk'
  const parts = [`${kind} landing ${formatMeters(row.distanceToCenter_m)} from center`]
  if (Number.isFinite(Number(row.overlap_m))) {
    parts.push(`overlap ${formatMeters(row.overlap_m)}`)
  }
  if (Number.isFinite(Number(row.landingRadius_m))) {
    parts.push(`r=${formatMeters(row.landingRadius_m)}`)
  }
  return parts.join(', ')
}

function formatMeters(value: unknown): string {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? `${numeric}m` : 'unknown'
}

function shotRouteLabel(row: Record<string, unknown>): string {
  const club = asString(row.club) ?? 'club unknown'
  const distance = typeof row.distance === 'number' ? `${row.distance}m` : asString(row.distance) ?? ''
  const surface = asString(row.surface) ?? ''
  return [club, distance, surface].filter(Boolean).join(' ')
}

function asRecordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object') : []
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null
}

function EvidenceRows({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  return (
    <section aria-label={title} className="hole-evidence-rows">
      <h3>{title}</h3>
      {rows.length ? (
        rows.map((row, index) => (
          <div className="report-row" key={`${title}-${index}`}>
            <strong>{String(row.label ?? row.kind ?? row.id ?? 'item')}</strong>
            <span>{String(row.ref ?? row.reason ?? row.value ?? '')}</span>
          </div>
        ))
      ) : (
        <p>None</p>
      )}
    </section>
  )
}

function GeometryMiniMap({ features }: { features: GeoJsonFeature[] }) {
  const points = collectPoints(features)
  const bounds = boundsFor(points)
  return (
    <svg className="hole-geometry-map" aria-label="Hole geometry map" viewBox="0 0 320 210" role="img">
      <rect x="0" y="0" width="320" height="210" rx="8" />
      {features.map((feature, index) => renderFeature(feature, index, bounds))}
    </svg>
  )
}

type Point = [number, number]

interface Bounds {
  minX: number
  maxX: number
  minY: number
  maxY: number
}

function renderFeature(feature: GeoJsonFeature, index: number, bounds: Bounds) {
  const layer = asString(feature.properties.layer) ?? 'unknown'
  const kind = asString(feature.properties.kind)
  const className = ['hole-map-feature', `feature-${layer}`, kind ? `feature-${layer}-${kind}` : ''].filter(Boolean).join(' ')
  if (feature.geometry.type === 'Point') {
    const point = parsePoint(feature.geometry.coordinates)
    if (!point) return null
    const [x, y] = project(point, bounds)
    return <circle className={className} cx={x} cy={y} r={layer === 'target' ? 5 : 4} key={`point-${index}`} />
  }
  if (feature.geometry.type === 'LineString') {
    const points = parsePointList(feature.geometry.coordinates)
    if (!points.length) return null
    return <polyline className={className} points={points.map((point) => project(point, bounds).join(',')).join(' ')} key={`line-${index}`} />
  }
  if (feature.geometry.type === 'Polygon') {
    const ring = parsePolygonRing(feature.geometry.coordinates)
    if (!ring.length) return null
    return <polygon className={className} points={ring.map((point) => project(point, bounds).join(',')).join(' ')} key={`polygon-${index}`} />
  }
  return null
}

function collectPoints(features: GeoJsonFeature[]): Point[] {
  return features.flatMap((feature) => {
    if (feature.geometry.type === 'Point') {
      const point = parsePoint(feature.geometry.coordinates)
      return point ? [point] : []
    }
    if (feature.geometry.type === 'LineString') return parsePointList(feature.geometry.coordinates)
    if (feature.geometry.type === 'Polygon') return parsePolygonRing(feature.geometry.coordinates)
    return []
  })
}

function parsePoint(value: unknown): Point | null {
  if (!Array.isArray(value) || value.length < 2) return null
  const lon = Number(value[0])
  const lat = Number(value[1])
  return Number.isFinite(lon) && Number.isFinite(lat) ? [lon, lat] : null
}

function parsePointList(value: unknown): Point[] {
  return Array.isArray(value) ? value.map(parsePoint).filter((point): point is Point => point !== null) : []
}

function parsePolygonRing(value: unknown): Point[] {
  if (!Array.isArray(value) || !Array.isArray(value[0])) return []
  return parsePointList(value[0])
}

function boundsFor(points: Point[]): Bounds {
  if (!points.length) return { minX: 0, maxX: 1, minY: 0, maxY: 1 }
  const xs = points.map((point) => point[0])
  const ys = points.map((point) => point[1])
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  return {
    minX,
    maxX: maxX === minX ? minX + 1 : maxX,
    minY,
    maxY: maxY === minY ? minY + 1 : maxY,
  }
}

function project(point: Point, bounds: Bounds): [number, number] {
  const padding = 18
  const width = 320 - padding * 2
  const height = 210 - padding * 2
  const x = padding + ((point[0] - bounds.minX) / (bounds.maxX - bounds.minX)) * width
  const y = padding + (1 - (point[1] - bounds.minY) / (bounds.maxY - bounds.minY)) * height
  return [Number(x.toFixed(1)), Number(y.toFixed(1))]
}

function geometryCoverageClass(value: string): string {
  if (value === 'ready') return 'quality-good'
  return semanticClass('quality', value)
}
