import type { ReactNode } from 'react'
import {
  PAGE_TO_SECTION,
  SECTION_LABELS,
  subnavForPage,
  visibleSettingsSubnav,
  type ProductPage,
  type SettingsAccess,
} from '../navigation'
import type { CurrentPlayer } from '../types'
import { AppSidebar } from './AppSidebar'
import { CurrentPlayerBadge } from './CurrentPlayerBadge'
import { SubNav } from './SubNav'

interface AppShellProps {
  activePage: ProductPage
  onNavigate: (page: ProductPage) => void
  children: ReactNode
  // Owner mode = bare URL (no per-player token). Only gates the owner-only
  // diagnostics switch in the topbar; player links never see that switch.
  isOwnerMode?: boolean
  // Who may see which settings tab. The owner sees everything; a signed-in member sees
  // only the consumer tabs (连接 Garmin / 球包管理 / 账户 / 订正); a fresh or legacy
  // per-player-link visitor sees neither the owner tabs (球员管理 / 后端配置) nor
  // account / 球包. Defaults to the locked-down (consumer-link) view.
  settingsAccess?: SettingsAccess
  // Owner-only "diagnostics mode": reveal internal refs / source panels / data
  // quality. Default off; the topbar switch is shown only in owner mode.
  diagnostics?: boolean
  onToggleDiagnostics?: () => void
  // Token-resolved current player for the read-only top-bar badge ("当前是谁").
  // Null until known (e.g. overview still loading) → no badge.
  currentPlayer?: CurrentPlayer | null
}

export function AppShell({
  activePage,
  onNavigate,
  children,
  isOwnerMode = true,
  settingsAccess = { isOwner: false, hasSession: false },
  diagnostics = false,
  onToggleDiagnostics,
  currentPlayer = null,
}: AppShellProps) {
  const subnav = subnavForPage(activePage)
  // The settings subnav is access-filtered (owner vs member vs locked); other sections
  // (e.g. history) show their full subnav.
  const items =
    subnav && PAGE_TO_SECTION[activePage] === 'settings' ? visibleSettingsSubnav(settingsAccess) : subnav
  return (
    <div className="app-layout">
      <AppSidebar activePage={activePage} onNavigate={onNavigate} />
      <div className="app-main">
        <header className="app-topbar">
          <h1 className="app-topbar-title">{SECTION_LABELS[PAGE_TO_SECTION[activePage]]}</h1>
          <div className="app-topbar-actions">
            {isOwnerMode && onToggleDiagnostics ? (
              <label className="diagnostics-toggle" title="显示内部 ref / 来源 / 数据质量(仅本人)">
                <input type="checkbox" checked={diagnostics} onChange={onToggleDiagnostics} />
                <span>诊断模式</span>
              </label>
            ) : null}
            {currentPlayer ? <CurrentPlayerBadge player={currentPlayer} /> : null}
          </div>
        </header>
        {items ? <SubNav items={items} activePage={activePage} onNavigate={onNavigate} /> : null}
        <main className="app-content">
          <div className="app-shell">{children}</div>
        </main>
      </div>
    </div>
  )
}
