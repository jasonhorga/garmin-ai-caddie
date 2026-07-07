import { useMemo } from 'react'
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

// Courses in the same city project to near-identical lat/long, so their pins
// used to stack into an unreadable blob. Nudge only pins that would collide
// just far enough apart to read, keeping the geographic layout otherwise.
const PIN_MIN_GAP = 1.5 // desired clear gap between pin edges, in SVG units
const RELAX_ITERATIONS = 120 // hard cap so overpacked maps still terminate
const RELAX_EPS = 0.05 // stop once the largest nudge falls below this

export function CourseDistributionMap({ rows, onSelectRef, metricMode = 'split', maxRows }: CourseDistributionMapProps) {
  const { parsed, plotted, distributionLength } = useMemo(() => {
    const distribution = asRows(rows).slice(0, maxRows)
    const parsedRows = distribution.map((row) => ({ row, location: parseLocation(row.location) }))
    const projected = projectPoints(
      parsedRows.flatMap(({ row, location }) => (location ? [{ row, ...location }] : [])),
    )
    return { parsed: parsedRows, plotted: declutterPoints(projected), distributionLength: distribution.length }
  }, [rows, maxRows])
  const missingCount = distributionLength - plotted.length

  if (distributionLength === 0) {
    return (
      <article className="stats-empty">
        <h3>暂无球场分布数据</h3>
        <p>同步球局数据后球场分布将自动填充。</p>
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
            aria-label="球场地理分布"
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
          <div className="course-map-summary" aria-label="地图覆盖情况">
            <span>{plotted.length} 已标注</span>
            <span className={missingCount ? 'semantic-chip quality-missing' : 'semantic-chip quality-good'}>{missingCount} 无位置信息</span>
          </div>
        </div>
      ) : (
        <article className="stats-empty">
          <h3>暂无位置信息</h3>
          <p>球场数据需包含经纬度才能在地图上显示标注。</p>
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
                {location ? <em>{formatLocation(location)}</em> : <em className="semantic-chip quality-missing">无位置信息</em>}
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
  return points.map((point) => {
    const key = asString(point.row.courseKey) ?? asString(point.row.courseName) ?? `${point.latitude}:${point.longitude}`
    return {
      key,
      name: asString(point.row.courseName) ?? key,
      row: point.row,
      latitude: point.latitude,
      longitude: point.longitude,
      x: MAP_PADDING + ((point.longitude + 180) / 360) * (MAP_WIDTH - MAP_PADDING * 2),
      y: MAP_PADDING + ((90 - point.latitude) / 180) * (MAP_HEIGHT - MAP_PADDING * 2),
    }
  })
}

// Beeswarm-style de-overlap: iteratively push apart only pins whose circles
// (radius + gap) would collide, leaving well-separated pins exactly on their
// projected spot. Fully deterministic — same course set in, same layout out —
// with a fixed iteration cap so a dense map still terminates instead of the
// pins flying off. Data is untouched; only where a pin is drawn changes.
function declutterPoints(points: CoursePoint[]): CoursePoint[] {
  if (points.length < 2) return points
  const n = points.length
  const xs = points.map((point) => point.x)
  const ys = points.map((point) => point.y)
  const rs = points.map((point) => pinRadius(point.row.roundCount))
  for (let iter = 0; iter < RELAX_ITERATIONS; iter++) {
    let maxShift = 0
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = xs[j] - xs[i]
        let dy = ys[j] - ys[i]
        let dist = Math.hypot(dx, dy)
        const minDist = rs[i] + rs[j] + PIN_MIN_GAP
        if (dist >= minDist) continue
        if (dist < 1e-4) {
          // Exact coincidence has no direction to push along — fan the pair out
          // on a stable angle derived from their indices so the result is still
          // deterministic rather than dependent on floating-point noise.
          const angle = (((i * 73 + j * 149) % 360) * Math.PI) / 180
          dx = Math.cos(angle)
          dy = Math.sin(angle)
          dist = 1
        }
        const shift = (minDist - dist) / 2
        const ux = dx / dist
        const uy = dy / dist
        xs[i] -= ux * shift
        ys[i] -= uy * shift
        xs[j] += ux * shift
        ys[j] += uy * shift
        if (shift > maxShift) maxShift = shift
      }
    }
    for (let i = 0; i < n; i++) {
      xs[i] = clampToFrame(xs[i], rs[i], MAP_WIDTH)
      ys[i] = clampToFrame(ys[i], rs[i], MAP_HEIGHT)
    }
    if (maxShift < RELAX_EPS) break
  }
  return points.map((point, i) => ({ ...point, x: xs[i], y: ys[i] }))
}

// Keep a nudged pin fully inside the map frame.
function clampToFrame(value: number, radius: number, extent: number): number {
  const margin = radius + 3
  return Math.max(margin, Math.min(extent - margin, value))
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
  return `${number === null ? '-' : number} 场`
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
