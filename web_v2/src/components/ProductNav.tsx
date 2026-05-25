export type ProductPage = 'overview' | 'history' | 'stats' | 'courses' | 'holes' | 'clubs' | 'issues' | 'quality'

const navItems: Array<{ id: ProductPage; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'history', label: 'History' },
  { id: 'stats', label: 'Stats' },
  { id: 'courses', label: 'Courses' },
  { id: 'holes', label: 'Holes' },
  { id: 'clubs', label: 'Clubs' },
  { id: 'issues', label: 'Issues' },
  { id: 'quality', label: 'Quality' },
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
