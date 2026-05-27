import { SourceRefs } from './SourceRefs'
import { asNumber, asRows, asString, formatNumber } from './statsValues'

interface CourseDistributionMapProps {
  rows: unknown
  onSelectRef?: (sourceRef: string) => void
  metricMode?: 'split' | 'combined'
  maxRows?: number
}

interface CoursePoint {
  key: string
  name: string
  row: Record<string, unknown>
  latitude: number
  longitude: number
  x: number
  y: number
}

const MAP_WIDTH = 320
const MAP_HEIGHT = 180
const MAP_PADDING = 32

export function CourseDistributionMap({ rows, onSelectRef, metricMode = 'split', maxRows }: CourseDistributionMapProps) {
  const distribution = asRows(rows).slice(0, maxRows)
  const parsed = distribution.map((row) => ({ row, location: parseLocation(row.location) }))
  const plotted = projectPoints(
    parsed.flatMap(({ row, location }) => (location ? [{ row, ...location }] : [])),
  )
  const missingCount = distribution.length - plotted.length

  if (distribution.length === 0) {
    return (
      <article className="stats-empty">
        <h3>No course distribution yet</h3>
        <p>Distribution rows appear after round history has course keys.</p>
      </article>
    )
  }

  return (
    <div className="course-distribution-map">
      {plotted.length > 0 ? (
        <div className="course-map-shell">
          <svg
            className="course-distribution-svg"
            role="img"
            aria-label="Course distribution geography"
            viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
            data-plotted-count={plotted.length}
          >
            <rect className="course-map-frame" x="1" y="1" width={MAP_WIDTH - 2} height={MAP_HEIGHT - 2} rx="8" />
            <path className="course-map-grid" d="M32 40H288M32 90H288M32 140H288M80 24V156M160 24V156M240 24V156" />
            {plotted.map((point, index) => (
              <g key={point.key} className="course-map-pin-node">
                <title>{`${point.name}: ${formatNumber(point.row.pct)}%, ${roundLabel(point.row.roundCount)}, ${formatLocation(point)}`}</title>
                <circle
                  data-testid={`course-map-pin-${testIdToken(point.key)}`}
                  cx={formatSvgNumber(point.x)}
                  cy={formatSvgNumber(point.y)}
                  r={pinRadius(point.row.roundCount)}
                />
                <text x={formatSvgNumber(point.x)} y={formatSvgNumber(point.y + 4)}>
                  {index + 1}
                </text>
              </g>
            ))}
          </svg>
          <div className="course-map-summary" aria-label="Course map coverage">
            <span>{plotted.length} plotted</span>
            <span className={missingCount ? 'semantic-chip quality-missing' : 'semantic-chip quality-good'}>{missingCount} missing location</span>
          </div>
        </div>
      ) : (
        <article className="stats-empty">
          <h3>No mapped locations yet</h3>
          <p>Course rows need latitude and longitude before map pins can render.</p>
        </article>
      )}
      <div className="course-distribution-list">
        {parsed.map(({ row, location }) => {
          const key = asString(row.courseKey) ?? asString(row.courseName) ?? 'course'
          return (
            <div key={key} className="course-distribution-row">
              <span className={location ? 'course-map-pin' : 'course-map-pin missing'} aria-hidden="true" />
              <div>
                <strong>{asString(row.courseName) ?? key}</strong>
                {metricMode === 'combined' ? (
                  <span>
                    {formatNumber(row.pct)}% / {roundLabel(row.roundCount)}
                  </span>
                ) : (
                  <>
                    <span>{formatNumber(row.pct)}%</span>
                    <span>{roundLabel(row.roundCount)}</span>
                  </>
                )}
                {location ? <em>{formatLocation(location)}</em> : <em className="semantic-chip quality-missing">location missing</em>}
              </div>
              <SourceRefs refs={refsFor(row)} maxVisible={4} onSelectRef={onSelectRef} />
            </div>
          )
        })}
      </div>
    </div>
  )
}

function parseLocation(value: unknown): { latitude: number; longitude: number } | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return null
  const row = value as Record<string, unknown>
  const latitude = asNumber(row.latitude) ?? asNumber(row.lat)
  const longitude = asNumber(row.longitude) ?? asNumber(row.lon)
  if (latitude === null || longitude === null) return null
  if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return null
  return { latitude, longitude }
}

function projectPoints(points: Array<{ row: Record<string, unknown>; latitude: number; longitude: number }>): CoursePoint[] {
  if (points.length === 0) return []
  const latitudes = points.map((point) => point.latitude)
  const longitudes = points.map((point) => point.longitude)
  const minLatitude = Math.min(...latitudes)
  const maxLatitude = Math.max(...latitudes)
  const minLongitude = Math.min(...longitudes)
  const maxLongitude = Math.max(...longitudes)
  const latitudeSpan = maxLatitude - minLatitude
  const longitudeSpan = maxLongitude - minLongitude

  return points.map((point) => {
    const longitudeRatio = longitudeSpan === 0 ? 0.5 : (point.longitude - minLongitude) / longitudeSpan
    const latitudeRatio = latitudeSpan === 0 ? 0.5 : (point.latitude - minLatitude) / latitudeSpan
    const x = MAP_PADDING + longitudeRatio * (MAP_WIDTH - MAP_PADDING * 2)
    const y = MAP_HEIGHT - MAP_PADDING - latitudeRatio * (MAP_HEIGHT - MAP_PADDING * 2)
    const key = asString(point.row.courseKey) ?? asString(point.row.courseName) ?? `${point.latitude}:${point.longitude}`
    return {
      key,
      name: asString(point.row.courseName) ?? key,
      row: point.row,
      latitude: point.latitude,
      longitude: point.longitude,
      x,
      y,
    }
  })
}

function pinRadius(value: unknown): number {
  const count = asNumber(value) ?? 1
  return Math.max(7, Math.min(15, 7 + Math.sqrt(count) * 2))
}

function formatSvgNumber(value: number): string {
  const rounded = Math.round(value * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}

function formatLocation(value: { latitude: number; longitude: number }): string {
  return `${value.latitude.toFixed(4)}, ${value.longitude.toFixed(4)}`
}

function roundLabel(value: unknown): string {
  const number = asNumber(value)
  return `${number === null ? '-' : number} rounds`
}

function refsFor(row: Record<string, unknown>) {
  const refs = row.roundRefs ?? row.sourceRefs ?? row.roundIds
  if (refs) return refs
  const singular = row.roundRef ?? row.sourceRef
  return singular ? [singular] : []
}

function testIdToken(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9_-]+/g, '_')
}
