import { useEffect, useState } from 'react'
import { fetchFamilyUsers } from '../api'
import type { FamilyUserRow } from '../types'

// Owner-only family roster (consumer era). Members now self-register via Sign in
// with Apple, so the old per-player link-issuance model is gone: this page only
// LISTS the family (display name + role + join date) from the identity DB
// (/admin/family/users). It holds no score analysis and no token/link material,
// and is reached only in owner mode (gated out of the consumer nav by AppShell).

interface PlayerAdminPageProps {
  adminToken?: string
}

type ListState =
  | { status: 'loading' }
  | { status: 'ready'; users: FamilyUserRow[] }
  | { status: 'error'; message: string }

const ROLE_LABEL: Record<string, string> = { admin: '主理人', member: '家人' }

function roleLabel(role: string): string {
  return ROLE_LABEL[role] ?? role
}

function joinedDate(createdAt: string): string {
  return createdAt.slice(0, 10)
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '未知错误'
}

export function PlayerAdminPage({ adminToken }: PlayerAdminPageProps) {
  const [listState, setListState] = useState<ListState>({ status: 'loading' })

  useEffect(() => {
    // Every setState runs in the async continuation (never synchronously in the effect
    // body) so a token change can't trigger a cascading render (react-hooks/set-state-in-effect).
    // The initial state is already 'loading'.
    let cancelled = false
    fetchFamilyUsers(adminToken)
      .then((data) => {
        if (cancelled) return
        // Soft-deleted users still come back on the roster — hide them.
        const active = data.users.filter((user) => !user.deletedAt)
        setListState({ status: 'ready', users: active })
      })
      .catch((error: unknown) => {
        if (!cancelled) setListState({ status: 'error', message: errorMessage(error) })
      })
    return () => {
      cancelled = true
    }
  }, [adminToken])

  return (
    <section className="player-admin-page" aria-label="家庭成员工作区">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">家庭成员</p>
          <h1>球员管理</h1>
          <p>家人用 Apple 登录后自动加入,这里只看成员,不展示任何人的成绩。</p>
        </div>
      </div>

      {listState.status === 'loading' ? (
        <section className="panel empty-state">
          <h2>成员加载中</h2>
        </section>
      ) : null}

      {listState.status === 'error' ? (
        <section className="panel empty-state">
          <h2>加载成员失败</h2>
          <p>{listState.message}</p>
        </section>
      ) : null}

      {listState.status === 'ready' ? (
        listState.users.length ? (
          <ul className="player-admin-list" aria-label="家庭成员列表">
            {listState.users.map((user) => {
              const joined = joinedDate(user.createdAt)
              return (
                <li key={user.id} className="panel player-admin-row">
                  <div className="player-admin-row-main">
                    <div className="player-admin-identity">
                      <strong>{user.displayName}</strong>
                      <span className={user.role === 'admin' ? 'semantic-chip quality-good' : 'semantic-chip'}>
                        {roleLabel(user.role)}
                      </span>
                    </div>
                    {joined ? (
                      <div className="player-admin-meta">
                        <span className="player-admin-stat player-admin-muted">{joined} 加入</span>
                      </div>
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ul>
        ) : (
          <section className="panel empty-state">
            <h2>还没有家人加入</h2>
            <p className="empty-state-hint">把 App 分享给家人,他们用 Apple 登录后会自动出现在这里。</p>
          </section>
        )
      ) : null}
    </section>
  )
}
