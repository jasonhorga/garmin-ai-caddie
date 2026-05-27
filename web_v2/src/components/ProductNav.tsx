export type ProductPage =
  | 'overview'
  | 'history'
  | 'rounds'
  | 'caddie'
  | 'corrections'
  | 'courses'
  | 'holes'
  | 'clubs'
  | 'issues'
  | 'reports'
  | 'sync-quality'
  | 'settings'

const navItems: Array<{ id: ProductPage; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'history', label: 'History' },
  { id: 'rounds', label: 'Rounds' },
  { id: 'courses', label: 'Courses' },
  { id: 'holes', label: 'Holes' },
  { id: 'clubs', label: 'Clubs' },
  { id: 'issues', label: 'Issues' },
  { id: 'caddie', label: 'Caddie' },
  { id: 'corrections', label: 'Corrections' },
  { id: 'sync-quality', label: 'Sync & Data Quality' },
  { id: 'reports', label: 'Reports' },
  { id: 'settings', label: 'Settings' },
]

interface ProductNavProps {
  activePage: ProductPage
  onNavigate: (page: ProductPage) => void
}

export function ProductNav({ activePage, onNavigate }: ProductNavProps) {
  return (
    <header className="topbar">
      <div className="brand-mark" aria-hidden="true" />
      <nav aria-label="Primary">
        {navItems.map((item) => {
          if (item.id === activePage) {
            return (
              <span key={item.id} className="active" aria-current="page">
                {item.label}
              </span>
            )
          }

          return (
            <button key={item.id} type="button" onClick={() => onNavigate(item.id)}>
              {item.label}
            </button>
          )
        })}
      </nav>
    </header>
  )
}
