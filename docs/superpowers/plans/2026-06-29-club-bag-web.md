# Club-bag Manual Setup — Web Slice Implementation Plan

> **For agentic workers:** The web gates are LOCAL: `npm test -- --run` (vitest) + `npm run build` (tsc + vite) inside `web_v2/`. TDD the page test. The GitHub `frontend` CI job runs test+lint+build+playwright. No homeserver needed to develop/CI (deploy waits for it).

**Goal:** A new **club-bag editor** page in web Settings (owner-only) with a member picker, so the OWNER can set up any family member's bag (`GET`/`PUT /api/v2/players/{id}/clubs/bag`, owner acts-for-any via the admin token). Mirrors the iOS slice (select clubs from a catalog + optional per-club distance; no-distance clubs stay blank).

**Architecture:** Add a web `clubCatalog.ts` (mirrors the backend token vocabulary), TS types for the effective-bag contract, `putJson` + two API fns, a `'club-bag'` Settings sub-page gated owner-only, and a self-fetching `ClubBagPage` (member picker → grouped catalog with checkboxes + yards distance inputs → save).

**Tech Stack:** React + TypeScript + Vite, vitest + @testing-library/react.

---

## File Structure
- **Create** `web_v2/src/clubCatalog.ts` — `CLUB_CATALOG` (30 entries: token, zhName, category) + `CLUB_CATEGORIES` order + `catalogByCategory()`.
- **Modify** `web_v2/src/types.ts` — `ClubBagEntry`, `EffectiveClubBagResponse`, `ClubBagUpdateEntry`, `ClubBagUpdateRequest`.
- **Modify** `web_v2/src/api.ts` — `putJson<T>` (copy `patchJson`, method PUT) + `fetchPlayerClubBag(playerId, adminToken?)` + `putPlayerClubBag(playerId, body, adminToken?)`.
- **Modify** `web_v2/src/navigation.ts` — `'club-bag'` in `ProductPage`, `PAGE_TO_SECTION`, `SETTINGS_SUBNAV` (label '球包管理').
- **Modify** `web_v2/src/components/AppShell.tsx` — filter the `club-bag` subnav tab to owner-only (same condition as `players`).
- **Modify** `web_v2/src/App.tsx` — render branch `if (activePage === 'club-bag') return <ClubBagPage adminToken={currentAdminToken()} />`.
- **Create** `web_v2/src/components/ClubBagPage.tsx` — the editor.
- **Create** `web_v2/src/components/ClubBagPage.test.tsx` — vitest (mock api Pattern B).

---

## Task 1: Catalog (`clubCatalog.ts`)
```ts
export type ClubCategory = '木杆' | '混合杆' | '铁杆' | '挖起杆' | '推杆'
export interface CatalogClub { token: string; zhName: string; category: ClubCategory }

export const CLUB_CATEGORIES: ClubCategory[] = ['木杆', '混合杆', '铁杆', '挖起杆', '推杆']

// Tokens MUST match the backend club_catalog.py vocabulary (so PUTs aren't 422'd).
export const CLUB_CATALOG: CatalogClub[] = [
  { token: 'driver', zhName: '一号木', category: '木杆' },
  { token: 'wood3', zhName: '三号木', category: '木杆' },
  { token: 'wood5', zhName: '五号木', category: '木杆' },
  { token: 'wood7', zhName: '七号木', category: '木杆' },
  { token: 'hybrid1', zhName: '一号小鸡腿', category: '混合杆' },
  { token: 'hybrid2', zhName: '二号小鸡腿', category: '混合杆' },
  { token: 'hybrid3', zhName: '三号小鸡腿', category: '混合杆' },
  { token: 'hybrid4', zhName: '四号小鸡腿', category: '混合杆' },
  { token: 'hybrid5', zhName: '五号小鸡腿', category: '混合杆' },
  { token: 'hybrid6', zhName: '六号小鸡腿', category: '混合杆' },
  { token: 'iron1', zhName: '一号铁', category: '铁杆' },
  { token: 'iron2', zhName: '二号铁', category: '铁杆' },
  { token: 'iron3', zhName: '三号铁', category: '铁杆' },
  { token: 'iron4', zhName: '四号铁', category: '铁杆' },
  { token: 'iron5', zhName: '五号铁', category: '铁杆' },
  { token: 'iron6', zhName: '六号铁', category: '铁杆' },
  { token: 'iron7', zhName: '七号铁', category: '铁杆' },
  { token: 'iron8', zhName: '八号铁', category: '铁杆' },
  { token: 'iron9', zhName: '九号铁', category: '铁杆' },
  { token: 'pw', zhName: 'P杆', category: '挖起杆' },
  { token: 'gw', zhName: 'A杆', category: '挖起杆' },
  { token: 'sw', zhName: 'S杆', category: '挖起杆' },
  { token: 'lw', zhName: 'L杆', category: '挖起杆' },
  { token: 'wedge50', zhName: '50°', category: '挖起杆' },
  { token: 'wedge52', zhName: '52°', category: '挖起杆' },
  { token: 'wedge54', zhName: '54°', category: '挖起杆' },
  { token: 'wedge56', zhName: '56°', category: '挖起杆' },
  { token: 'wedge58', zhName: '58°', category: '挖起杆' },
  { token: 'wedge60', zhName: '60°', category: '挖起杆' },
  { token: 'putter', zhName: '推杆', category: '推杆' },
]

export function catalogByCategory(c: ClubCategory): CatalogClub[] {
  return CLUB_CATALOG.filter((x) => x.category === c)
}
export const METRES_PER_YARD = 0.9144
```
- [ ] Commit: `feat(web-clubs): club catalog (token vocabulary mirroring the backend)`

