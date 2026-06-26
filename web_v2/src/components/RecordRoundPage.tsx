import { useMemo, useState } from 'react'
import type { MobileCourseOptionsResponse, RoundIngestEvent, RoundIngestRequestBody, RoundIngestResult } from '../types'

interface RecordRoundPageProps {
  playerId: string
  playerName?: string | null
  courseOptions: MobileCourseOptionsResponse | null
  // Injected so the page is testable without the real fetch/auth stack.
  onIngest: (playerId: string, body: RoundIngestRequestBody) => Promise<RoundIngestResult>
  // Optional geolocation override (tests pass a stub); defaults to the browser API.
  getPosition?: () => Promise<{ latitude: number; longitude: number; accuracy: number | null }>
  onExit: () => void
}

interface RecordedShot {
  club: string
  latitude: number
  longitude: number
  accuracy: number | null
}

interface HoleRecord {
  strokes: string
  putts: string
  shots: RecordedShot[]
}

const CLUBS = ['1W', '3W', '5W', '3H', '4i', '5i', '6i', '7i', '8i', '9i', 'PW', 'GW', 'SW', 'LW', '推杆']

function browserGetPosition(): Promise<{ latitude: number; longitude: number; accuracy: number | null }> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
      reject(new Error('此设备或浏览器不支持定位'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: Number.isFinite(pos.coords.accuracy) ? pos.coords.accuracy : null,
        }),
      (err) => reject(new Error(err.code === err.PERMISSION_DENIED ? '定位权限被拒绝,请在浏览器允许定位' : '定位失败,请到空旷处重试')),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    )
  })
}

function emptyHole(): HoleRecord {
  return { strokes: '', putts: '', shots: [] }
}

function buildEvents(holes: Record<number, HoleRecord>): RoundIngestEvent[] {
  const events: RoundIngestEvent[] = []
  for (const hole of Object.keys(holes).map(Number).sort((a, b) => a - b)) {
    const rec = holes[hole]
    for (const shot of rec.shots) {
      events.push({ hole, kind: 'club', payload: { clubName: shot.club, source: 'web' } })
      events.push({
        hole,
        kind: 'location',
        payload: {
          latitude: shot.latitude,
          longitude: shot.longitude,
          ...(shot.accuracy !== null ? { horizontalAccuracyM: shot.accuracy } : {}),
          source: 'web',
        },
      })
    }
    const strokes = Number.parseInt(rec.strokes, 10)
    if (Number.isFinite(strokes) && strokes >= 1) events.push({ hole, kind: 'score', payload: { strokes } })
    const putts = Number.parseInt(rec.putts, 10)
    if (Number.isFinite(putts) && putts >= 0) events.push({ hole, kind: 'putt', payload: { putts } })
  }
  return events
}

