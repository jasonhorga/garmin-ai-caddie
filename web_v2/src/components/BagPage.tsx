import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchPlayerClubBag, putPlayerClubBag } from '../api'
import { METRES_PER_YARD } from '../clubCatalog'
import { normalizeMeasuredClubToken, shortClubLabel, tokenRank } from '../clubProfile'
import type { ProductPage } from '../navigation'
import type { ClubBagUpdateEntry, EffectiveClubBagResponse } from '../types'
import { yards } from '../units'
import { confidenceZh } from '../zhLabels'
import { asNumber, asRows, asString, type StatRow } from './statsValues'

// 球包 (bag) page — the club-distance gapping workbench. It joins TWO real sources:
//   • the effective club bag (roster + editable carry distance, keyed by canonical
//     token; the SAME profile iOS uses) — authoritative + editable, and
//   • the measured per-club stats from your shot records (median/P10–P90/sample,
//     keyed by Garmin short codes) — used only to ENRICH each club's dispersion band.
// Nothing is invented: a club with no manual/synced distance shows its measured
// median (source 实测); a club with no measured samples shows 数据不足 for the band /
// sample columns. Total distance & 左右偏差 aren't in either payload, so those
// mockup columns are omitted rather than faked.

interface Measured {
  medianM: number | null
  p10M: number | null
  p90M: number | null
  sampleCount: number | null
  confidence: string | null
}

interface BagClub {
  token: string
  zhName: string
  shortLabel: string
  distanceM: number | null // the bag's editable carry (metres), or null if unset
  carryYd: number | null // effective carry: bag distance, else measured median
  source: 'manual' | 'default' | 'garmin' | 'record' | 'none'
  measured: Measured | null
}

const SOURCE_LABEL: Record<BagClub['source'], string> = {
  manual: '手动',
  default: '默认',
  garmin: '同步',
  record: '实测',
  none: '未设',
}

function buildMeasured(rows: StatRow[]): Map<string, Measured> {
  const map = new Map<string, Measured>()
  for (const row of rows) {
    const token = normalizeMeasuredClubToken(asString(row.club))
    if (!token || map.has(token)) continue
    map.set(token, {
      medianM: asNumber(row.median),
      p10M: asNumber(row.p10),
      p90M: asNumber(row.p90),
      sampleCount: asNumber(row.sampleCount),
      confidence: asString(row.confidence),
    })
  }
  return map
}

function buildClubs(bag: EffectiveClubBagResponse | null, measured: Map<string, Measured>): BagClub[] {
  if (!bag || bag.clubs.length === 0) return []
  const clubs: BagClub[] = bag.clubs.map((c) => {
    const m = measured.get(c.token) ?? null
    const distanceM = c.distanceM
    const carryYd = distanceM != null ? yards(distanceM) : yards(m?.medianM)
    let source: BagClub['source'] = 'none'
    if (c.distanceSource === 'manual') source = 'manual'
    else if (c.distanceSource === 'default') source = 'default'
    else if (distanceM != null) source = bag.source === 'garmin' ? 'garmin' : 'manual'
    else if (m?.medianM != null) source = 'record'
    return {
      token: c.token,
      zhName: c.zhName ?? c.customName ?? shortClubLabel(c.token),
      shortLabel: shortClubLabel(c.token),
      distanceM,
      carryYd,
      source,
      measured: m,
    }
  })
  clubs.sort((a, b) => {
    if (a.carryYd == null && b.carryYd == null) return tokenRank(a.token) - tokenRank(b.token)
    if (a.carryYd == null) return 1
    if (b.carryYd == null) return -1
    if (b.carryYd !== a.carryYd) return b.carryYd - a.carryYd
    return tokenRank(a.token) - tokenRank(b.token)
  })
  return clubs
}

function firstToken(clubs: BagClub[]): string | null {
  return clubs.length > 0 ? clubs[0].token : null
}

// A club's 散布 range text, "198–210" (yards), or null when it has no measured band.
function bandText(m: Measured | null): string | null {
  if (!m) return null
  const lo = yards(m.p10M)
  const hi = yards(m.p90M)
  if (lo == null || hi == null) return null
  return `${lo}–${hi}`
}

