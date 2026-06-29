import { useCallback, useEffect, useState } from 'react'
import { fetchAdminPlayers, fetchPlayerClubBag, putPlayerClubBag } from '../api'
import type { AdminPlayer, ClubBagUpdateEntry, EffectiveClubBagResponse } from '../types'
import { CLUB_CATEGORIES, METRES_PER_YARD, catalogByCategory } from '../clubCatalog'

// Owner-only club-bag editor (settings → 球包管理). The OWNER (admin token) sets up any family
// member's MANUAL bag: pick the clubs they really carry from the catalog + optionally enter each
// club's typical distance (yards). It mirrors the iOS slice and the backend acts-for-any rule
// (GET/PUT /api/v2/players/{id}/clubs/bag); no-distance clubs stay blank so the caddie uses its
// generic fallback ladder. The page never shows anyone's scores — only their bag selection.

export function ClubBagPage({ adminToken }: { adminToken?: string }) {
  const token = adminToken?.trim()
  const [players, setPlayers] = useState<AdminPlayer[]>([])
  const [playerId, setPlayerId] = useState('me')
  const [selected, setSelected] = useState<Set<string>>(new Set()) // tokens
  const [distYd, setDistYd] = useState<Record<string, number>>({}) // token -> yards
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [saveMsg, setSaveMsg] = useState<string>('')

  const applyBag = useCallback((bag: EffectiveClubBagResponse) => {
    setSelected(new Set(bag.clubs.map((c) => c.token)))
    const d: Record<string, number> = {}
    for (const c of bag.clubs) if (c.distanceM != null) d[c.token] = Math.round(c.distanceM / METRES_PER_YARD)
    setDistYd(d)
  }, [])

  const loadBag = useCallback(
    async (pid: string) => {
      if (!token) return
      setStatus('loading')
      try {
        applyBag(await fetchPlayerClubBag(pid, token))
        setStatus('ready')
      } catch {
        setStatus('error')
      }
    },
    [token, applyBag],
  )

  useEffect(() => {
    if (!token) return
    fetchAdminPlayers(token)
      .then((r) => setPlayers(r.players))
      .catch(() => {})
    void loadBag('me')
  }, [token, loadBag])

  const onPickPlayer = (pid: string) => {
    setPlayerId(pid)
    setSaveMsg('')
    void loadBag(pid)
  }

  const toggle = (tok: string) =>
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(tok)) n.delete(tok)
      else n.add(tok)
      return n
    })

  const setYards = (tok: string, raw: string) => {
    const v = parseInt(raw.replace(/[^0-9]/g, ''), 10)
    setDistYd((d) => {
      const n = { ...d }
      if (v > 0) n[tok] = v
      else delete n[tok]
      return n
    })
  }

  const save = async () => {
    if (!token) return
    const clubs: ClubBagUpdateEntry[] = [...selected].map((tok) => ({
      token: tok,
      distanceM: distYd[tok] != null ? Math.round(distYd[tok] * METRES_PER_YARD) : null,
    }))
    setSaveMsg('保存中…')
    try {
      applyBag(await putPlayerClubBag(playerId, { clubs }, token))
      setSaveMsg('已保存到云端')
    } catch {
      setSaveMsg('保存失败')
    }
  }

  if (!token) {
    return (
      <section className="stats-page">
        <div className="panel empty-state">需要管理员令牌(在「同步与数据健康」里登录)。</div>
      </section>
    )
  }

  return (
    <section className="stats-page" aria-label="球包管理工作区">
      <header className="section-head stats-head">
        <div>
          <p className="eyebrow">设置</p>
          <h1>球包管理</h1>
        </div>
      </header>
      <div className="panel">
        <label>
          球员:&nbsp;
          <select value={playerId} onChange={(e) => onPickPlayer(e.target.value)}>
            {players.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.isOwner ? '(本人)' : ''}
              </option>
            ))}
          </select>
        </label>
        <p className="eyebrow">勾选该球员真实有的球杆,可填每支的常用距离(码)。没填的杆球童用通用兜底。</p>
      </div>
      {status === 'loading' ? <div className="panel empty-state">加载中…</div> : null}
      {status === 'error' ? <div className="panel empty-state">加载失败。</div> : null}
      {status === 'ready'
        ? CLUB_CATEGORIES.map((cat) => (
            <div className="panel" key={cat}>
              <p className="eyebrow">{cat}</p>
              {catalogByCategory(cat).map((club) => {
                const on = selected.has(club.token)
                return (
                  <div key={club.token} className="club-row">
                    <label>
                      <input type="checkbox" checked={on} onChange={() => toggle(club.token)} /> {club.zhName}
                    </label>
                    {on ? (
                      <span className="club-row-dist">
                        <input
                          inputMode="numeric"
                          aria-label={`${club.zhName} 常用距离(码)`}
                          value={distYd[club.token]?.toString() ?? ''}
                          onChange={(e) => setYards(club.token, e.target.value)}
                          placeholder="—"
                        />{' '}
                        码
                      </span>
                    ) : null}
                  </div>
                )
              })}
            </div>
          ))
        : null}
      <div className="panel">
        <button className="sync-action" type="button" onClick={() => void save()} disabled={status !== 'ready'}>
          保存到云端
        </button>
        {saveMsg ? <span className="sync-session-state">&nbsp;{saveMsg}</span> : null}
      </div>
    </section>
  )
}
