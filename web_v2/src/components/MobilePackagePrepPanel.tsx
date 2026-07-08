import { useEffect, useState, type FormEvent } from 'react'
import { fmtYd } from '../units'
import { confidenceZh, coverageZh, dataModeZh, stateZh } from '../zhLabels'
import type {
  CourseTee,
  CourseTeesResponse,
  MobileCourseOptionsResponse,
  LiveRoundPackageResponse,
  MobileCoursePackageParams,
  MobileRoundPackageParams,
} from '../types'

// 发球台颜色 key → 中文标签(镜像 iOS zhTeeLabel);接口返回的 name 作兜底(CourseView 自带名)。
const TEE_BOX_ZH: Record<string, string> = {
  blue: '蓝 T',
  white: '白 T',
  red: '红 T',
  gold: '金 T',
  black: '黑 T',
  green: '绿 T',
  yellow: '黄 T',
  silver: '银 T',
}

// 选台下拉标签:中文台名 + 已知则附总码数(缺码数不显示,不造假)。
function teeOptionLabel(tee: CourseTee): string {
  const base = TEE_BOX_ZH[tee.teeBox.toLowerCase()] ?? tee.name
  return tee.yards != null ? `${base} · ${tee.yards} 码` : base
}

type PackagePrepMode = 'round' | 'course'

export type MobilePackagePrepState =
  | { status: 'idle' }
  | { status: 'loading'; mode: PackagePrepMode; target: string }
  | { status: 'ready'; data: LiveRoundPackageResponse }
  | { status: 'error'; mode: PackagePrepMode; target: string; message: string }

export type MobileCourseOptionsState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: MobileCourseOptionsResponse }
  | { status: 'error'; message: string }

interface MobilePackagePrepPanelProps {
  state: MobilePackagePrepState
  courseOptionsState?: MobileCourseOptionsState
  onPrepareRound: (roundId: string, params: MobileRoundPackageParams) => void | Promise<void>
  onPrepareCourse: (globalId: number, params: MobileCoursePackageParams) => void | Promise<void>
  /// 拉取所选球场的可选发球台(颜色 + 总码数 + 默认);未提供时发球台退化为手输文本框。
  onLoadCourseTees?: (globalId: number) => Promise<CourseTeesResponse>
  defaultRoundId?: string
  defaultCourseGlobalId?: string
  showAdminTokenInput?: boolean
  adminTokenValue?: string
  onAdminTokenChange?: (value: string) => void
}

function trimmedOrUndefined(value: string) {
  const trimmed = value.trim()
  return trimmed.length ? trimmed : undefined
}

function compactValue(value: unknown) {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return null
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function asRecordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.map(asRecord).filter((row) => Object.keys(row).length) : []
}

// Closed machine-token vocabulary shared by the readiness-check labels
// (mobile_live._package_readiness_checks) and the missing-data labels
// (mobile_live missingData emission sites + weather_context.weather_values).
// Unknown tokens fall through raw.
const PACKAGE_TOKEN_ZH: Record<string, string> = {
  source: '数据源',
  geometry: '几何',
  weather: '天气',
  club_profiles: '球杆样本',
  recent_history: '近期历史',
  caddie_seeds: '球童预置',
  club_profile_sample: '球杆样本',
  current_location: '当前位置',
  weather_values: '天气数据',
  course_prep: '球场备战包',
  route_geometry: '路线几何',
  lie: '球位',
  manual_notes: '手动备注',
  round_reference: '球局引用',
}

function packageTokenZh(raw: string): string {
  return PACKAGE_TOKEN_ZH[raw] ?? raw
}

// Offline option labels (mobile_live option_specs Safe/Stock/Attack and the
// caddie seed options safe layup/stock line/attack line).
const OPTION_LABEL_ZH: Record<string, string> = {
  Safe: '保守',
  Stock: '标准',
  Attack: '强攻',
  'safe layup': '保守起步',
  'stock line': '标准线',
  'attack line': '强攻线',
}