interface BagPageProps {
  // Measured per-club stats from history_stats (data.clubs) — enrichment only.
  measuredClubs: StatRow[]
  adminToken?: string
  isOwner?: boolean
  selfPlayerId?: string
  onNavigate: (page: ProductPage) => void
}

// —— left detail: a longitudinal (distance) dispersion band. There is NO lateral /
// 左右 data in either payload, so we render an HONEST 1-D band (P10–median–P90 from
// records) with the club's set carry marked — not a fabricated 2-D落点 ellipse.
function DistanceBand({ club }: { club: BagClub }) {
  const m = club.measured
  const p10 = yards(m?.p10M)
  const p90 = yards(m?.p90M)
  const median = yards(m?.medianM)
  const carry = club.carryYd
  if (p10 == null || p90 == null) {
    return (
      <div className="bagx-band bagx-band--empty" aria-label="落点距离散布">
        {carry != null ? <span className="bagx-band-carry-only">{carry} 码</span> : null}
        <span className="bagx-band-note">实测样本不足,暂无散布</span>
      </div>
    )
  }
  const lo = Math.min(p10, carry ?? p10) - 6
  const hi = Math.max(p90, carry ?? p90) + 6
  const span = hi - lo || 1
  const pct = (v: number) => ((v - lo) / span) * 100
  return (
    <svg className="bagx-band" viewBox="0 0 240 74" role="img" aria-label="落点距离散布">
      <rect x="0" y="0" width="240" height="74" rx="8" className="bagx-band-bg" />
      <text x="10" y="18" className="bagx-band-cap">落点距离散布 · 实测(码)</text>
      <line x1="12" y1="48" x2="228" y2="48" className="bagx-band-axis" />
      <rect x={12 + (pct(p10) / 100) * 216} y="40" width={((pct(p90) - pct(p10)) / 100) * 216} height="16" rx="4" className="bagx-band-rng" />
      {median != null ? <line x1={12 + (pct(median) / 100) * 216} y1="36" x2={12 + (pct(median) / 100) * 216} y2="60" className="bagx-band-median" /> : null}
      {carry != null ? <line x1={12 + (pct(carry) / 100) * 216} y1="34" x2={12 + (pct(carry) / 100) * 216} y2="62" className="bagx-band-carry" /> : null}
      <text x={12 + (pct(p10) / 100) * 216} y="70" className="bagx-band-tick" textAnchor="middle">{p10}</text>
      <text x={12 + (pct(p90) / 100) * 216} y="70" className="bagx-band-tick" textAnchor="middle">{p90}</text>
    </svg>
  )
}