## Task 2: Types (`types.ts`)
```ts
export interface ClubBagEntry {
  token: string
  zhName: string | null
  customName: string | null
  clubTypeId: number | null
  distanceM: number | null
  distanceSource: string | null  // 'manual' | 'default' | null
}
export interface EffectiveClubBagResponse {
  schema: string
  source: string  // 'manual' | 'garmin' | 'none'
  found: boolean
  clubs: ClubBagEntry[]
}
export interface ClubBagUpdateEntry { token: string; customName?: string | null; distanceM?: number | null }
export interface ClubBagUpdateRequest { clubs: ClubBagUpdateEntry[] }
```
- [ ] Commit: `feat(web-clubs): effective club-bag TS types`

## Task 3: API (`api.ts`)
- [ ] Add `putJson<T>(path, body, adminToken?)` (copy `patchJson` verbatim, `method: 'PUT'`).
- [ ] Add (near `fetchAdminPlayers`):
```ts
export function fetchPlayerClubBag(playerId: string, adminToken?: string): Promise<EffectiveClubBagResponse> {
  return getJson<EffectiveClubBagResponse>(`/api/v2/players/${encodeURIComponent(playerId)}/clubs/bag`, adminToken)
}
export function putPlayerClubBag(playerId: string, body: ClubBagUpdateRequest, adminToken?: string): Promise<EffectiveClubBagResponse> {
  return putJson<EffectiveClubBagResponse>(`/api/v2/players/${encodeURIComponent(playerId)}/clubs/bag`, body, adminToken)
}
```
  (import the new types.)
- [ ] Commit: `feat(web-clubs): putJson + fetch/put player club bag`

## Task 4: Navigation + owner-only gate
- [ ] `navigation.ts`: add `| 'club-bag'` to `ProductPage`; `'club-bag': 'settings'` to `PAGE_TO_SECTION`; `{ page: 'club-bag', label: '球包管理' }` to `SETTINGS_SUBNAV` (place after `players`).
- [ ] `AppShell.tsx`: in the subnav filter that drops `players` unless owner, ALSO drop `club-bag` unless owner (same `playersAdminVisible` condition). Find the existing `.filter(... 'players' ...)` and extend it to `['players','club-bag'].includes(item.page)`.
- [ ] Commit: `feat(web-clubs): club-bag settings sub-page (owner-only)`

