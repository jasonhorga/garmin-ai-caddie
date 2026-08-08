import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { fetchCaddieContext, fetchCaddieDecision, fetchCoursePrep, topoImageUrl } from '../api'
import { fmtYd, metersFromYards } from '../units'
import { missDirectionZh } from '../zhLabels'
import type {
  CaddieContextParams,
  CaddieContextResponse,
  CaddieDecisionResponse,
  CaddieShotType,
  CoursePrepResponse,
  CourseSearchResponse,
  MobileCourseOption,
  MobileCourseOptionsResponse,
  RoundCard,
  WeatherSnapshotResponse,
} from '../types'
import { CourseFinder } from './CourseFinder'
import { HoleBaseImage } from './HoleBaseImage'
import { atCum, nearestCum } from './coursePrepPanelLogic'
import { asNumber, asRows, asString } from './statsValues'

// 决策沙盘 (spec §5.4 web scope, W3 T3+T4): pick a course (CourseFinder entry)
// → fetch its prep facts (default holes, shared topo projection) → pick a hole →
// place the ball on the hole map and read the situation (距T/到果岭) → set
// 球位状态/风/稳博 → 要建议 runs the context+decision pair and renders ONE
// main recommendation (advice card) with a 稳/默认/博 recompute toggle.
interface LiveSandboxProps {
  courseOptions: MobileCourseOptionsResponse | null
  adminToken?: string
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>
  // Latest rounds (overview recentRounds) — the advice sourceRef fallback when
  // the picked course has no played round of its own, or when none of its own
  // refs resolves on the backend (chain rule below).
  recentRounds: RoundCard[]
}

// PrepPage PrepDone idiom: the effect records only its settled result keyed by
// course+attempt; loading is DERIVED from a key mismatch so effects never set
// state synchronously and stale paints are impossible.
type PrepResult = { data: CoursePrepResponse } | { error: string }
interface PrepDone {
  key: string
  result: PrepResult
}

// ⚠ startX/startY/targetX/targetY UNITS — verified against the backend before
// wiring any drag→request mapping (W3 T3 finding; T4 consumes this):
// - server_v2/caddie.py:54-57 accepts start_x/start_y/target_x/target_y and
//   caddie.py:90-93 (`_local_point`) wraps the raw floats as {x, y} with NO
//   unit conversion; ai_caddie/caddie_context.py:216-222 forwards them to
//   build_route_geometry_evidence(start=…, target=…).
// - ai_caddie/geometry_evidence.py:132-140 (`_position_to_local`) returns the
//   {x, y} values UNCHANGED and compares them directly against hazard-polygon
//   coordinates; geometry_evidence.py:384+455 then report `routeLength_m` as
//   the plain Euclidean distance of those values (`distanceFromStart_m`
//   likewise at :564/:575) — i.e. ONE UNIT == ONE METRE, in the hole's
//   hazard-geometry LOCAL frame (x = metres east, y = metres north of the
//   hazard file's refLat/refLon anchor; frame defined by
//   ai_caddie/data.py:55-59 `wgs84_to_local`).
// - The prep map overlay is a DIFFERENT frame: `overlay.route` rows are
//   DISPLAY PIXELS produced by a rotate(tee→green up)+scale+translate
//   projection plus /SS downsample (ai_caddie/hole_render.py:59-62,107-111,
//   183-190; ppm = px per metre). The payload ships no inverse transform
//   (no tee/u/perp/cx/amin), so the client CANNOT recover local-frame metre
//   coordinates from a dragged pixel; px/ppm only converts pixel *distances*
//   to metres within the rotated render frame.
// → Therefore the sandbox MUST NOT feed dragged px into startX/…/targetY. The
//   ball state below is `ballCum` (true metres along the playing route — the
//   overlay cum stamps are computed from local-metre route geometry,
//   hole_render.py:185-189), and T4 sends `distanceToPinM = overlay.ln −
//   ballCum` (rounded 1dp) + the derived shotType instead of route coords,
//   until the prep payload also ships the local-metre route or the inverse
//   transform (backend change, out of scope for this frontend-only phase).

function findCourseOption(courseOptions: MobileCourseOptionsResponse | null, globalId: number): MobileCourseOption | null {
  if (!courseOptions || !Array.isArray(courseOptions.courses)) return null
  return (
    courseOptions.courses.find(
      (course): course is MobileCourseOption =>
        course !== null && typeof course === 'object' && course.globalId === globalId && typeof course.name === 'string',
    ) ?? null
  )
}