export function BagPage({ measuredClubs, adminToken, isOwner = true, selfPlayerId = 'me', onNavigate }: BagPageProps) {
  const token = adminToken?.trim()
  const apiToken = isOwner ? token : undefined
  const playerId = isOwner ? 'me' : selfPlayerId

  const [bag, setBag] = useState<EffectiveClubBagResponse | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [selectedToken, setSelectedToken] = useState<string | null>(null)
  // null = the field mirrors the selected club's carry; a string = an unsaved edit.
  const [editYd, setEditYd] = useState<string | null>(null)
  const [saveMsg, setSaveMsg] = useState('')
  const [saving, setSaving] = useState(false)

  const measured = useMemo(() => buildMeasured(asRows(measuredClubs)), [measuredClubs])
  const clubs = useMemo(() => buildClubs(bag, measured), [bag, measured])

  const applyBag = useCallback((resp: EffectiveClubBagResponse, built: BagClub[]) => {
    setBag(resp)
    setSelectedToken((prev) => prev ?? firstToken(built))
  }, [])

  useEffect(() => {
    // status stays at its 'loading' default; every setState runs in the async
    // continuation below (never synchronously in the effect body — see
    // react-hooks/set-state-in-effect).
    let cancelled = false
    fetchPlayerClubBag(playerId, apiToken)
      .then((resp) => {
        if (cancelled) return
        applyBag(resp, buildClubs(resp, measured))
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [playerId, apiToken, measured, applyBag])

  const selected = clubs.find((c) => c.token === selectedToken) ?? clubs[0] ?? null
  // The field shows an unsaved edit if present, else mirrors the selected carry.
  const fieldValue = editYd ?? (selected?.carryYd != null ? String(selected.carryYd) : '')

  const select = (tok: string) => {
    setSelectedToken(tok)
    setSaveMsg('')
    setEditYd(null)
  }

  const persist = async (entries: ClubBagUpdateEntry[], okMsg: string) => {
    setSaving(true)
    setSaveMsg('保存中…')
    try {
      const resp = await putPlayerClubBag(playerId, { clubs: entries }, apiToken)
      applyBag(resp, buildClubs(resp, measured))
      setEditYd(null)
      setSaveMsg(okMsg)
    } catch {
      setSaveMsg('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const save = () => {
    if (!bag || !selected) return
    const yd = parseInt(fieldValue.replace(/[^0-9]/g, ''), 10)
    const entries: ClubBagUpdateEntry[] = bag.clubs.map((c) => ({
      token: c.token,
      customName: c.customName ?? undefined,
      distanceM: c.token === selected.token ? (yd > 0 ? Math.round(yd * METRES_PER_YARD) : null) : c.distanceM,
    }))
    void persist(entries, '已保存到云端')
  }

  // 从记录重算: push each club's measured median (from your shot records) into the
  // bag as its carry distance. Only clubs WITH a measured median change; the rest
  // keep whatever they had. Nothing is invented — it copies real recorded medians.
  const recompute = () => {
    if (!bag) return
    let changed = 0
    const entries: ClubBagUpdateEntry[] = bag.clubs.map((c) => {
      const medianM = measured.get(c.token)?.medianM
      if (medianM != null) {
        changed += 1
        return { token: c.token, customName: c.customName ?? undefined, distanceM: Math.round(medianM) }
      }
      return { token: c.token, customName: c.customName ?? undefined, distanceM: c.distanceM }
    })
    if (changed === 0) {
      setSaveMsg('没有可用于重算的击球记录')
      return
    }
    void persist(entries, `已按记录重算 ${changed} 支球杆`)
  }

  const clubCount = clubs.length

  // —— ladder geometry: a shared yardage axis across every club with a carry ——
  const axisValues: number[] = []
  for (const c of clubs) {
    if (c.carryYd != null) axisValues.push(c.carryYd)
    const lo = yards(c.measured?.p10M)
    const hi = yards(c.measured?.p90M)
    if (lo != null) axisValues.push(lo)
    if (hi != null) axisValues.push(hi)
  }
  const hasAxis = axisValues.length > 0
  const rawLo = hasAxis ? Math.min(...axisValues) : 0
  const rawHi = hasAxis ? Math.max(...axisValues) : 0
  const pad = Math.max(12, Math.round((rawHi - rawLo) * 0.08))
  const axisMin = Math.max(0, Math.floor((rawLo - pad) / 10) * 10)
  const axisMax = Math.ceil((rawHi + pad) / 10) * 10
  const axisSpan = axisMax - axisMin || 1
  const pct = (yd: number) => ((yd - axisMin) / axisSpan) * 100
  const clampPct = (yd: number) => Math.max(5, Math.min(95, pct(yd)))
  const ticks = Array.from({ length: 5 }, (_, i) => Math.round(axisMin + (axisSpan * i) / 4))

  // Gap annotations: flag a notably large distance jump to the club above.
  const carriesDesc = clubs.filter((c) => c.carryYd != null)
  const gaps: number[] = []
  for (let i = 1; i < carriesDesc.length; i += 1) {
    gaps.push((carriesDesc[i - 1].carryYd as number) - (carriesDesc[i].carryYd as number))
  }
  const medianGap = gaps.length ? [...gaps].sort((a, b) => a - b)[Math.floor(gaps.length / 2)] : 0
  const gapThreshold = Math.max(18, Math.round(medianGap * 1.6))
  const gapByToken = new Map<string, number>()
  for (let i = 1; i < carriesDesc.length; i += 1) {
    const gap = (carriesDesc[i - 1].carryYd as number) - (carriesDesc[i].carryYd as number)
    if (gap >= gapThreshold) gapByToken.set(carriesDesc[i].token, gap)
  }
  const biggestGap = gaps.length ? Math.max(...gaps) : 0
  const biggestGapIndex = gaps.indexOf(biggestGap)
  const ladderNote =
    carriesDesc.length >= 2 && biggestGapIndex >= 0
      ? `最大距离空档约 ${biggestGap} 码,在 ${carriesDesc[biggestGapIndex].shortLabel} 与 ${carriesDesc[biggestGapIndex + 1].shortLabel} 之间。`
      : '继续记录击球,阶梯与散布会越来越准。'

  if (status === 'loading') {
    return (
      <section className="bagx" aria-label="球包">
        <BagHeader clubCount={0} onRecompute={recompute} onAdd={() => onNavigate('club-bag')} disabled />
        <div className="panel bagx-panel bagx-empty-panel">加载中…</div>
      </section>
    )
  }

  if (status === 'error') {
    return (
      <section className="bagx" aria-label="球包">
        <BagHeader clubCount={0} onRecompute={recompute} onAdd={() => onNavigate('club-bag')} disabled />
        <div className="panel bagx-panel bagx-empty-panel">
          <p>暂时读不到你的球包。</p>
          <button type="button" className="prep-topbtn" onClick={() => onNavigate('club-bag')}>
            去球包管理
          </button>
        </div>
      </section>
    )
  }

  if (clubCount === 0) {
    return (
      <section className="bagx" aria-label="球包">
        <BagHeader clubCount={0} onRecompute={recompute} onAdd={() => onNavigate('club-bag')} disabled />
        <div className="panel bagx-panel bagx-empty-panel bagx-onboard">
          <h2>你的球包还没有球杆</h2>
          <p>先到「球包管理」勾选你真实带的球杆,填上常用距离,或多打几场让我们从记录里学到你的距离。</p>
          <button type="button" className="prep-topbtn primary" onClick={() => onNavigate('club-bag')}>
            + 添加球杆
          </button>
        </div>
      </section>
    )
  }

  return (
    <section className="bagx" aria-label="球包">
      <BagHeader clubCount={clubCount} onRecompute={recompute} onAdd={() => onNavigate('club-bag')} disabled={saving} />

      <div className="bagx-grid">
        {/* —— gapping ladder —— */}
        <section className="panel bagx-panel bagx-ladder" aria-label="距离阶梯">
          <h2 className="statsx-h">
            距离阶梯 Gapping<small>你的 carry(码)· 浅条 = 实测 P10–P90 散布</small>
          </h2>
          <div className="bagx-axis" aria-hidden="true">
            {ticks.map((t, i) => (
              <span key={t}>{i === ticks.length - 1 ? `${t} 码` : t}</span>
            ))}
          </div>
          <div className="bagx-rows">
            {clubs.map((club) => {
              const isSel = club.token === selected?.token
              const lo = yards(club.measured?.p10M)
              const hi = yards(club.measured?.p90M)
              const hasBand = lo != null && hi != null
              const gap = gapByToken.get(club.token)
              return (
                <button
                  key={club.token}
                  type="button"
                  className={isSel ? 'bagx-grow bagx-grow--sel' : 'bagx-grow'}
                  aria-pressed={isSel}
                  aria-label={`${club.zhName} 距离条`}
                  onClick={() => select(club.token)}
                >
                  <span className="bagx-cl">{club.shortLabel}</span>
                  <span className="bagx-track">
                    {gap != null && club.carryYd != null ? (
                      <span className="bagx-gaptag" style={{ left: `${clampPct(club.carryYd)}%` }}>
                        ↕ {gap} 空档
                      </span>
                    ) : null}
                    {club.carryYd == null ? (
                      <span className="bagx-nodata">数据不足</span>
                    ) : (
                      <>
                        {hasBand ? (
                          <span
                            className="bagx-rng"
                            style={{ left: `${pct(lo as number)}%`, width: `${Math.max(1.5, pct(hi as number) - pct(lo as number))}%` }}
                          />
                        ) : null}
                        <span className="bagx-carry" style={{ left: `${pct(club.carryYd)}%` }} />
                      </>
                    )}
                  </span>
                  <span className="bagx-val">{club.carryYd ?? '—'}</span>
                </button>
              )
            })}
          </div>
          <p className="statsx-note">{ladderNote}</p>
        </section>

        {/* —— selected-club detail —— */}
        <section className="panel bagx-panel bagx-detail" aria-label="球杆详情">
          {selected ? (
            <>
              <h2 className="statsx-h">
                {selected.zhName}
                <small>{selected.shortLabel} · 选中 · 可编辑</small>
              </h2>
              <DistanceBand club={selected} />
              <div className="bagx-kv">
                <span className="bagx-k">Carry P50</span>
                <span className="bagx-v">{selected.carryYd != null ? `${selected.carryYd} 码` : '数据不足'}</span>
              </div>
              <div className="bagx-kv">
                <span className="bagx-k">散布 P10–P90</span>
                <span className="bagx-v">{bandText(selected.measured) ?? '数据不足'}</span>
              </div>
              <div className="bagx-kv">
                <span className="bagx-k">样本</span>
                <span className="bagx-v">
                  {selected.measured?.sampleCount != null ? `${selected.measured.sampleCount} 次击球` : '数据不足'}
                </span>
              </div>
              <div className="bagx-kv">
                <span className="bagx-k">距离来源</span>
                <span className="bagx-v">{SOURCE_LABEL[selected.source]}</span>
              </div>
              {selected.measured?.confidence ? (
                <div className="bagx-kv">
                  <span className="bagx-k">置信度</span>
                  <span className="bagx-v">{confidenceZh(selected.measured.confidence)}</span>
                </div>
              ) : null}
              <div className="bagx-field">
                <span className="bagx-field-k">手动改(码)</span>
                <input
                  className="bagx-field-input"
                  inputMode="numeric"
                  aria-label={`${selected.zhName} 手动距离(码)`}
                  value={fieldValue}
                  placeholder="—"
                  onChange={(e) => {
                    setEditYd(e.target.value)
                    setSaveMsg('')
                  }}
                />
                <button type="button" className="bagx-save" onClick={save} disabled={saving}>
                  保存
                </button>
              </div>
              {(() => {
                const medianYd = yards(selected.measured?.medianM)
                return medianYd != null ? (
                  <button
                    type="button"
                    className="bagx-record-btn"
                    onClick={() => {
                      setEditYd(String(medianYd))
                      setSaveMsg('')
                    }}
                  >
                    用记录值 {medianYd} 码
                  </button>
                ) : null
              })()}
              {saveMsg ? <p className="bagx-savemsg">{saveMsg}</p> : null}
            </>
          ) : null}
        </section>

        {/* —— full editable table —— */}
        <section className="panel bagx-panel bagx-table-wrap" aria-label="全部球杆">
          <h2 className="statsx-h">
            全部球杆<small>与 iOS 同一份 club profile · 只显示你真实有的杆</small>
          </h2>
          <div className="bagx-table-scroll">
            <table className="statsx-table bagx-table">
              <thead>
                <tr>
                  <th>球杆</th>
                  <th className="statsx-num">Carry P50</th>
                  <th className="statsx-num">P10–P90</th>
                  <th className="statsx-num">样本</th>
                  <th>来源</th>
                  <th aria-label="操作" />
                </tr>
              </thead>
              <tbody>
                {clubs.map((club) => (
                  <tr key={club.token} className={club.token === selected?.token ? 'bagx-row-sel' : undefined}>
                    <td>{club.zhName}</td>
                    <td className="statsx-num">{club.carryYd ?? '—'}</td>
                    <td className="statsx-num">{bandText(club.measured) ?? '数据不足'}</td>
                    <td className="statsx-num">{club.measured?.sampleCount ?? '—'}</td>
                    <td>{SOURCE_LABEL[club.source]}</td>
                    <td>
                      <button type="button" className="bagx-edit" onClick={() => select(club.token)}>
                        编辑
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </section>
  )
}

// The AppShell top-bar already titles the page 球包; this page toolbar carries the
// club-count crumb + the two page actions (no duplicate page title).
function BagHeader({
  clubCount,
  onRecompute,
  onAdd,
  disabled,
}: {
  clubCount: number
  onRecompute: () => void
  onAdd: () => void
  disabled?: boolean
}) {
  return (
    <div className="bagx-toolbar">
      <p className="bagx-crumb">
        {clubCount > 0 ? `${clubCount} 支 · ` : ''}你的实测距离 · 与 iOS 同一份 club profile
      </p>
      <div className="bagx-actions">
        <button type="button" className="prep-topbtn" onClick={onRecompute} disabled={disabled}>
          从记录重算
        </button>
        <button type="button" className="prep-topbtn primary" onClick={onAdd}>
          + 添加球杆
        </button>
      </div>
    </div>
  )
}