## Task 5: ClubBagPage (`ClubBagPage.tsx`)
- [ ] Self-fetching component (mirror `PlayerAdminPage`):
```tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchAdminPlayers, fetchPlayerClubBag, putPlayerClubBag } from '../api'
import type { AdminPlayer, ClubBagUpdateEntry, EffectiveClubBagResponse } from '../types'
import { CLUB_CATEGORIES, CLUB_CATALOG, METRES_PER_YARD, catalogByCategory } from '../clubCatalog'

export function ClubBagPage({ adminToken }: { adminToken?: string }) {
  const token = adminToken?.trim()
  const [players, setPlayers] = useState<AdminPlayer[]>([])
  const [playerId, setPlayerId] = useState('me')
  const [selected, setSelected] = useState<Set<string>>(new Set())   // tokens
  const [distYd, setDistYd] = useState<Record<string, number>>({})   // token -> yards
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [saveMsg, setSaveMsg] = useState<string>('')

  const applyBag = useCallback((bag: EffectiveClubBagResponse) => {
    setSelected(new Set(bag.clubs.map((c) => c.token)))
    const d: Record<string, number> = {}
    for (const c of bag.clubs) if (c.distanceM != null) d[c.token] = Math.round(c.distanceM / METRES_PER_YARD)
    setDistYd(d)
  }, [])

  const loadBag = useCallback(async (pid: string) => {
    if (!token) return
    setStatus('loading')
    try { applyBag(await fetchPlayerClubBag(pid, token)); setStatus('ready') }
    catch { setStatus('error') }
  }, [token, applyBag])

  useEffect(() => {
    if (!token) return
    fetchAdminPlayers(token).then((r) => setPlayers(r.players)).catch(() => {})
    loadBag('me')
  }, [token, loadBag])

  const onPickPlayer = (pid: string) => { setPlayerId(pid); setSaveMsg(''); loadBag(pid) }
  const toggle = (tok: string) => setSelected((s) => { const n = new Set(s); n.has(tok) ? n.delete(tok) : n.add(tok); return n })
  const setYards = (tok: string, raw: string) => {
    const v = parseInt(raw.replace(/[^0-9]/g, ''), 10)
    setDistYd((d) => { const n = { ...d }; if (v > 0) n[tok] = v; else delete n[tok]; return n })
  }

  const save = async () => {
    if (!token) return
    const clubs: ClubBagUpdateEntry[] = [...selected].map((tok) => ({
      token: tok, distanceM: distYd[tok] != null ? Math.round(distYd[tok] * METRES_PER_YARD) : null,
    }))
    setSaveMsg('保存中…')
    try { applyBag(await putPlayerClubBag(playerId, { clubs }, token)); setSaveMsg('已保存到云端') }
    catch { setSaveMsg('保存失败') }
  }

  if (!token) return <section className="stats-page"><div className="empty-state">需要管理员令牌(在「同步与数据健康」里登录)。</div></section>

  return (
    <section className="stats-page">
      <header className="section-head stats-head"><p className="eyebrow">设置</p><h1>球包管理</h1></header>
      <div className="panel">
        <label>球员:&nbsp;
          <select value={playerId} onChange={(e) => onPickPlayer(e.target.value)}>
            {players.map((p) => <option key={p.id} value={p.id}>{p.name}{p.isOwner ? '(本人)' : ''}</option>)}
          </select>
        </label>
        <p className="eyebrow">勾选该球员真实有的球杆,可填每支的常用距离(码)。没填的杆球童用通用兜底。</p>
      </div>
      {status === 'loading' && <div className="empty-state">加载中…</div>}
      {status === 'error' && <div className="empty-state">加载失败。</div>}
      {status === 'ready' && CLUB_CATEGORIES.map((cat) => (
        <div className="panel" key={cat}>
          <p className="eyebrow">{cat}</p>
          {catalogByCategory(cat).map((club) => {
            const on = selected.has(club.token)
            return (
              <div key={club.token} className="club-row">
                <label>
                  <input type="checkbox" checked={on} onChange={() => toggle(club.token)} /> {club.zhName}
                </label>
                {on && (
                  <span>
                    <input inputMode="numeric" value={distYd[club.token]?.toString() ?? ''}
                      onChange={(e) => setYards(club.token, e.target.value)} placeholder="—" style={{ width: 56, textAlign: 'right' }} /> 码
                  </span>
                )}
              </div>
            )
          })}
        </div>
      ))}
      <div className="panel">
        <button className="primary" onClick={save} disabled={status !== 'ready'}>保存到云端</button>
        {saveMsg && <span>&nbsp;{saveMsg}</span>}
      </div>
    </section>
  )
}
```
  (Adjust class names / button class to match an existing primary button in the codebase — grep `className="primary"` or how `PlayerAdminPage` styles its action buttons, and reuse that. Add a minimal `.club-row { display:flex; justify-content:space-between; align-items:center; padding:6px 0 }` to `styles.css` if no equivalent exists.)
- [ ] Commit: `feat(web-clubs): club-bag editor page (member picker + catalog + distances)`

## Task 6: Test (`ClubBagPage.test.tsx`) — TDD
- [ ] Mock api (Pattern B): mock `fetchAdminPlayers` → `{players:[{id:'me',name:'我',isOwner:true,...},{id:'p_a',name:'老王',isOwner:false,...}]}`, `fetchPlayerClubBag` → a bag with `source:'garmin'` + a couple clubs (e.g. `{token:'iron7', zhName:'七号铁', distanceM:128, ...}`), `putPlayerClubBag` → echoes. Assert: the player select lists both names; the bag's clubs render checked; the iron7 distance prefills `140` (128m→yd); toggling a club + clicking 保存到云端 calls `putPlayerClubBag('me', { clubs: [...] })` with the right tokens; picking 老王 calls `fetchPlayerClubBag('p_a', ...)`.
- [ ] Run: `cd web_v2 && npm test -- --run src/components/ClubBagPage.test.tsx` → expect PASS.
- [ ] Commit: `test(web-clubs): ClubBagPage member picker + save`

## Self-Review
- **Catalog tokens** all exist in backend `club_catalog.py` (driver…putter, wood7, wedge50-60) → PUTs won't 422.
- **Units:** UI yards; PUT `distanceM` metres (`yards*0.9144`); GET `distanceM` metres → yards. Blank when no distance (per the product call).
- **Owner-only:** the page + subnav tab gated by the admin-token/owner condition; the member picker uses `/api/v2/admin/players` ids; saves via `/api/v2/players/{id}/clubs/bag` (owner acts-for-any).
- **Gates:** `npm test` + `npm run build` locally; GitHub `frontend` CI. No homeserver needed until deploy.
