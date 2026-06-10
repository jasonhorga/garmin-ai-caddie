import type { ProductPage, SubNavItem } from '../navigation'

interface SubNavProps {
  items: SubNavItem[]
  activePage: ProductPage
  onNavigate: (page: ProductPage) => void
  variant?: 'tabs' | 'inner'
  label?: string
}

export function SubNav({ items, activePage, onNavigate, variant = 'tabs', label }: SubNavProps) {
  return (
    <nav className={variant === 'inner' ? 'subnav subnav--inner' : 'subnav'} aria-label={label ?? 'Secondary'}>
      {items.map((item) => {
        const active = item.page === activePage || Boolean(item.activeFor?.includes(activePage))
        return (
          <button
            key={item.page}
            type="button"
            className={active ? 'subnav-tab active' : 'subnav-tab'}
            aria-current={active ? 'page' : undefined}
            onClick={() => onNavigate(item.page)}
          >
            {item.label}
          </button>
        )
      })}
    </nav>
  )
}
