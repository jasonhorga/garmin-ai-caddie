import type { ProductPage } from '../navigation'
import type { CurrentPlayer, ProductSettingsResponse } from '../types'

interface SettingsPageProps {
  onNavigate: (page: ProductPage) => void
  settings?: ProductSettingsResponse | null
  settingsError?: string | null
  // The signed-in player (Apple session) for the 账号 card. Null until known.
  currentPlayer?: CurrentPlayer | null
  // Clears the Apple session and returns to sign-in (App wires this to sessionStore).
  onSignOut?: () => void
}

// Consumer 设置 — account, Garmin connection, clubs, corrections, privacy. The
// engineering control plane (AI engines, OAuth capability matrices, offline-package
// internals, admin-token entry, snapshot/reconciliation diagnostics) is NOT here:
// the owner manages backend config via ops/env, and everyone else signs in with
// Apple. Garmin connection is read-only here (connect/re-login happens in the
// iPhone app) and is derived from the product-settings data-source state.
export function SettingsPage({ onNavigate, settings, settingsError, currentPlayer, onSignOut }: SettingsPageProps) {
  const dataSources = Array.isArray(settings?.dataSources) ? settings.dataSources : []
  const cnSession = dataSources.find((source) => asString(source.id) === 'garmin_cn_web_session')
  const garminState = asString(cnSession?.state)
  // The CN web-session data source is the only path that reads golf data; treat a
  // configured/available/ready source as 已连接. Anything else (or no settings yet) → 未连接.
  const garminConnected = garminState ? CONNECTED_STATES.has(garminState) : false
  const accountName = currentPlayer?.name?.trim() || '已登录'

  return (
    <section className="settings-page" aria-label="设置">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">你的账号</p>
          <h1>设置</h1>
          <p>账号、Garmin 连接、球杆与隐私。</p>
        </div>
        {settingsError ? <span className="semantic-chip quality-missing">{settingsError}</span> : null}
      </div>

      <div className="settings-grid">
        <article className="settings-item" aria-label="账号">
          <div className="settings-item-main">
            <h2>账号</h2>
            <p className="settings-account-name">{accountName}</p>
            <p className="settings-account-sub">通过 Apple 登录</p>
          </div>
          {onSignOut ? (
            <button type="button" onClick={onSignOut}>
              退出登录
            </button>
          ) : null}
        </article>

        <article className="settings-item" aria-label="连接 Garmin">
          <div className="settings-item-main">
            <h2>连接 Garmin</h2>
            <div className="setting-chip-row">
              <span className={garminConnected ? 'semantic-chip quality-good' : 'semantic-chip quality-missing'}>
                {garminConnected ? '已连接' : '未连接'}
              </span>
            </div>
            <p>你的成绩和击球数据会从 Garmin 手表同步过来。</p>
            <p className="settings-account-sub">在 iPhone App 上连接或重新登录 Garmin。</p>
          </div>
        </article>

        <article className="settings-item" aria-label="我的球杆">
          <div className="settings-item-main">
            <h2>我的球杆</h2>
            <p>管理你真实在用的球杆，以及每支杆的常用距离。</p>
          </div>
          <button type="button" onClick={() => onNavigate('club-bag')}>
            管理你的球杆
          </button>
        </article>

        <article className="settings-item" aria-label="数据更正">
          <div className="settings-item-main">
            <h2>数据更正</h2>
            <p>修正成绩、问题标签、球童反馈。</p>
          </div>
          <button type="button" onClick={() => onNavigate('corrections')}>
            打开数据更正
          </button>
        </article>

        <article className="settings-item" aria-label="隐私">
          <div className="settings-item-main">
            <h2>隐私</h2>
            <p>你的数据只属于你。</p>
            <p>照片和视频可以先脱敏，再用于分析。</p>
          </div>
        </article>

        <article className="settings-item" aria-label="关于">
          <div className="settings-item-main">
            <h2>关于</h2>
            <p>AI Caddie</p>
            <p className="settings-account-sub">你的随身高尔夫球童。</p>
          </div>
        </article>
      </div>
    </section>
  )
}

// Data-source states (server_v2/product_settings.py + connectors) that mean the
// Garmin path is wired up. Unknown/missing states fall through to 未连接.
const CONNECTED_STATES = new Set(['available', 'ready', 'configured'])

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}
