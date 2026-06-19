import type { ReactNode } from 'react'
import { OWNER_ONLY_PAGES, PAGE_TO_SECTION, SECTION_LABELS, subnavForPage, type ProductPage } from '../navigation'
import type { CurrentPlayer } from '../types'
import { AppSidebar } from './AppSidebar'
import { CurrentPlayerBadge } from './CurrentPlayerBadge'
import { SubNav } from './SubNav'

interface AppShellProps {
  activePage: ProductPage
  onNavigate: (page: ProductPage) => void
  children: ReactNode
  // Owner mode = bare URL (no per-player token). A player share link is not owner
  // mode → the 设置 section and every owner-only sub-page are hidden from it.
  isOwnerMode?: boolean
  // Owner-only 球员管理 tab. Shown only once an admin token is present (owner mode
  // + authenticated); the rest of 设置 stays reachable pre-auth so the owner can
  // enter the token.
  playersAdminVisible?: boolean
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
  playersAdminVisible = false,
  diagnostics = false,
  onToggleDiagnostics,
  currentPlayer = null,
}: AppShellProps) {
  const subnav = subnavForPage(activePage)
  const items = subnav
    ? subnav.filter((item) => {
        // Player links never see owner-only pages; pre-auth owners see 设置 but not
        // the data-bearing 球员管理 until a token is entered.
        if (!isOwnerMode && OWNER_ONLY_PAGES.includes(item.page)) return false
        if (item.page === 'players' && !playersAdminVisible) return false
        return true
      })
    : subnav
  return (
    <div className="app-layout">
      <AppSidebar activePage={activePage} onNavigate={onNavigate} isOwnerMode={isOwnerMode} />
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
