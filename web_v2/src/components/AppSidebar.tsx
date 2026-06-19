import type { ReactElement } from 'react'
import {
  PAGE_TO_SECTION,
  SECTION_DEFAULT_PAGE,
  SECTION_LABELS,
  SECTION_ORDER,
  type ProductPage,
  type ProductSection,
} from '../navigation'

function SectionIcon({ section }: { section: ProductSection }): ReactElement {
  switch (section) {
    case 'home':
      return (
        <svg className="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3 10.5 12 3l9 7.5" />
          <path d="M5 9.5V21h14V9.5" />
        </svg>
      )
    case 'history':
      return (
        <svg className="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
          <polyline points="3 15 8 10 12 13 21 4" />
          <polyline points="15 4 21 4 21 10" />
        </svg>
      )
    case 'prep':
      return (
        <svg className="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="4" />
          <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
        </svg>
      )
    case 'live':
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
          <circle cx="9" cy="8.5" r="2.3" fill="var(--panel)" />
          <circle cx="15" cy="15.5" r="2.3" fill="var(--panel)" />
        </svg>
      )
  }
}

interface AppSidebarProps {
  activePage: ProductPage
  onNavigate: (page: ProductPage) => void
}

export function AppSidebar({ activePage, onNavigate }: AppSidebarProps) {
  const activeSection = PAGE_TO_SECTION[activePage]
  return (
    <nav className="app-sidebar" aria-label="主导航">
      <div className="sidebar-brand">
        <span className="sidebar-logo" aria-hidden="true" />
        AI Caddie
      </div>
      {SECTION_ORDER.map((section) => {
        const active = section === activeSection
        const classes = ['sidebar-item']
        if (section === 'settings') classes.push('sidebar-item--footer')
        if (active) classes.push('active')
        return (
          <button
            key={section}
            type="button"
            className={classes.join(' ')}
            aria-current={active ? 'page' : undefined}
            onClick={() => onNavigate(SECTION_DEFAULT_PAGE[section])}
          >
            <SectionIcon section={section} />
            {SECTION_LABELS[section]}
          </button>
        )
      })}
    </nav>
  )
}