// 要建议 sourceRef rule — pinned against the backend before wiring (W3 T4):
// build_caddie_context REQUIRES a resolvable PLAYED history ref —
// resolve_history_ref (ai_caddie/history_drilldown.py:134-160) must find it or
// the whole context degrades to _missing_context with NO clubProfiles/
// geometry/history (ai_caddie/caddie_context.py:40-42). A 'roundId:hole' ref
// resolves only when that hole exists in that round
// (history_drilldown.py:147-151) and binds geometry/history through the
// ROUND's own globalId (caddie_context.py:47-67), so a cross-course
// 'anyRound:hole' ref would either fail outright or inject ANOTHER course's
// hazards into this course's simulation. The rule is an ORDERED candidate
// chain — requestAdvice walks it until one ref RESOLVES, because an
// unresolvable ref is NOT an HTTP error (see isUnresolvedContext below):
// 1) latest played round ON THIS COURSE + ':hole' → full same-course binding.
//    Derivable client-side from MobileCourseOption.latestRoundId — the newest
//    round grouped by this globalId (ai_caddie/mobile_live.py:303-323);
//    sourceRefs[0] is the same newest-first list's head (fallback for older
//    payloads without latestRoundId).
// 2) the same on-course round as a BARE round ref — a known round always
//    resolves bare (history_drilldown.py:134-135,143-146) even when it lacks
//    this hole (e.g. a 9-hole round on an 18-hole course); clubProfiles and
//    the stored weather still bind (caddie_context.py:104-137) — NOT
//    playerProfile, which only binds through the hole-keyed history context
//    (_history_context bails without a local hole,
//    caddie_context.py:238-291) — while geometry+hole history degrade to
//    explicit missingData (caddie_context.py:74) instead of wrong-course
//    facts.
// 3) the latest ANY round (recentRounds[0]) as a BARE round ref, same
//    degraded-but-honest binding as 2.
// 4) empty chain → 要建议 disabled with a zh hint.
function adviceSourceRefChain(
  courseOptions: MobileCourseOptionsResponse | null,
  globalId: number,
  holeNumber: number | null,
  recentRounds: RoundCard[],
): string[] {
  const option = findCourseOption(courseOptions, globalId)
  const refs = option !== null && Array.isArray(option.sourceRefs) ? option.sourceRefs : []
  const latestOnCourse = asString(option?.latestRoundId) ?? asString(refs[0])
  const latestAny = asString(recentRounds[0]?.id)
  const chain: string[] = []
  if (latestOnCourse !== null && holeNumber !== null) chain.push(`${latestOnCourse}:${holeNumber}`)
  if (latestOnCourse !== null) chain.push(latestOnCourse)
  if (latestAny !== null) chain.push(latestAny)
  // Dedupe (e.g. latest ANY round == the on-course round): retrying the exact
  // ref that just failed to resolve would be a wasted request.
  return chain.filter((ref, index) => chain.indexOf(ref) === index)
}

// Unresolved-ref detection (W3 adversarial review, REPRODUCED on real data:
// 4/24 courses): when the ref does not resolve, the backend still answers
// HTTP 200 with the _missing_context shape (caddie_context.py:227-235) —
// context carries ONLY {source, sourceRef, shotType} and the user's
// distance/lie are silently DROPPED, after which the decision engine floors
// the missing distance to 1m and emits absurd ~7m advice. Key the detection
// on both signals of that shape: a RESOLVED context always carries roundId
// (caddie_context.py:157-158), and the degraded one carries the 'source_ref'
// missingData row.
function isUnresolvedContext(response: CaddieContextResponse): boolean {
  if (asString(recordFrom(response.context).roundId) === null) return true
  return asRows(response.missingData).some((row) => asString(row.label) === 'source_ref')
}