function optionLabelZh(raw: string): string {
  return OPTION_LABEL_ZH[raw] ?? raw
}

function missingLabel(row: Record<string, unknown>) {
  return packageTokenZh(compactValue(row.label) ?? compactValue(row.key) ?? 'missing')
}

function missingReason(row: Record<string, unknown>) {
  return compactValue(row.reason) ?? compactValue(row.detail) ?? ''
}

function recentScoreCount(data: LiveRoundPackageResponse) {
  const recentScores = (data.recentHistory.course as Record<string, unknown> | undefined)?.recentScores
  return Array.isArray(recentScores) ? recentScores.length : 0
}

function packageCoverageFacts(data: LiveRoundPackageResponse) {
  const coverage = data.sourceCoverage
  const facts = [
    `来源 ${stateZh(coverage.state)}`,
    `${dataModeZh(coverage.dataMode)}数据`,
    `${coverage.availableRoundCount} 场可用球局`,
    `${coverage.holeCount} 洞`,
    `${coverage.clubProfileCount} 支球杆`,
    `${recentScoreCount(data)} 条近期成绩`,
  ]
  if (coverage.preparationMode === 'course' && coverage.requestedCourseGlobalId) {
    facts.push(`球场 ${coverage.requestedCourseGlobalId}`)
  }
  if (typeof coverage.courseFound === 'boolean') {
    facts.push(coverage.courseFound ? '球场已找到' : '球场缺失')
  }
  if (coverage.geometryEnsure) {
    facts.push(`几何拉取 ${coverageZh(coverage.geometryEnsure.state)}`)
    facts.push(`已拉取 ${coverage.geometryEnsure.ready}/${coverage.geometryEnsure.attempted}`)
  }
  facts.push(coverage.roundFound ? '球局已找到' : '球局缺失')
  facts.push(coverage.selectedRoundId ? `模板球局 ${coverage.selectedRoundId}` : '无模板球局')
  facts.push(`有效期至 ${data.offlinePackageStatus.expiresAt}`)
  return facts
}

function weatherCoverageText(data: LiveRoundPackageResponse) {
  const coverage = data.weatherSnapshot.coverage
  if (!coverage) return data.weatherSnapshot.source
  return `${coverage.ready}/${coverage.total} 洞`
}

function readinessTitle(label: string) {
  const zh = PACKAGE_TOKEN_ZH[label]
  return zh ?? label.replace(/_/g, ' ')
}

function optionCoverageText(option: Record<string, unknown>) {
  const coverage = asRecord(option.coverage)
  const ready = compactValue(coverage.ready)
  const total = compactValue(coverage.total)
  return ready && total ? `覆盖 ${ready}/${total}` : null
}

function optionMissingText(option: Record<string, unknown>) {
  const rows = asRecordArray(option.missingData)
  const labels = rows.map(missingLabel).filter(Boolean)
  return labels.length ? `缺失 ${labels.slice(0, 2).join(', ')}` : null
}

function offlineSeedOptionRows(data: LiveRoundPackageResponse) {
  return asRecordArray(data.caddieContextSeeds)
    .flatMap((seed) => {
      const hole = compactValue(seed.hole) ?? '-'
      const selectedId = compactValue(seed.selectedOfflineOptionId)
      const sourceRef = compactValue(seed.sourceRef)
      return asRecordArray(seed.offlineOptions).map((option) => {
        const optionId = compactValue(option.id) ?? compactValue(option.optionId) ?? ''
        const label = optionLabelZh(compactValue(option.label) ?? (optionId || 'Option'))
        const club = compactValue(option.clubName) ?? '-'
        const carry = compactValue(option.carryM)
        const confidence = compactValue(option.confidence)
        const sampleSize = compactValue(option.sampleSize)
        const sourceRefs = Array.isArray(option.sourceRefs) ? option.sourceRefs.map(compactValue).filter(Boolean) : []
        const sampleRefs = Array.isArray(option.sampleRefs) ? option.sampleRefs.map(compactValue).filter(Boolean) : []
        return {
          key: `${hole}-${optionId || label}`,
          hole,
          label,
          club,
          carry,
          confidence,
          sampleSize,
          coverage: optionCoverageText(option),
          sourceRef: sourceRefs[0] ?? sourceRef,
          sampleRefCount: sampleRefs.length,
          missing: optionMissingText(option),
          selected: selectedId ? selectedId === optionId : false,
        }
      })
    })
    .slice(0, 12)
}

