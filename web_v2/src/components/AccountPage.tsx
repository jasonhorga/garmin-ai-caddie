import type { CurrentPlayer } from '../types'

// Consumer account screen (settings → 账户). Shows who you're signed in as and lets
// you sign out — clearing the Apple session and returning to the sign-in screen. No
// engineering controls; the owner-only backend config lives on its own gated tab.

interface AccountPageProps {
  player?: CurrentPlayer | null
  onSignOut: () => void
}

export function AccountPage({ player = null, onSignOut }: AccountPageProps) {
  return (
    <section className="settings-page" aria-label="账户工作区">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">账户</p>
          <h1>账户</h1>
          <p>你的登录身份与隐私。</p>
        </div>
      </div>
      <div className="panel">
        <div className="settings-fact-grid">
          <span>当前登录</span>
          <b>{player?.name ?? '已用 Apple 登录'}</b>
          <span>数据可见</span>
          <b>仅你自己</b>
        </div>
        <p className="eyebrow">我们只用你的高尔夫数据为你做分析,不与家人互通成绩。</p>
        <button className="sync-action" type="button" onClick={onSignOut}>
          退出登录
        </button>
      </div>
    </section>
  )
}
