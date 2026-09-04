import type { ReactElement } from 'react'
import {
  OFF_RAIL_PAGES,
  PAGE_TO_SECTION,
  SECTION_DEFAULT_PAGE,
  SECTION_LABELS,
  SECTION_ORDER,
  UTILITY_NAV,
  type ProductPage,
  type ProductSection,
} from '../navigation'
import type { CurrentPlayer } from '../types'
import { CurrentPlayerBadge } from './CurrentPlayerBadge'

function SectionIcon({ section }: { section: ProductSection }): ReactElement {
  switch (section) {
    case 'results':
      // 成绩 — a compact performance trend.
      return (
        <svg className="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
          <polyline points="4 16 9 11 13 14 20 6" />
          <line x1="4" y1="20" x2="20" y2="20" />
        </svg>
      )
    case 'prep':
      // 备战 — a target (试算 the shot).
      return (
        <svg className="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="4" />
          <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
        </svg>
      )
    case 'bag':
      // 球包 — a golf flag on the green.
      return (
        <svg className="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M6 21V4" />
          <path d="M6 4h11l-2.5 3.5L17 11H6" />
        </svg>
      )
    case 'settings':
      return (
        <svg className="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
          <line x1="4" y1="8.5" x2="20" y2="8.5" />
          <line x1="4" y1="15.5" x2="20" y2="15.5" />
          <circle cx="9" cy="8.5" r="2.3" fill="#0f1729" />
          <circle cx="15" cy="15.5" r="2.3" fill="#0f1729" />
        </svg>
      )
  }
}

function UtilityIcon({ page }: { page: ProductPage }): ReactElement {
  if (page === 'record') {
    // 手机记分 — a phone.
    return (
      <svg className="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="7" y="3" width="10" height="18" rx="2.4" />
        <line x1="10.5" y1="18" x2="13.5" y2="18" />
      </svg>
    )
  }
  // 球童沙盘 — an advice lightbulb.
  return (
    <svg className="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9.5 18h5" />
      <path d="M10 21h4" />
      <path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1.1 1.3 1.1 2.2h5c0-.9.5-1.7 1.1-2.2A6 6 0 0 0 12 3z" />
    </svg>
  )
}

interface AppSidebarProps {
  activePage: ProductPage
  onNavigate: (page: ProductPage) => void
  // Signed-in identity, pinned to the rail footer. Null until resolved → no chip.
  currentPlayer?: CurrentPlayer | null
}

export function AppSidebar({ activePage, onNavigate, currentPlayer = null }: AppSidebarProps) {
  const activeSection = PAGE_TO_SECTION[activePage]
  // An off-rail page (single-round review / caddie sandbox / phone scorer) highlights its own secondary
  // entry, not the primary section it happens to belong to.
  const onOffRailPage = OFF_RAIL_PAGES.includes(activePage)
  const primarySections = SECTION_ORDER.filter((section) => section !== 'settings')
  return (
    <nav className="app-sidebar" aria-label="主导航">
      <div className="sidebar-brand">
        <span className="sidebar-logo" aria-hidden="true" />
        AI Caddie
      </div>
      {primarySections.map((section) => {
        const active = section === activeSection && !onOffRailPage
        return (
          <button
            key={section}
            type="button"
            className={active ? 'sidebar-item active' : 'sidebar-item'}
            aria-current={active ? 'page' : undefined}
            onClick={() => onNavigate(SECTION_DEFAULT_PAGE[section])}
          >
            <SectionIcon section={section} />
            {SECTION_LABELS[section]}
          </button>
        )
      })}

      <div className="sidebar-utility" aria-label="工具">
        {UTILITY_NAV.map((item) => {
          const active = item.page === activePage
          return (
            <button
              key={item.page}
              type="button"
              className={active ? 'sidebar-item sidebar-item--utility active' : 'sidebar-item sidebar-item--utility'}
              aria-current={active ? 'page' : undefined}
              onClick={() => onNavigate(item.page)}
            >
              <UtilityIcon page={item.page} />
              {item.label}
            </button>
          )
        })}
      </div>

      <span className="sidebar-spacer" />

      <button
        type="button"
        className={
          activeSection === 'settings' && !onOffRailPage
            ? 'sidebar-item sidebar-item--footer active'
            : 'sidebar-item sidebar-item--footer'
        }
        aria-current={activeSection === 'settings' && !onOffRailPage ? 'page' : undefined}
        onClick={() => onNavigate(SECTION_DEFAULT_PAGE.settings)}
      >
        <SectionIcon section="settings" />
        {SECTION_LABELS.settings}
      </button>

      {currentPlayer ? (
        <div className="sidebar-who">
          <CurrentPlayerBadge player={currentPlayer} />
        </div>
      ) : null}
    </nav>
  )
}