export function MobilePackagePrepPanel({
  state,
  courseOptionsState = { status: 'idle' },
  onPrepareRound,
  onPrepareCourse,
  onLoadCourseTees,
  defaultRoundId = '900001',
  defaultCourseGlobalId = '31795',
  showAdminTokenInput = false,
  adminTokenValue = '',
  onAdminTokenChange,
}: MobilePackagePrepPanelProps) {
  const [mode, setMode] = useState<PackagePrepMode>('round')
  const [roundId, setRoundId] = useState(defaultRoundId)
  const [courseGlobalId, setCourseGlobalId] = useState(defaultCourseGlobalId)
  const [selectedCourseOption, setSelectedCourseOption] = useState('')
  const [liveRoundId, setLiveRoundId] = useState('')
  const [teeBox, setTeeBox] = useState('')
  const [courseTees, setCourseTees] = useState<CourseTee[]>([])
  const [capturedAt, setCapturedAt] = useState('')
  const [ensureGeometry, setEnsureGeometry] = useState(true)
  const courseOptions = courseOptionsState.status === 'ready' && Array.isArray(courseOptionsState.data.courses)
    ? courseOptionsState.data.courses
    : []

  // 选了球场 → 拉该球场的可选发球台(颜色 + 总码数 + 默认),把发球台从手输框换成下拉。
  useEffect(() => {
    const gid = Number(courseGlobalId.trim())
    const canLoad = mode === 'course' && Number.isInteger(gid) && gid > 0 && Boolean(onLoadCourseTees)
    let cancelled = false
    async function loadTees() {
      if (!canLoad || !onLoadCourseTees) {
        setCourseTees([])
        return
      }
      try {
        const response = await onLoadCourseTees(gid)
        if (cancelled) return
        const tees = response.tees ?? []
        setCourseTees(tees)
        // 默认选中球场默认台;仅当当前所选台不在该球场可选台里时才改(不覆盖用户明确选择)。
        setTeeBox((prev) => {
          if (tees.some((tee) => tee.teeBox.toLowerCase() === prev.toLowerCase())) return prev
          return tees.find((tee) => tee.default)?.teeBox ?? response.defaultTeeBox ?? prev
        })
      } catch {
        if (!cancelled) setCourseTees([])
      }
    }
    void loadTees()
    return () => {
      cancelled = true
    }
  }, [mode, courseGlobalId, onLoadCourseTees])

  function handleCourseOptionChange(value: string) {
    setSelectedCourseOption(value)
    const option = courseOptions.find((row) => String(row.globalId) === value)
    if (!option) return
    setMode('course')
    setCourseGlobalId(String(option.globalId))
    setLiveRoundId(option.suggestedLiveRoundId ?? `live-${option.globalId}`)
    setTeeBox(option.teeBox && option.teeBox !== 'unknown' ? option.teeBox : '')
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const captured = trimmedOrUndefined(capturedAt)
    if (mode === 'round') {
      const nextRoundId = roundId.trim()
      if (!nextRoundId) return
      void onPrepareRound(nextRoundId, { capturedAt: captured, ensureGeometry })
      return
    }

    const parsedGlobalId = Number(courseGlobalId.trim())
    if (!Number.isInteger(parsedGlobalId) || parsedGlobalId <= 0) return
    void onPrepareCourse(parsedGlobalId, {
      roundId: trimmedOrUndefined(liveRoundId),
      teeBox: trimmedOrUndefined(teeBox),
      capturedAt: captured,
      ensureGeometry,
    })
  }

  const isLoading = state.status === 'loading'
  const readyData = state.status === 'ready' ? state.data : null
  const courseIdValue = Number(courseGlobalId.trim())
  const canPrepare = mode === 'round' ? Boolean(roundId.trim()) : Number.isInteger(courseIdValue) && courseIdValue > 0

  return (
    <section className="mobile-package-panel" aria-label="移动离线包准备">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">离线球局</p>
          <h2>离线包准备</h2>
        </div>
        {readyData ? <span className={`semantic-chip package-state-${readyData.offlinePackageStatus.state}`}>{stateZh(readyData.offlinePackageStatus.state)}</span> : null}
      </div>

      <form className="mobile-package-form" aria-label="离线包查询" onSubmit={handleSubmit}>
        <div className="package-mode-toggle" role="radiogroup" aria-label="打包模式">
          <label>
            <input
              type="radio"
              name="package-mode"
              checked={mode === 'round'}
              onChange={() => setMode('round')}
            />
            <span>球局</span>
          </label>
          <label>
            <input
              type="radio"
              name="package-mode"
              checked={mode === 'course'}
              onChange={() => setMode('course')}
            />
            <span>球场</span>
          </label>
        </div>

        {mode === 'round' ? (
          <label>
            <span>球局编号</span>
            <input value={roundId} onChange={(event) => setRoundId(event.target.value)} spellCheck={false} />
          </label>
        ) : (
          <>
            {courseOptions.length ? (
              <label>
                <span>最近球场</span>
                <select
                  value={selectedCourseOption}
                  onChange={(event) => handleCourseOptionChange(event.target.value)}
                >
                  <option value="">手动输入球场编号</option>
                  {courseOptions.map((option) => (
                    <option key={option.globalId} value={option.globalId}>
                      {option.name} / {option.holes} 洞 / {option.roundCount} 场
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <label>
              <span>球场全局编号</span>
              <input inputMode="numeric" value={courseGlobalId} onChange={(event) => setCourseGlobalId(event.target.value)} spellCheck={false} />
            </label>
            <label>
              <span>实战球局编号</span>
              <input value={liveRoundId} onChange={(event) => setLiveRoundId(event.target.value)} spellCheck={false} />
            </label>
            <label>
              <span>发球台</span>
              {courseTees.length ? (
                <select value={teeBox} onChange={(event) => setTeeBox(event.target.value)}>
                  {courseTees.map((tee) => (
                    <option key={tee.teeBox} value={tee.teeBox}>
                      {teeOptionLabel(tee)}
                    </option>
                  ))}
                </select>
              ) : (
                <input value={teeBox} onChange={(event) => setTeeBox(event.target.value)} spellCheck={false} />
              )}
            </label>
          </>
        )}

        <label>
          <span>采集时间</span>
          <input value={capturedAt} onChange={(event) => setCapturedAt(event.target.value)} spellCheck={false} placeholder="2026-05-25T08:00:00Z" />
        </label>

        <label className="package-checkbox">
          <input
            type="checkbox"
            checked={ensureGeometry}
            onChange={(event) => setEnsureGeometry(event.target.checked)}
          />
          <span>拉取几何</span>
        </label>

        {showAdminTokenInput ? (
          <label>
            <span>管理令牌</span>
            <input
              type="password"
              value={adminTokenValue}
              onChange={(event) => onAdminTokenChange?.(event.target.value)}
              spellCheck={false}
              autoComplete="off"
            />
          </label>
        ) : null}

        <button type="submit" disabled={!canPrepare || isLoading}>
          {isLoading ? '打包中' : '生成离线包'}
        </button>
      </form>

      {mode === 'course' && courseOptionsState.status === 'loading' ? (
        <p className="mobile-package-note">正在载入最近球场。</p>
      ) : null}

      {mode === 'course' && courseOptionsState.status === 'error' ? (
        <p className="mobile-package-note">球场选项不可用:{courseOptionsState.message}</p>
      ) : null}

      {state.status === 'idle' ? (
        <article className="stats-empty">
          <h2>尚未生成离线包</h2>
          <p>选择球局或球场后再开始实战。</p>
        </article>
      ) : null}

      {state.status === 'loading' ? (
        <article className="stats-empty">
          <h2>离线包生成中</h2>
          <p>{state.target}</p>
        </article>
      ) : null}

      {state.status === 'error' ? (
        <article className="stats-empty">
          <h2>离线包不可用</h2>
          <p>{state.message}</p>
        </article>
      ) : null}

      {readyData ? <PackageSummary data={readyData} /> : null}
    </section>
  )
}

function PackageSummary({ data }: { data: LiveRoundPackageResponse }) {
  const missingRows = data.missingData ?? []
  const readinessChecks = data.readinessChecks ?? []
  const seedOptions = offlineSeedOptionRows(data)
  return (
    <div className="mobile-package-body">
      <div className="package-summary-grid" aria-label="离线包摘要">
        <article>
          <span>球场</span>
          <strong>{data.course.name}</strong>
          <em>{data.course.globalId} / {data.course.teeBox}</em>
        </article>
        <article>
          <span>球局</span>
          <strong>{data.roundId}</strong>
          <em>{data.sourceCoverage.preparationMode === 'course' ? '球场包' : '球局包'}</em>
        </article>
        <article>
          <span>几何</span>
          <strong>{coverageZh(data.geometryCoverage.state)}</strong>
          <em>{data.geometryCoverage.readyHoles}/{data.geometryCoverage.totalHoles} 洞</em>
        </article>
        <article>
          <span>天气</span>
          <strong>天气{coverageZh(data.weatherSnapshot.state)}</strong>
          <em>{weatherCoverageText(data)}</em>
        </article>
      </div>

      <div className="package-chip-row" aria-label="离线包要点">
        {packageCoverageFacts(data).map((fact) => (
          <span key={fact}>{fact}</span>
        ))}
      </div>

      {readinessChecks.length ? (
        <div className="package-readiness-list" aria-label="离线包就绪检查">
          {readinessChecks.map((row) => (
            <div className="report-row" key={row.label}>
              <strong>{readinessTitle(row.label)}</strong>
              <span className={`semantic-chip package-state-${row.state}`}>{stateZh(row.state)}</span>
              <span>{row.ready}/{row.total}</span>
              <span>{row.reason}</span>
            </div>
          ))}
        </div>
      ) : null}

      {seedOptions.length ? (
        <div className="package-caddie-list" aria-label="离线球童候选">
          {seedOptions.map((row) => (
            <div className="report-row" key={row.key}>
              <strong>H{row.hole} {row.label}</strong>
              {row.selected ? <span className="semantic-chip package-state-ready">已选</span> : null}
              <span>{row.club}{row.carry ? ` / ${fmtYd(Number(row.carry))}` : ''}</span>
              {row.confidence ? <span>{confidenceZh(row.confidence)} 置信</span> : null}
              {row.sampleSize ? <span>{row.sampleSize} 个样本</span> : null}
              {row.coverage ? <span>{row.coverage}</span> : null}
              {row.sourceRef ? <span>来源 {row.sourceRef}</span> : null}
              {row.sampleRefCount ? <span>样本引用 {row.sampleRefCount}</span> : null}
              {row.missing ? <span>{row.missing}</span> : null}
            </div>
          ))}
        </div>
      ) : null}

      <div className="package-missing-list" aria-label="离线包缺失数据">
        {missingRows.length ? (
          missingRows.map((row, index) => (
            <div className="report-row" key={`${missingLabel(row)}-${index}`}>
              <strong>{missingLabel(row)}</strong>
              <span>{missingReason(row)}</span>
            </div>
          ))
        ) : (
          <div className="report-row">
            <strong>覆盖</strong>
            <span>就绪</span>
          </div>
        )}
      </div>
    </div>
  )
}