// CaddiePage numericInput idiom: blank → undefined, otherwise a finite number.
function parseNumberInput(value: string): number | undefined {
  if (!value.trim()) return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function recordFrom(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

// Manual wind must be CONSTRUCTED client-side, not fetched: the snapshot
// endpoint without latitude/longitude builds state:'missing'
// (ai_caddie/weather_context.py:91-98) and the decision engine ignores any
// snapshot whose state is not 'ready' (ai_caddie/decision.py:1481-1483,
// 2643-2645) — a manual fetch would silently no-op because the sandbox has no
// geo coordinates for the simulated ball (see the units note above). The
// engine reads only state/windSpeedMps/windDirectionDeg (+temperatureC for
// evidence text, decision.py:1466-1476), so a shape-compatible
// WeatherSnapshotResponse with state 'ready' is the cheapest CORRECT path;
// confidence mirrors the backend's manual-ready 'medium'
// (weather_context.py:111).
//
// The input is ONE 逆风 speed on purpose (W3 review honesty fix): the
// direction-aware head/tail/cross split needs BOTH windDirectionDeg AND
// context.shotBearingDeg, and without a bearing the engine classifies ANY
// direction as pure headwind at +1.5×speed metres (decision.py:1487-1502).
// The sandbox can never supply shotBearingDeg (no geo frame, see the units
// note), so a 风向 input would be an inert control that silently changes
// nothing — the snapshot ships windDirectionDeg: null and the label promises
// exactly what the engine computes (逆风折算;顺风请留空). The engine treats
// speed<=0 as no adjustment, so the snapshot only attaches when a speed is
// set.
function manualWindSnapshot(headwindSpeed: string): WeatherSnapshotResponse | null {
  const speed = parseNumberInput(headwindSpeed)
  if (speed === undefined || speed < 0) return null
  return {
    schema: 'ai-caddie-weather-snapshot-v1',
    state: 'ready',
    source: 'manual',
    roundId: null,
    hole: null,
    capturedAt: new Date().toISOString(),
    location: null,
    windSpeedMps: speed,
    windDirectionDeg: null,
    temperatureC: null,
    precipitationMm: null,
    confidence: 'medium',
    missingData: [],
  }
}

// CaddiePage selectedDecisionOption idiom: resolve the selected id inside
// options first, then fall back to the loosely-typed selectedOption/selected
// records the API may ship instead.
function selectedDecisionOption(decision: CaddieDecisionResponse): Record<string, unknown> {
  const selectedId = asString(decision.selectedOptionId)
  const fromOptions =
    selectedId === null ? undefined : asRows(decision.options).find((option) => asString(option.id) === selectedId)
  if (fromOptions) return fromOptions
  return recordFrom(decision.selectedOption ?? decision.selected)
}

// CaddiePage optionClubLabel idiom: direct club fields first, then the
// clubRecommendation rows.
function optionClub(option: Record<string, unknown>): string {
  const direct = asString(option.recommendedClub) ?? asString(option.club)
  if (direct !== null) return direct
  const clubs = asRows(recordFrom(option.clubRecommendation).clubs)
    .map((club) => asString(club.clubName) ?? asString(club.name))
    .filter((name): name is string => name !== null)
  return clubs.length ? clubs.slice(0, 2).join(' / ') : '—'
}

// Decision riskScore is an additive scale: base 1 (safe/stock) / 3 (attack)
// plus hazard penalties +1/+3/+6 (ai_caddie/decision.py:957-975). ≤2 reads as
// a clean conservative line, ≤4 as attack-base or mildly pressured, above as
// hazard-hot.
function riskClass(score: number): string {
  return score <= 2 ? 'low' : score <= 4 ? 'medium' : 'high'
}

const CONFIDENCE_ZH: Record<string, string> = { high: '信心高', medium: '信心中', low: '信心低' }

function confidencePill(confidence: string | null): React.ReactElement | null {
  if (confidence === null) return null
  return <span className={`confidence-pill ${confidence}`}>{CONFIDENCE_ZH[confidence] ?? confidence}</span>
}

// 落点/风险/信心 numbers for one option (主建议 meta + 其它选项 detail line).
function optionNumbers(option: Record<string, unknown>): string[] {
  const carry = asNumber(option.carry_m)
  const risk = asNumber(option.riskScore)
  const confidence = asString(option.confidence)
  const parts: string[] = []
  if (carry !== null) parts.push(`落点 ${fmtYd(carry)}`)
  if (risk !== null) parts.push(`风险 ${risk}`)
  if (confidence !== null) parts.push(CONFIDENCE_ZH[confidence] ?? confidence)
  return parts
}

type AdviceState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; decision: CaddieDecisionResponse }

// Situation distances display in yards (fmtYd); distanceToPinM sent to the
// engine stays in metres (the API's resolution unit — see the units note above).

const SHOT_TYPE_OPTIONS: Array<{ value: CaddieShotType; label: string }> = [
  { value: 'tee', label: '开球' },
  { value: 'approach', label: '攻果岭' },
  { value: 'recovery', label: '救球' },
]

// 球位状态 → the lie strings the engine vocabulary uses.
const LIE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'fairway', label: '球道' },
  { value: 'rough', label: '长草' },
  { value: 'bunker', label: '沙坑' },
  { value: 'fringe', label: '果岭边' },
  { value: 'green', label: '果岭' },
]

