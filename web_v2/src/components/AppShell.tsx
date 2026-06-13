import type { ReactNode } from 'react'
import { PAGE_TO_SECTION, SECTION_LABELS, subnavForPage, type ProductPage } from '../navigation'
import type { CurrentPlayer } from '../types'
import { AppSidebar } from './AppSidebar'
import { CurrentPlayerBadge } from './CurrentPlayerBadge'
import { SubNav } from './SubNav'

interface AppShellProps {
  activePage: ProductPage
  onNavigate: (page: ProductPage) => void
  children: ReactNode
  // Owner-only 球员管理 tab. Hidden by default so a per-player link (no admin
  // token) never exposes the management surface; App turns it on only in owner
  // mode (admin token present, no player token in the URL).
  playersAdminVisible?: boolean
  // Token-resolved current player for the read-only top-bar badge ("当前是谁").
  // Null until known (e.g. overview still loading) → no badge.
  currentPlayer?: CurrentPlayer | null
}

export function AppShell({
  activePage,
  onNavigate,
  children,
  playersAdminVisible = false,
  currentPlayer = null,
}: AppShellProps) {
  const subnav = subnavForPage(activePage)
  const items = subnav && !playersAdminVisible ? subnav.filter((item) => item.page !== 'players') : subnav
  return (
    <div className="app-layout">
      <AppSidebar activePage={activePage} onNavigate={onNavigate} />
      <div className="app-main">
        <header className="app-topbar">
          <h1 className="app-topbar-title">{SECTION_LABELS[PAGE_TO_SECTION[activePage]]}</h1>
          {currentPlayer ? <CurrentPlayerBadge player={currentPlayer} /> : null}
        </header>
        {items ? <SubNav items={items} activePage={activePage} onNavigate={onNavigate} /> : null}
        <main className="app-content">
          <div className="app-shell">{children}</div>
        </main>
      </div>
    </div>
  )
}
