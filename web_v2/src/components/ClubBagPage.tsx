import { useCallback, useEffect, useState } from 'react'
import { fetchAdminPlayers, fetchPlayerClubBag, putPlayerClubBag } from '../api'
import type { AdminPlayer, ClubBagUpdateEntry, EffectiveClubBagResponse } from '../types'
import { CLUB_CATEGORIES, METRES_PER_YARD, catalogByCategory } from '../clubCatalog'

// Club-bag editor (settings → 球包管理). Every signed-in user edits THEIR OWN bag:
// pick the clubs they really carry from the catalog + optionally enter each club's
// typical distance (yards). A member authorizes with their Apple session bearer; the
// OWNER additionally gets a picker to set up any family member's bag (the admin token
// acts-for-any, GET/PUT /api/v2/players/{id}/clubs/bag). No-distance clubs stay blank
// so the caddie uses its generic fallback ladder. The page never shows anyone's scores.

export function ClubBagPage({
  adminToken,
  isOwner = true,
  selfPlayerId = 'me',
}: {
  adminToken?: string
  isOwner?: boolean
  selfPlayerId?: string
}) {
  // The OWNER acts-for-any family member via the admin token (member picker). A
  // signed-in member edits only THEIR OWN bag via their session bearer — no admin
  // token, no picker, no 需要管理员令牌 gate.
  const token = adminToken?.trim()
  const apiToken = isOwner ? token : undefined
  const initialPlayerId = isOwner ? 'me' : selfPlayerId
  const [players, setPlayers] = useState<AdminPlayer[]>([])
  const [playerId, setPlayerId] = useState(initialPlayerId)
  const [selected, setSelected] = useState<Set<string>>(new Set()) // tokens
  const [distYd, setDistYd] = useState<Record<string, number>>({}) // token -> yards
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('loading')
  const [saveMsg, setSaveMsg] = useState<string>('')

  const applyBag = useCallback((bag: EffectiveClubBagResponse) => {
    setSelected(new Set(bag.clubs.map((c) => c.token)))
    const d: Record<string, number> = {}
    for (const c of bag.clubs) if (c.distanceM != null) d[c.token] = Math.round(c.distanceM / METRES_PER_YARD)
    setDistYd(d)
  }, [])

  const loadBag = useCallback(
    async (pid: string) => {
      setStatus('loading')
      try {
        applyBag(await fetchPlayerClubBag(pid, apiToken))
        setStatus('ready')
      } catch {
        setStatus('error')
      }
    },
    [apiToken, applyBag],
  )

  useEffect(() => {
    let cancelled = false
    // Owner-only: the family member picker (acts-for-any via the admin token).
    if (isOwner && token) {
      fetchAdminPlayers(token)
        .then((r) => {
          if (!cancelled) setPlayers(r.players)
        })
        .catch(() => {})
    }
    // Fetch the active bag inline (not via loadBag) so every setState runs in the async
    // continuation, never synchronously in the effect body (react-hooks/set-state-in-effect).
    fetchPlayerClubBag(initialPlayerId, apiToken)
      .then((bag) => {
        if (!cancelled) {
          applyBag(bag)
          setStatus('ready')
        }
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [isOwner, token, apiToken, initialPlayerId, applyBag])

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
    const clubs: ClubBagUpdateEntry[] = [...selected].map((tok) => ({
      token: tok,
      distanceM: distYd[tok] != null ? Math.round(distYd[tok] * METRES_PER_YARD) : null,
    }))
    setSaveMsg('保存中…')
    try {
      applyBag(await putPlayerClubBag(playerId, { clubs }, apiToken))
      setSaveMsg('已保存到云端')
    } catch {
      setSaveMsg('保存失败')
    }
  }

  return (
    <section className="stats-page" aria-label="球包管理工作区">
      <header className="section-head stats-head">
        <div>
          <p className="eyebrow">设置</p>
          <h1>球包管理</h1>
        </div>
      </header>
      {isOwner ? (
        <div className="panel">
          <label>
            球员:&nbsp;
            <select value={playerId} onChange={(e) => onPickPlayer(e.target.value)}>
              {players.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <p className="eyebrow">勾选该球员真实有的球杆,可填每支的常用距离(码)。没填的杆球童用通用兜底。</p>
        </div>
      ) : (
        <div className="panel">
          <p className="eyebrow">勾选你真实有的球杆,可填每支的常用距离(码)。没填的杆球童用通用兜底。</p>
        </div>
      )}
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