function freshClientRoundId(): string {
  // Unique per round (so two real rounds with the same shot/hole counts never
  // collide on the server's idempotency key and get merged) yet stable across
  // re-submits of the same round (so a retry dedupes instead of duplicating).
  const rand =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`
  return `web-${rand}`
}

export function RecordRoundPage({ playerId, playerName, courseOptions, onIngest, getPosition, onExit }: RecordRoundPageProps) {
  const [phase, setPhase] = useState<'setup' | 'recording' | 'done'>('setup')
  const [courseName, setCourseName] = useState('')
  const [courseGlobalId, setCourseGlobalId] = useState<number | null>(null)
  const [holes, setHoles] = useState<Record<number, HoleRecord>>({ 1: emptyHole() })
  const [currentHole, setCurrentHole] = useState(1)
  const [club, setClub] = useState('1W')
  const [locating, setLocating] = useState(false)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<RoundIngestResult | null>(null)
  const [clientRoundId, setClientRoundId] = useState(freshClientRoundId)

  const locate = getPosition ?? browserGetPosition
  const courses = courseOptions?.courses ?? []
  const hole = holes[currentHole] ?? emptyHole()
  const totalShots = useMemo(() => Object.values(holes).reduce((sum, h) => sum + h.shots.length, 0), [holes])
  const scoredHoles = useMemo(() => Object.values(holes).filter((h) => h.shots.length > 0 || h.strokes.trim()).length, [holes])

  function updateHole(patch: Partial<HoleRecord>) {
    setHoles((prev) => ({ ...prev, [currentHole]: { ...(prev[currentHole] ?? emptyHole()), ...patch } }))
  }

  async function recordShot() {
    setErrorMsg(null)
    setStatusMsg(null)
    setLocating(true)
    try {
      const pos = await locate()
      const shot: RecordedShot = { club, latitude: pos.latitude, longitude: pos.longitude, accuracy: pos.accuracy }
      setHoles((prev) => {
        const rec = prev[currentHole] ?? emptyHole()
        return { ...prev, [currentHole]: { ...rec, shots: [...rec.shots, shot] } }
      })
      setStatusMsg(pos.accuracy !== null ? `已记录第 ${hole.shots.length + 1} 杆 · 精度 ±${Math.round(pos.accuracy)}m` : `已记录第 ${hole.shots.length + 1} 杆`)
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '定位失败')
    } finally {
      setLocating(false)
    }
  }

  function goToHole(next: number) {
    if (next < 1) return
    setStatusMsg(null)
    setErrorMsg(null)
    setHoles((prev) => (prev[next] ? prev : { ...prev, [next]: emptyHole() }))
    setCurrentHole(next)
  }

  async function submitRound() {
    setErrorMsg(null)
    const events = buildEvents(holes)
    if (events.length === 0) {
      setErrorMsg('还没有记录任何一杆或成绩')
      return
    }
    setSubmitting(true)
    try {
      const meta: Record<string, unknown> = {
        courseName: courseName.trim() || '手机记分',
        holesCompleted: scoredHoles,
      }
      if (courseGlobalId !== null) meta.courseGlobalId = courseGlobalId
      const body: RoundIngestRequestBody = { events, meta, clientRoundId }
      const res = await onIngest(playerId, body)
      setResult(res)
      setPhase('done')
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '提交失败,请重试')
    } finally {
      setSubmitting(false)
    }
  }

  if (phase === 'done' && result) {
    return (
      <section className="record-page" aria-label="记分完成">
        <section className="panel record-done">
          <h1>已提交 ✅</h1>
          <p>
            {(result.course ?? courseName) || '本场'} · {result.holesCompleted ?? scoredHoles} 洞
            {result.strokes != null ? ` · ${result.strokes} 杆` : ''} · {result.shotCount ?? totalShots} 杆位置
          </p>
          <p className="record-hint">{result.idempotent ? '这场之前已提交过(未重复创建)。' : '已存入你的球局,稍后可在 历史 · 球局 查看。'}</p>
          <button type="button" onClick={onExit}>
            返回
          </button>
        </section>
      </section>
    )
  }

  if (phase === 'setup') {
    return (
      <section className="record-page" aria-label="开始记分">
        <header className="overview-hero">
          <p className="eyebrow">手机记分</p>
          <h1>记一场球(GPS)</h1>
          <p className="lead">边打边记:每一杆点一下定位,自动记录球位坐标。{playerName ? `当前球员:${playerName}。` : ''}</p>
        </header>
        <section className="panel record-setup">
          <label className="record-field">
            球场名称
            <input
              type="text"
              value={courseName}
              placeholder="如:北京丽宫"
              onChange={(e) => setCourseName(e.target.value)}
              aria-label="球场名称"
            />
          </label>
          {courses.length > 0 ? (
            <label className="record-field">
              或从常打球场选
              <select
                aria-label="常打球场"
                value={courseGlobalId ?? ''}
                onChange={(e) => {
                  const gid = e.target.value ? Number(e.target.value) : null
                  setCourseGlobalId(gid)
                  const picked = courses.find((c) => c.globalId === gid)
                  if (picked) setCourseName(picked.name)
                }}
              >
                <option value="">不指定</option>
                {courses.map((c) => (
                  <option key={c.globalId} value={c.globalId}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <div className="record-actions">
            <button type="button" className="record-primary" onClick={() => { setClientRoundId(freshClientRoundId()); setPhase('recording') }}>
              开始记分
            </button>
            <button type="button" onClick={onExit}>
              取消
            </button>
          </div>
        </section>
      </section>
    )
  }

  return (
    <section className="record-page" aria-label="记分中">
      <header className="overview-hero record-hole-head">
        <div>
          <p className="eyebrow">{courseName.trim() || '手机记分'}</p>
          <h1>第 {currentHole} 洞</h1>
          <p className="lead">本洞已记 {hole.shots.length} 杆 · 全场 {totalShots} 杆位置 / {scoredHoles} 洞</p>
        </div>
      </header>

      <section className="panel record-capture">
        <label className="record-field">
          球杆
          <select aria-label="球杆" value={club} onChange={(e) => setClub(e.target.value)}>
            {CLUBS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="record-primary record-locate" disabled={locating} onClick={() => void recordShot()}>
          {locating ? '定位中…' : '📍 记一杆'}
        </button>
        {statusMsg ? <p className="record-status" role="status">{statusMsg}</p> : null}
        {errorMsg ? <p className="record-error" role="alert">{errorMsg}</p> : null}

        {hole.shots.length > 0 ? (
          <ol className="record-shot-list" aria-label="本洞击球">
            {hole.shots.map((s, i) => (
              <li key={i}>
                第{i + 1}杆 · {s.club} · {s.accuracy !== null ? `±${Math.round(s.accuracy)}m` : '已记录'}
              </li>
            ))}
          </ol>
        ) : null}
      </section>

      <section className="panel record-score">
        <label className="record-field">
          本洞杆数
          <input type="number" inputMode="numeric" min={1} value={hole.strokes} onChange={(e) => updateHole({ strokes: e.target.value })} aria-label="本洞杆数" />
        </label>
        <label className="record-field">
          推杆数
          <input type="number" inputMode="numeric" min={0} value={hole.putts} onChange={(e) => updateHole({ putts: e.target.value })} aria-label="推杆数" />
        </label>
      </section>

      <div className="record-actions record-hole-nav">
        <button type="button" disabled={currentHole <= 1} onClick={() => goToHole(currentHole - 1)}>
          上一洞
        </button>
        <button type="button" onClick={() => goToHole(currentHole + 1)}>
          下一洞 →
        </button>
      </div>

      <div className="record-actions">
        <button type="button" className="record-primary" disabled={submitting} onClick={() => void submitRound()}>
          {submitting ? '提交中…' : '结束并提交'}
        </button>
        <button type="button" onClick={onExit}>
          退出(不保存)
        </button>
      </div>
    </section>
  )
}
