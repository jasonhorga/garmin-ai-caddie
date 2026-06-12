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
