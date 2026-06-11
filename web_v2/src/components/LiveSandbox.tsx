import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { fetchCoursePrep } from '../api'
import type {
  CaddieShotType,
  CoursePrepResponse,
  CourseSearchResponse,
  MobileCourseOption,
  MobileCourseOptionsResponse,
} from '../types'
import { CourseFinder } from './CourseFinder'
import { atCum, nearestCum } from './coursePrepPanelLogic'

// 决策沙盘 (spec §5.4 web scope, W3 T3): pick a course (CourseFinder entry) →
// fetch its prep payload (default holes, rendered maps) → pick a hole → place
// the ball on the hole map and read the situation (距T/到果岭). T4 adds the
// 球位/风/稳博 inputs and the decision advice card on top of this state.
interface LiveSandboxProps {
  courseOptions: MobileCourseOptionsResponse | null
  adminToken?: string
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>
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

// Situation distances render in metres at 1dp (matching distanceToPinM's
// resolution) — the prep card speaks yards, the sandbox speaks the engine's m.
function formatMetres(value: number): string {
  return String(Math.round(value * 10) / 10)
}

const SHOT_TYPE_OPTIONS: Array<{ value: CaddieShotType; label: string }> = [
  { value: 'tee', label: '开球' },
  { value: 'approach', label: '攻果岭' },
  { value: 'recovery', label: '救球' },
]

export function LiveSandbox({ courseOptions, adminToken, onSearchCourses }: LiveSandboxProps) {
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
  // Degraded no-map mode: holes without rendered geometry swap the canvas for
  // this manual 到果岭 metres input — the sandbox stays fully usable (T4 reads
  // distanceToPinM from here when there is no ball to drag).
  const [manualToGreen, setManualToGreen] = useState('')
  const svgRef = useRef<SVGSVGElement>(null)
  // The W1b seq-ref race guard (HomeOverview searchSeq idiom): a stale prep
  // response from an earlier course/attempt must never clobber the latest one.
  const prepSeq = useRef(0)

  useEffect(() => {
    if (course === null) return
    const key = `${course.globalId}:${attempt}`
    const seq = ++prepSeq.current
    // Default holes + default render (the sandbox needs the map images);
    // include_shots stays off — the sandbox places ONE simulated ball, not the
    // prep scatter.
    fetchCoursePrep(course.globalId, {}, adminToken)
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
  // shotType derives from the ball — on the tee (cum 0) it's a tee shot,
  // anywhere down the route it's an approach; the no-map mode mirrors this
  // (nothing entered ≈ still on the tee). A user 击球类型 pick wins until the
  // hole changes.
  const derivedShotType: CaddieShotType = (overlay !== null ? ballCum === 0 : manualToGreen.trim() === '') ? 'tee' : 'approach'
  const shotType: CaddieShotType = shotTypeOverride ?? derivedShotType

  const onPointer = (event: ReactPointerEvent<SVGSVGElement>): void => {
    if (overlay === null || !svgRef.current) return
    // Ignore plain hovers: only a pressed pointer drags the ball.
    if (event.buttons === 0 && event.type === 'pointermove') return
    const rect = svgRef.current.getBoundingClientRect()
    const px = ((event.clientX - rect.left) / rect.width) * overlay.w
    const py = ((event.clientY - rect.top) / rect.height) * overlay.h
    setBallCum(nearestCum(overlay.route, px, py))
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

  let holeStage: React.ReactElement | null = null
  if (hole !== null && hole.map && overlay !== null) {
    const tee = atCum(overlay.route, 0)
    const green = atCum(overlay.route, overlay.ln)
    const ball = atCum(overlay.route, ballCum)
    holeStage = (
      <div className="live-sandbox-hole">
        <div className="live-sandbox-map">
          <img src={hole.map.image} alt={`第${hole.hole}洞球道图`} />
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
            <circle cx={ball.x} cy={ball.y} r={12} fill="#e8963a" stroke="#fff" strokeWidth={3} />
          </svg>
        </div>
        <p className="live-sandbox-readout">{`距T ${formatMetres(ballCum)}m · 到果岭 ${formatMetres(overlay.ln - ballCum)}m`}</p>
        <p className="live-sandbox-hint">拖动橙球摆位</p>
        <div className="live-sandbox-controls">{shotTypeControl}</div>
      </div>
    )
  } else if (hole !== null) {
    holeStage = (
      <div className="live-sandbox-hole">
        <p className="live-sandbox-nomap">此洞暂无几何图,直接输入到果岭距离。</p>
        <div className="live-sandbox-controls">
          <label className="live-sandbox-control">
            <span>到果岭(m)</span>
            <input
              type="number"
              aria-label="到果岭(m)"
              min={0}
              inputMode="decimal"
              placeholder="如 135"
              value={manualToGreen}
              onChange={(event) => setManualToGreen(event.target.value)}
            />
          </label>
          {shotTypeControl}
        </div>
      </div>
    )
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
        <section className="panel live-sandbox-stage">
          <div className="live-hole-chips" aria-label="选洞">
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
        </section>
      )}
    </>
  )
}