// 稳/默认/博 → context.strategyMode ('' = stock, omitted from the request the
// same way CaddiePage's buildContextLoadParams skips blank modes).
const STRATEGY_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'protect_score', label: '稳' },
  { value: '', label: '默认' },
  { value: 'attack', label: '博' },
]

export function LiveSandbox({ courseOptions, adminToken, onSearchCourses, recentRounds }: LiveSandboxProps) {
  // course === null → entry state (course finder).
  const [course, setCourse] = useState<{ globalId: number; name: string | null } | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [done, setDone] = useState<PrepDone | null>(null)
  // selectedHole === null → default to the first hole in the response.
  const [selectedHole, setSelectedHole] = useState<number | null>(null)
  // Ball position as metres along the playing route (cum); 0 == on the tee.
  // See the units note above: cum metres (not overlay px) is the state T4 maps
  // into the decision request (distanceToPinM = ln − ballCum).
  const [ballCum, setBallCum] = useState(0)
  // null → shotType derives from the ball (tee at cum 0, otherwise approach);
  // a user pick from the 击球类型 select wins until the hole changes.
  const [shotTypeOverride, setShotTypeOverride] = useState<CaddieShotType | null>(null)
  // Manual 到果岭 metres (keyboard path). On mapped holes it is an OVERRIDE
  // that wins over the dragged ball until the next drag clears it; on holes
  // without rendered geometry it is the ONLY distance input — the sandbox
  // stays fully usable either way (T4 reads distanceToPinM from here).
  const [manualToGreen, setManualToGreen] = useState('')
  // 球位状态 (sent for non-tee shots only: the context builder excuses tee
  // shots from the lie requirement, ai_caddie/caddie_context.py:100-102, and
  // none of the five surface strings describes a tee box).
  const [lie, setLie] = useState('fairway')
  // Optional manual 逆风 (m/s) → client-built headwind-only snapshot.
  const [windSpeed, setWindSpeed] = useState('')
  // 稳/默认/博; sticky across holes — a player preference, not a ball fact.
  const [strategyMode, setStrategyMode] = useState('')
  const [advice, setAdvice] = useState<AdviceState>({ status: 'idle' })
  // 其它选项 chip currently expanded on the advice card.
  const [altOptionId, setAltOptionId] = useState<string | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  // The W1b seq-ref race guard (HomeOverview searchSeq idiom): a stale prep
  // response from an earlier course/attempt must never clobber the latest one.
  const prepSeq = useRef(0)
  // Same guard for the 要建议 context+decision pair: 稳/博 re-requests and
  // hole/course switches must drop any in-flight stale advice.
  const adviceSeq = useRef(0)

  useEffect(() => {
    if (course === null) return
    const key = `${course.globalId}:${attempt}`
    const seq = ++prepSeq.current
    // The shared topo endpoint owns the bitmap.  Requesting an embedded JPEG for every hole made a
    // cold sandbox rebuild the same maps before it could open; projection facts are sufficient for
    // the draggable overlay. include_shots stays off because this surface places one simulated ball.
    fetchCoursePrep(course.globalId, { render: false }, adminToken)
      .then((data) => {
        if (prepSeq.current !== seq) return
        setDone({ key, result: { data } })
      })
      .catch((error: unknown) => {
        if (prepSeq.current !== seq) return
        setDone({ key, result: { error: error instanceof Error ? error.message : '未知错误' } })
      })
  }, [course, adminToken, attempt])

  const resetBall = () => {
    setBallCum(0)
    setShotTypeOverride(null)
    setManualToGreen('')
    // A new hole/course is a new simulation: drop the advice card and
    // invalidate any in-flight advice request (lie/wind/strategy stay — they
    // are conditions and preferences, not ball state).
    adviceSeq.current += 1
    setAdvice({ status: 'idle' })
    setAltOptionId(null)
  }

  const selectCourse = (globalId: number, name?: string) => {
    setCourse({ globalId, name: typeof name === 'string' && name.trim() ? name : null })
    setAttempt(0)
    setSelectedHole(null)
    resetBall()
  }

  const resetToEntry = () => {
    setCourse(null)
    setDone(null)
    setAttempt(0)
    setSelectedHole(null)
    resetBall()
  }

  // Hole switch resets the simulation: ball back to that hole's tee, shot type
  // back to derived.
  const selectHole = (hole: number) => {
    setSelectedHole(hole)
    resetBall()
  }

  if (course === null) {
    return (
      <section className="panel prep-entry">
        <CourseFinder
          heading="选择球场开始模拟"
          sub="搜索球场,或从常打球场直接开始模拟。"
          ctaLabel="开始模拟"
          courseOptions={courseOptions}
          onSearchCourses={onSearchCourses}
          onSelectCourse={selectCourse}
        />
      </section>
    )
  }

  const key = `${course.globalId}:${attempt}`
  const current = done !== null && done.key === key ? done.result : null
  const data = current !== null && 'data' in current ? current.data : null
  const error = current !== null && 'error' in current ? current.error : null
  const holes = data && Array.isArray(data.holes) ? data.holes : []
  const hole = holes.find((row) => row.hole === selectedHole) ?? holes[0] ?? null

  // courseOptions (played, canonical) wins; the finder-handed search name
  // covers never-played courses; the bare gid is the last resort (W2 idiom).
  const courseName = findCourseOption(courseOptions, course.globalId)?.name ?? course.name ?? `球场 ${course.globalId}`

  const overlay = hole?.map?.overlay ?? null
  // Keyboard path on mapped holes (W3 review): the 到果岭 input accepts yards;
  // metersFromYards converts to the metre domain for effectiveCum + the API.
  // effectiveCum places the ball marker at atCum(ln − manualDistanceM) while it
  // stays within the route; a value past the route has no honest position (the
  // marker hides) but the distance still drives the request.
  const manualYards = parseNumberInput(manualToGreen)
  const manualDistanceM = manualYards !== undefined ? metersFromYards(manualYards) : undefined
  const effectiveCum = overlay !== null && manualDistanceM !== undefined ? overlay.ln - manualDistanceM : ballCum
  const ballOnRoute = overlay !== null && effectiveCum >= 0 && effectiveCum <= overlay.ln
  // shotType derives from the ball — on the tee (cum 0) it's a tee shot,
  // anywhere down the route it's an approach; the no-map mode mirrors this
  // (nothing entered ≈ still on the tee). A user 击球类型 pick wins until the
  // hole changes.
  const derivedShotType: CaddieShotType = (overlay !== null ? effectiveCum === 0 : manualToGreen.trim() === '') ? 'tee' : 'approach'
  const shotType: CaddieShotType = shotTypeOverride ?? derivedShotType

  const onPointer = (event: ReactPointerEvent<SVGSVGElement>): void => {
    if (overlay === null || !svgRef.current) return
    // Ignore plain hovers: only a pressed pointer drags the ball.
    if (event.buttons === 0 && event.type === 'pointermove') return
    const rect = svgRef.current.getBoundingClientRect()
    const px = ((event.clientX - rect.left) / rect.width) * overlay.w
    const py = ((event.clientY - rect.top) / rect.height) * overlay.h
    setBallCum(nearestCum(overlay.route, px, py))
    // A drag is a new ball placement: it supersedes any typed 到果岭 override.
    setManualToGreen('')
  }

  const adviceRefChain = adviceSourceRefChain(courseOptions, course.globalId, hole?.hole ?? null, recentRounds)
  // distanceToPinM per the units note above: 到果岭 = ln − effectiveCum (1dp,
  // i.e. the typed override when set, else the dragged ball) on the map, the
  // manual 到果岭 input alone in the degraded mode (blank/invalid → omitted;
  // tee shots are excused from distance, approach/recovery get a backend
  // missing_data chip instead of a client error).
  const adviceDistance = overlay !== null ? manualDistanceM ?? Math.round((overlay.ln - ballCum) * 10) / 10 : manualDistanceM

  const requestAdvice = (mode: string) => {
    if (adviceRefChain.length === 0) return
    const requestShotType = shotType
    const seq = ++adviceSeq.current
    setAdvice({ status: 'loading' })
    setAltOptionId(null)
    const paramsFor = (sourceRef: string): CaddieContextParams => {
      const params: CaddieContextParams = {
        sourceRef,
        shotType: requestShotType,
        capturedAt: new Date().toISOString(),
      }
      if (adviceDistance !== undefined) params.distanceToPinM = adviceDistance
      if (requestShotType !== 'tee') params.lie = lie
      if (mode.trim()) params.strategyMode = mode
      return params
    }
    // Walk the candidate chain until one ref RESOLVES (see isUnresolvedContext:
    // an unresolved ref is an HTTP-200 _missing_context that silently DROPS the
    // typed distance/lie — feeding it onward would floor the distance to 1m and
    // recommend a 7m chip from 200m out). Each fallback re-sends the full
    // situation against the next ref; the chain is finite (≤3 documented
    // candidates, deduped) and stops as soon as a newer request bumps
    // adviceSeq, so retries can neither loop nor race a fresher simulation.
    const resolveContext = async (): Promise<CaddieContextResponse> => {
      for (let index = 0; index < adviceRefChain.length; index += 1) {
        if (index > 0 && adviceSeq.current !== seq) break
        const response = await fetchCaddieContext(paramsFor(adviceRefChain[index]), adminToken)
        if (!isUnresolvedContext(response)) return response
      }
      throw new Error('历史球局引用无法解析,无法生成建议')
    }
    const windSnapshot = manualWindSnapshot(windSpeed)
    resolveContext()
      .then((contextResponse) =>
        // Mirrors CaddiePage's buildDecisionRequest (CaddiePage.tsx:1603-1625):
        // spread the loaded context, re-assert shotType, then layer the
        // weatherSnapshot on top — last spread wins, so the manual wind
        // overrides any stored snapshot the context builder bound.
        fetchCaddieDecision(
          {
            shotType: requestShotType,
            context: {
              ...contextResponse.context,
              shotType: requestShotType,
              ...(windSnapshot ? { weatherSnapshot: windSnapshot } : {}),
            },
            includeExplanation: true,
          },
          adminToken,
        ),
      )
      .then((decision) => {
        if (adviceSeq.current !== seq) return
        setAdvice({ status: 'ready', decision })
      })
      .catch((error: unknown) => {
        if (adviceSeq.current !== seq) return
        setAdvice({ status: 'error', message: error instanceof Error ? error.message : '未知错误' })
      })
  }

  // 稳/博 switch RE-REQUESTS the pair with the new mode once an advice exists
  // (idle = nothing requested yet → just record the preference).
  const selectStrategy = (mode: string) => {
    setStrategyMode(mode)
    if (advice.status !== 'idle') requestAdvice(mode)
  }

  const shotTypeControl = (
    <label className="live-sandbox-control">
      <span>击球类型</span>
      <select
        aria-label="击球类型"
        value={shotType}
        onChange={(event) => setShotTypeOverride(event.target.value as CaddieShotType)}
      >
        {SHOT_TYPE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )

  const situationControls = (
    <>
      {shotTypeControl}
      <label className="live-sandbox-control">
        <span>球位状态</span>
        <select
          aria-label="球位状态"
          value={lie}
          disabled={shotType === 'tee'}
          title={shotType === 'tee' ? '开球无需球位状态' : undefined}
          onChange={(event) => setLie(event.target.value)}
        >
          {LIE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="live-sandbox-control live-sandbox-control--helper">
        <span>逆风(m/s)</span>
        <input
          type="number"
          aria-label="逆风(m/s)"
          min={0}
          step="0.1"
          inputMode="decimal"
          placeholder="选填"
          value={windSpeed}
          onChange={(event) => setWindSpeed(event.target.value)}
        />
        <span className="live-sandbox-helper">引擎按逆风折算;顺风请留空</span>
      </label>
    </>
  )

  // The manual 到果岭 control renders in BOTH hole modes (next to the readout
  // on mapped holes, alone in the degraded mode) — exactly one instance exists
  // at a time, so its label stays unique.
  const manualDistanceControl = (
    <label className="live-sandbox-control">
      <span>到果岭(码)</span>
      <input
        type="number"
        aria-label="到果岭(码)"
        min={0}
        inputMode="decimal"
        placeholder="如 150"
        value={manualToGreen}
        onChange={(event) => setManualToGreen(event.target.value)}
      />
    </label>
  )

  let holeStage: React.ReactElement | null = null
  if (hole !== null && overlay !== null) {
    const tee = atCum(overlay.route, 0)
    const green = atCum(overlay.route, overlay.ln)
    // A typed 到果岭 past the route length has no honest map position — render
    // no ball rather than extrapolating a marker off the playing line.
    const ball = ballOnRoute ? atCum(overlay.route, effectiveCum) : null
    const readout = ballOnRoute
      ? `距T ${fmtYd(effectiveCum)} · 到果岭 ${fmtYd(overlay.ln - effectiveCum)}`
      : `到果岭 ${fmtYd(manualDistanceM ?? 0)}`
    holeStage = (
      <div className="live-sandbox-hole">
        <div
          className="live-sandbox-map"
          style={{ aspectRatio: `${overlay.w} / ${overlay.h}` }}
        >
          <HoleBaseImage
            className="live-sandbox-base"
            topoSrc={hole.geometryCoverage === 'ready'
              ? topoImageUrl(course.globalId, hole.hole, hole.geometryRevision)
              : undefined}
            fallbackSrc={hole.map?.image}
            alt={`第${hole.hole}洞球道图`}
          />
          <svg
            ref={svgRef}
            className="live-sandbox-canvas"
            viewBox={`0 0 ${overlay.w} ${overlay.h}`}
            onPointerDown={onPointer}
            onPointerMove={onPointer}
          >
            <polyline
              points={overlay.route.map((point) => `${point[0]},${point[1]}`).join(' ')}
              fill="none"
              stroke="#fff"
              strokeOpacity={0.85}
              strokeWidth={3}
              strokeDasharray="6 5"
            />
            <circle cx={tee.x} cy={tee.y} r={9} fill="#4aa3d6" stroke="#fff" strokeWidth={3} />
            <circle cx={green.x} cy={green.y} r={7} fill="#fff" stroke="#333" strokeWidth={2} />
            {ball !== null ? <circle cx={ball.x} cy={ball.y} r={12} fill="#e8963a" stroke="#fff" strokeWidth={3} /> : null}
          </svg>
        </div>
        <div className="live-sandbox-readout-row">
          <p className="live-sandbox-readout">{readout}</p>
          {manualDistanceControl}
        </div>
        <p className="live-sandbox-hint">拖动橙球摆位,或直接键入到果岭距离</p>
        <div className="live-sandbox-controls">{situationControls}</div>
      </div>
    )
  } else if (hole !== null) {
    holeStage = (
      <div className="live-sandbox-hole">
        <p className="live-sandbox-nomap">此洞暂无几何图,直接输入到果岭距离。</p>
        <div className="live-sandbox-controls">
          {manualDistanceControl}
          {situationControls}
        </div>
      </div>
    )
  }

  // 策略 (稳/默认/博) + 要建议 sit under the situation controls for any
  // selected hole, mapped or not.
  const adviceActions =
    hole === null ? null : (
      <div className="live-advice-actions">
        <div className="live-strategy" role="group" aria-label="策略">
          {STRATEGY_OPTIONS.map((option) => (
            <button
              key={option.value || 'stock'}
              type="button"
              className={strategyMode === option.value ? 'live-strategy-chip active' : 'live-strategy-chip'}
              aria-pressed={strategyMode === option.value}
              onClick={() => selectStrategy(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="live-advice-cta"
          disabled={adviceRefChain.length === 0 || advice.status === 'loading'}
          onClick={() => requestAdvice(strategyMode)}
        >
          要建议
        </button>
        {adviceRefChain.length === 0 ? <span className="live-advice-hint">暂无历史球局,无法生成建议</span> : null}
      </div>
    )

  let adviceSection: React.ReactElement | null = null
  if (advice.status === 'loading') {
    adviceSection = (
      <section className="panel live-advice" aria-label="沙盘建议">
        <p className="live-advice-loading">建议生成中…</p>
      </section>
    )
  } else if (advice.status === 'error') {
    adviceSection = (
      <section className="panel empty-state prep-load-error" aria-label="建议生成失败" aria-live="polite">
        <h2>建议生成失败</h2>
        <p>{advice.message}</p>
        <button type="button" onClick={() => requestAdvice(strategyMode)}>
          重试
        </button>
      </section>
    )
  } else if (advice.status === 'ready') {
    adviceSection = <AdviceCard decision={advice.decision} altOptionId={altOptionId} onSelectAlt={setAltOptionId} />
  }

  return (
    <>
      <header className="panel prep-course-header">
        <div className="prep-course-info">
          <h2>{courseName}</h2>
          <p className="prep-course-meta">决策沙盘 · 选洞摆球,模拟下一杆</p>
        </div>
        <button type="button" className="prep-change-course" onClick={resetToEntry}>
          换球场
        </button>
      </header>
      {error !== null ? (
        <section className="panel empty-state prep-load-error" aria-label="沙盘加载失败" aria-live="polite">
          <h2>沙盘加载失败</h2>
          <p>{error}</p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>
            重试
          </button>
        </section>
      ) : data === null ? (
        <section className="panel">
          <p className="prep-tab-placeholder">沙盘加载中…</p>
        </section>
      ) : (
        <>
          <section className="panel live-sandbox-stage">
            <div className="live-hole-chips" role="group" aria-label="选洞">
              {holes.map((row) => (
                <button
                  key={row.hole}
                  type="button"
                  className={hole !== null && row.hole === hole.hole ? 'live-hole-chip active' : 'live-hole-chip'}
                  aria-label={`第${row.hole}洞`}
                  aria-current={hole !== null && row.hole === hole.hole ? 'true' : undefined}
                  onClick={() => selectHole(row.hole)}
                >
                  {row.hole}
                </button>
              ))}
            </div>
            {holeStage}
            {adviceActions}
          </section>
          {adviceSection}
        </>
      )}
    </>
  )
}

// The ONE main recommendation (spec D7): selected option front and centre,
// 为什么 narrative, acceptable miss, the other options as informational chips,
// and the engine's missing-data chips. Decision payload fields are loosely
// typed Records — every read narrows defensively (CaddiePage idiom).
function AdviceCard({
  decision,
  altOptionId,
  onSelectAlt,
}: {
  decision: CaddieDecisionResponse
  altOptionId: string | null
  onSelectAlt: (optionId: string | null) => void
}) {
  const selected = selectedDecisionOption(decision)
  const selectedId = asString(selected.id) ?? asString(decision.selectedOptionId) ?? ''
  const label = asString(selected.label) ?? selectedId
  const carry = asNumber(selected.carry_m)
  const risk = asNumber(selected.riskScore)
  const confidence = asString(selected.confidence) ?? asString(recordFrom(decision.confidence).level)
  const narrative = asString(recordFrom(decision.explanation).narrative)
  const miss = recordFrom(decision.acceptableMiss)
  const missDirectionRaw = asString(miss.direction) ?? asString(miss.side)
  // acceptableMiss.direction bearings render zh; looser engine tokens
  // (away_from_known_risks / wide_side / history_*) pass through raw.
  const missDirection = missDirectionRaw === null ? null : missDirectionZh(missDirectionRaw)
  const missRationale = asString(miss.rationale)
  const others = asRows(decision.options).filter((option) => asString(option.id) !== selectedId)
  const alt = others.find((option) => asString(option.id) === altOptionId) ?? null
  const missingRows = asRows(decision.missingData)

  return (
    <section className="panel live-advice" aria-label="沙盘建议">
      <div className="live-advice-main">
        <span className="live-advice-club">{optionClub(selected)}</span>
        <div className="live-advice-meta">
          {label ? <span className="live-advice-option-label">{label}</span> : null}
          {carry !== null ? <span className="live-advice-carry">{`落点 ${fmtYd(carry)}`}</span> : null}
          {/* 风险 is VISIBLE text (not an aria-label-only dot): sighted users
              get the number too; the dot stays as a pure severity tint. */}
          {risk !== null ? (
            <span className={`live-advice-risk ${riskClass(risk)}`}>
              <span className={`live-risk-dot ${riskClass(risk)}`} aria-hidden="true" />
              {`风险 ${risk}`}
            </span>
          ) : null}
          {confidencePill(confidence)}
        </div>
      </div>
      {narrative !== null ? (
        <p className="live-advice-why">
          <strong>为什么</strong>
          {narrative}
        </p>
      ) : null}
      {missDirection !== null || missRationale !== null ? (
        <p className="live-advice-miss">{`可接受偏向:${[missDirection, missRationale].filter((part) => part !== null).join(' — ')}`}</p>
      ) : null}
      {others.length ? (
        // role=group: an aria-label on a generic div names nothing in the
        // accessibility tree; the explicit group role makes it land.
        <div className="live-advice-others" role="group" aria-label="其它选项">
          <span className="live-advice-others-label">其它选项</span>
          {others.map((option) => {
            const id = asString(option.id) ?? optionClub(option)
            const active = altOptionId === id
            return (
              <button
                key={id}
                type="button"
                className={active ? 'live-advice-chip active' : 'live-advice-chip'}
                aria-pressed={active}
                onClick={() => onSelectAlt(active ? null : id)}
              >
                {[asString(option.label) ?? id, optionClub(option)].join(' · ')}
              </button>
            )
          })}
          {alt !== null ? <p className="live-advice-alt">{optionNumbers(alt).join(' · ') || '暂无数据'}</p> : null}
        </div>
      ) : null}
      {missingRows.length ? (
        <div className="live-advice-missing" role="group" aria-label="数据缺口">
          {missingRows.map((row, index) => (
            <span key={`${asString(row.label) ?? 'missing'}-${index}`} className="fact-chip" title={asString(row.reason) ?? undefined}>
              {asString(row.label) ?? '未知'}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  )
}
