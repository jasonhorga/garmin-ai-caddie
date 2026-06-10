# Web Redesign W1a — App Shell, Sidebar IA, Design Tokens

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **中文摘要:** 本计划把 web_v2 从「12 个平铺英文标签的工程仪表盘」重组为「图标+文字中文侧边栏(概览/历史/备战/实战/设置)+ 二级页签」的产品外壳。纯结构重组:所有现有页面原样搬家,不改功能;工程面板从各页顶部消失、只留在「设置·同步与数据健康」;备战(赛前攻略)升为一级入口。新概览页/历史新页面是 W1b 的事。

**Goal:** Replace the flat 12-tab top nav with the validated product shell — icon+label Chinese sidebar (概览/历史/备战/实战/设置) + sub-nav tabs — rehoming every existing page with zero feature changes.

**Architecture:** Keep `ProductPage` string-state routing as the single source of truth (no router lib). Add a `navigation.ts` map (page→section, section→default page, sub-navs, Chinese labels), three presentational components (`AppSidebar`, `SubNav`, `AppShell`), and refactor `App.tsx` to render one `AppShell` wrapper around per-page content. The global sync panel disappears from product pages (stays on the overview error screen for token recovery, and inside 设置·同步 which already embeds it).

**Tech Stack:** React 19 + TypeScript + Vite, Vitest + Testing Library, Playwright e2e, plain CSS with custom properties (no new dependencies).

**Spec:** `docs/superpowers/specs/2026-06-09-web-product-redesign-design.md` (decisions D1, D4; §4 IA table; §6 tokens). W1a deliberately does NOT build the new 概览 home or 历史 redesigned pages (that is W1b) — 概览 shows the existing HistoryOverview content for now.

**Branch / worktree:** `superpowers/web-redesign-w1a` off `integration/v2`, in an isolated worktree (use superpowers:using-git-worktrees). All `npm` commands run in `web_v2/`; run `npm ci` once after entering the worktree. CI equivalents: `npm test -- --run`, `npm run lint`, `npm run build`, `npm run test:e2e`.

**New IA (interim W1a):**

| Sidebar (Chinese) | Sub-nav | ProductPage id (unchanged) | Content component |
|---|---|---|---|
| 概览 | — | `overview` | HistoryOverview (existing) |
| 历史 | 趋势总览 | `history` | StatsOverview |
| 历史 | 球局 | `rounds` | HistoryTimeline |
| 历史 | 强弱分析 (inner tabs 按洞/按杆/问题) | `holes` / `clubs` / `issues` | HoleStats / ClubStats / IssueStats |
| 历史 | 球场 | `courses` | CourseStats |
| 历史 | 报告 | `reports` | ReportsPage |
| 备战 | — | `prep` (NEW id) | CoursePrepPanel (moved out of caddie page) |
| 实战 | — | `caddie` | CaddiePage |
| 设置 | 同步与数据健康 | `sync-quality` | existing sync-quality workspace |
| 设置 | 订正 | `corrections` | CorrectionsPage |
| 设置 | 后端配置 | `settings` | SettingsPage |

---

### Task 0: Worktree, branch, and docs commit

**Files:**
- Commit: `docs/superpowers/specs/2026-06-09-web-product-redesign-design.md` (already written, untracked)
- Commit: `docs/superpowers/plans/2026-06-10-web-redesign-w1a-shell.md` (this file)

- [ ] **Step 1: Create worktree + branch** (superpowers:using-git-worktrees)

```bash
git -C /home/ubuntu/claude-web-data/repo/garmin-ai-caddie worktree add ../garmin-ai-caddie-w1a -b superpowers/web-redesign-w1a integration/v2
```

- [ ] **Step 2: Copy the two docs into the worktree (they are untracked in the main checkout), commit**

```bash
cd /home/ubuntu/claude-web-data/repo/garmin-ai-caddie-w1a
mkdir -p docs/superpowers/specs docs/superpowers/plans
cp ../garmin-ai-caddie/docs/superpowers/specs/2026-06-09-web-product-redesign-design.md docs/superpowers/specs/
cp ../garmin-ai-caddie/docs/superpowers/plans/2026-06-10-web-redesign-w1a-shell.md docs/superpowers/plans/
git add docs/superpowers/specs/2026-06-09-web-product-redesign-design.md docs/superpowers/plans/2026-06-10-web-redesign-w1a-shell.md
git commit -m "docs: spec + plan for web product redesign (W1a shell)"
```

- [ ] **Step 3: Install frontend deps**

```bash
cd web_v2 && npm ci
```
Expected: clean install, no errors.

---

### Task 1: `navigation.ts` — the IA map

**Files:**
- Create: `web_v2/src/navigation.ts`
- Test: `web_v2/src/navigation.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// web_v2/src/navigation.test.ts
import { describe, expect, it } from 'vitest'
import {
  ANALYSIS_TABS,
  HISTORY_SUBNAV,
  PAGE_TO_SECTION,
  SECTION_DEFAULT_PAGE,
  SECTION_LABELS,
  SECTION_ORDER,
  SETTINGS_SUBNAV,
  subnavForPage,
} from './navigation'

describe('navigation map', () => {
  it('assigns every page to a section whose default page maps back to that section', () => {
    for (const section of Object.values(PAGE_TO_SECTION)) {
      expect(SECTION_ORDER).toContain(section)
      expect(PAGE_TO_SECTION[SECTION_DEFAULT_PAGE[section]]).toBe(section)
    }
  })

  it('labels all five sections in Chinese, settings last', () => {
    expect(SECTION_ORDER.map((section) => SECTION_LABELS[section])).toEqual(['概览', '历史', '备战', '实战', '设置'])
  })

  it('returns the history subnav for any history page and the settings subnav for plumbing pages', () => {
    expect(subnavForPage('clubs')).toBe(HISTORY_SUBNAV)
    expect(subnavForPage('rounds')).toBe(HISTORY_SUBNAV)
    expect(subnavForPage('corrections')).toBe(SETTINGS_SUBNAV)
    expect(subnavForPage('overview')).toBeNull()
    expect(subnavForPage('prep')).toBeNull()
    expect(subnavForPage('caddie')).toBeNull()
  })

  it('marks 强弱分析 active for holes/clubs/issues and exposes the three analysis tabs', () => {
    const analysis = HISTORY_SUBNAV.find((item) => item.label === '强弱分析')
    expect(analysis?.page).toBe('holes')
    expect(analysis?.activeFor).toEqual(['holes', 'clubs', 'issues'])
    expect(ANALYSIS_TABS.map((tab) => tab.page)).toEqual(['holes', 'clubs', 'issues'])
  })
})
```

- [ ] **Step 2: Run it — must fail (module missing)**

```bash
npx vitest run src/navigation.test.ts
```
Expected: FAIL — cannot resolve `./navigation`.

- [ ] **Step 3: Implement `navigation.ts`**

```ts
// web_v2/src/navigation.ts
export type ProductPage =
  | 'overview'
  | 'history'
  | 'rounds'
  | 'courses'
  | 'holes'
  | 'clubs'
  | 'issues'
  | 'reports'
  | 'caddie'
  | 'prep'
  | 'corrections'
  | 'sync-quality'
  | 'settings'

export type ProductSection = 'home' | 'history' | 'prep' | 'live' | 'settings'

export const PAGE_TO_SECTION: Record<ProductPage, ProductSection> = {
  overview: 'home',
  history: 'history',
  rounds: 'history',
  courses: 'history',
  holes: 'history',
  clubs: 'history',
  issues: 'history',
  reports: 'history',
  prep: 'prep',
  caddie: 'live',
  corrections: 'settings',
  'sync-quality': 'settings',
  settings: 'settings',
}

export const SECTION_ORDER: ProductSection[] = ['home', 'history', 'prep', 'live', 'settings']

export const SECTION_LABELS: Record<ProductSection, string> = {
  home: '概览',
  history: '历史',
  prep: '备战',
  live: '实战',
  settings: '设置',
}

export const SECTION_DEFAULT_PAGE: Record<ProductSection, ProductPage> = {
  home: 'overview',
  history: 'history',
  prep: 'prep',
  live: 'caddie',
  settings: 'sync-quality',
}

export interface SubNavItem {
  page: ProductPage
  label: string
  activeFor?: ProductPage[]
}

export const HISTORY_SUBNAV: SubNavItem[] = [
  { page: 'history', label: '趋势总览' },
  { page: 'rounds', label: '球局' },
  { page: 'holes', label: '强弱分析', activeFor: ['holes', 'clubs', 'issues'] },
  { page: 'courses', label: '球场' },
  { page: 'reports', label: '报告' },
]

export const SETTINGS_SUBNAV: SubNavItem[] = [
  { page: 'sync-quality', label: '同步与数据健康' },
  { page: 'corrections', label: '订正' },
  { page: 'settings', label: '后端配置' },
]

export const ANALYSIS_TABS: SubNavItem[] = [
  { page: 'holes', label: '按洞' },
  { page: 'clubs', label: '按杆' },
  { page: 'issues', label: '问题' },
]

export function subnavForPage(page: ProductPage): SubNavItem[] | null {
  const section = PAGE_TO_SECTION[page]
  if (section === 'history') return HISTORY_SUBNAV
  if (section === 'settings') return SETTINGS_SUBNAV
  return null
}
```

- [ ] **Step 4: Re-run — must pass**

```bash
npx vitest run src/navigation.test.ts
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add web_v2/src/navigation.ts web_v2/src/navigation.test.ts
git commit -m "feat(web): navigation map for the five-section product IA"
```

---

### Task 2: Design tokens + shell CSS

**Files:**
- Modify: `web_v2/src/styles.css` (`:root` block at lines 1–27; append a new section at end of file)

- [ ] **Step 1: Update `:root` palette values** (keep every existing variable name; only change values and add new ones)

In the `:root` block, change:

```css
  --bg: #f6f7f8;
  --ink: #0f1720;
  --muted: #6b7280;
  --line: #e7e9ec;
  --green: #15803d;
```

and add (after `--double-soft`):

```css
  --green-bright: #22c55e;
  --green-tint: #e7f3ec;
  --radius-card: 14px;
```

Also update the two hardcoded literals at the very top of `:root` (`color: #18231f;` → `color: #0f1720;`, `background: #f4f6f2;` → `background: #f6f7f8;`).

- [ ] **Step 2: Append the shell layout CSS at the end of `styles.css`**

```css
/* ===== W1a app shell: sidebar + topbar + subnav ===== */
.app-layout {
  display: flex;
  min-height: 100vh;
}

.app-sidebar {
  width: 218px;
  flex: 0 0 218px;
  background: var(--panel);
  border-right: 1px solid var(--line);
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  position: sticky;
  top: 0;
  height: 100vh;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 9px;
  font-weight: 700;
  font-size: 14px;
  padding: 4px 8px 16px;
  color: var(--ink);
}

.sidebar-logo {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--green), var(--green-bright));
  flex: 0 0 26px;
}

.sidebar-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
  stroke: currentColor;
  fill: none;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.sidebar-item {
  display: flex;
  align-items: center;
  gap: 11px;
  color: var(--muted);
  font-size: 13.5px;
  padding: 9px 11px;
  border-radius: 10px;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  width: 100%;
  font-family: inherit;
}

.sidebar-item:hover {
  background: var(--bg);
  color: var(--ink);
}

.sidebar-item.active {
  background: var(--green-tint);
  color: var(--green);
  font-weight: 600;
}

.sidebar-item--footer {
  margin-top: auto;
}

.app-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}

.app-topbar {
  min-height: 54px;
  background: var(--panel);
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  padding: 0 18px;
  position: sticky;
  top: 0;
  z-index: 5;
}

.app-topbar-title {
  margin: 0;
  font-size: 17px;
  color: var(--ink);
}

.subnav {
  display: flex;
  gap: 4px;
  background: var(--panel);
  border-bottom: 1px solid var(--line);
  padding: 0 14px;
}

.subnav-tab {
  font-size: 13px;
  color: var(--muted);
  padding: 11px 12px;
  border: none;
  background: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  font-family: inherit;
}

.subnav-tab.active {
  color: var(--green);
  border-bottom-color: var(--green);
  font-weight: 600;
}

.subnav--inner {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 3px;
  gap: 2px;
  background: var(--bg);
  width: fit-content;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--line);
}

.subnav--inner .subnav-tab {
  border-bottom: none;
  border-radius: 7px;
  padding: 7px 14px;
}

.subnav--inner .subnav-tab.active {
  background: var(--green);
  color: #fff;
}

.app-content {
  flex: 1;
}

/* Inside the new layout the legacy .app-shell width clamp (100vw-based) would
   overflow horizontally next to the sidebar — neutralize it within .app-content. */
.app-content .app-shell {
  width: auto;
  max-width: 1100px;
  margin: 0;
  padding: 18px 18px 32px;
}

@media (max-width: 900px) {
  .app-sidebar {
    width: 64px;
    flex-basis: 64px;
    padding: 16px 8px;
  }

  .app-sidebar .sidebar-brand {
    justify-content: center;
    padding-bottom: 16px;
    font-size: 0;
    gap: 0;
  }

  .app-sidebar .sidebar-item {
    justify-content: center;
    font-size: 0;
    gap: 0;
    padding: 11px 0;
  }

  .app-sidebar .sidebar-icon {
    width: 20px;
    height: 20px;
  }
}
```

- [ ] **Step 3: Verify CSS parses (build)**

```bash
npm run build
```
Expected: build succeeds (TS errors none — no TS touched yet).

- [ ] **Step 4: Commit**

```bash
git add web_v2/src/styles.css
git commit -m "feat(web): design tokens + app-shell layout CSS (spec §6)"
```

---

### Task 3: `AppSidebar` component

**Files:**
- Create: `web_v2/src/components/AppSidebar.tsx`
- Test: `web_v2/src/components/AppSidebar.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// web_v2/src/components/AppSidebar.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AppSidebar } from './AppSidebar'

describe('AppSidebar', () => {
  it('renders the five Chinese sections and marks the active one', () => {
    render(<AppSidebar activePage="clubs" onNavigate={() => undefined} />)
    ;['概览', '历史', '备战', '实战', '设置'].forEach((label) =>
      expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    expect(screen.getByRole('button', { name: '历史' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: '概览' })).not.toHaveAttribute('aria-current')
    expect(screen.getByText('AI Caddie')).toBeInTheDocument()
  })

  it('navigates to each section default page', async () => {
    const onNavigate = vi.fn()
    render(<AppSidebar activePage="overview" onNavigate={onNavigate} />)
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    expect(onNavigate).toHaveBeenCalledWith('history')
    await userEvent.click(screen.getByRole('button', { name: '备战' }))
    expect(onNavigate).toHaveBeenCalledWith('prep')
    await userEvent.click(screen.getByRole('button', { name: '实战' }))
    expect(onNavigate).toHaveBeenCalledWith('caddie')
    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    expect(onNavigate).toHaveBeenCalledWith('sync-quality')
  })
})
```

- [ ] **Step 2: Run — FAIL (component missing)**

```bash
npx vitest run src/components/AppSidebar.test.tsx
```

- [ ] **Step 3: Implement**

```tsx
// web_v2/src/components/AppSidebar.tsx
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
    <nav className="app-sidebar" aria-label="Primary">
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
```

- [ ] **Step 4: Run — PASS**

```bash
npx vitest run src/components/AppSidebar.test.tsx
```

- [ ] **Step 5: Commit**

```bash
git add web_v2/src/components/AppSidebar.tsx web_v2/src/components/AppSidebar.test.tsx
git commit -m "feat(web): AppSidebar — icon+label Chinese section nav (spec D1)"
```

---

### Task 4: `SubNav` component

**Files:**
- Create: `web_v2/src/components/SubNav.tsx`
- Test: `web_v2/src/components/SubNav.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// web_v2/src/components/SubNav.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { HISTORY_SUBNAV } from '../navigation'
import { SubNav } from './SubNav'

describe('SubNav', () => {
  it('renders tabs and marks the active page, including activeFor aliases', () => {
    render(<SubNav items={HISTORY_SUBNAV} activePage="clubs" onNavigate={() => undefined} />)
    ;['趋势总览', '球局', '强弱分析', '球场', '报告'].forEach((label) =>
      expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    expect(screen.getByRole('button', { name: '强弱分析' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: '球局' })).not.toHaveAttribute('aria-current')
  })

  it('fires onNavigate with the tab page id', async () => {
    const onNavigate = vi.fn()
    render(<SubNav items={HISTORY_SUBNAV} activePage="history" onNavigate={onNavigate} />)
    await userEvent.click(screen.getByRole('button', { name: '报告' }))
    expect(onNavigate).toHaveBeenCalledWith('reports')
  })
})
```

- [ ] **Step 2: Run — FAIL**

```bash
npx vitest run src/components/SubNav.test.tsx
```

- [ ] **Step 3: Implement**

```tsx
// web_v2/src/components/SubNav.tsx
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
```

- [ ] **Step 4: Run — PASS, then commit**

```bash
npx vitest run src/components/SubNav.test.tsx
git add web_v2/src/components/SubNav.tsx web_v2/src/components/SubNav.test.tsx
git commit -m "feat(web): SubNav tabs (history/settings second level + inner analysis pills)"
```

---

### Task 5: `AppShell` component

**Files:**
- Create: `web_v2/src/components/AppShell.tsx`
- Test: `web_v2/src/components/AppShell.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// web_v2/src/components/AppShell.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders sidebar, section title, history subnav, and children for a history page', () => {
    render(
      <AppShell activePage="clubs" onNavigate={() => undefined}>
        <p>stats body</p>
      </AppShell>,
    )
    expect(screen.getByRole('button', { name: '历史' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('heading', { name: '历史' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '强弱分析' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('stats body')).toBeInTheDocument()
  })

  it('renders no subnav for sections without one', () => {
    render(
      <AppShell activePage="overview" onNavigate={() => undefined}>
        <p>home body</p>
      </AppShell>,
    )
    expect(screen.getByRole('heading', { name: '概览' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '趋势总览' })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run — FAIL**

```bash
npx vitest run src/components/AppShell.test.tsx
```

- [ ] **Step 3: Implement**

```tsx
// web_v2/src/components/AppShell.tsx
import type { ReactNode } from 'react'
import { PAGE_TO_SECTION, SECTION_LABELS, subnavForPage, type ProductPage } from '../navigation'
import { AppSidebar } from './AppSidebar'
import { SubNav } from './SubNav'

interface AppShellProps {
  activePage: ProductPage
  onNavigate: (page: ProductPage) => void
  children: ReactNode
}

export function AppShell({ activePage, onNavigate, children }: AppShellProps) {
  const subnav = subnavForPage(activePage)
  return (
    <div className="app-layout">
      <AppSidebar activePage={activePage} onNavigate={onNavigate} />
      <div className="app-main">
        <header className="app-topbar">
          <h2 className="app-topbar-title">{SECTION_LABELS[PAGE_TO_SECTION[activePage]]}</h2>
        </header>
        {subnav ? <SubNav items={subnav} activePage={activePage} onNavigate={onNavigate} /> : null}
        <div className="app-content">
          <div className="app-shell">{children}</div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run — PASS, then commit**

```bash
npx vitest run src/components/AppShell.test.tsx
git add web_v2/src/components/AppShell.tsx web_v2/src/components/AppShell.test.tsx
git commit -m "feat(web): AppShell — sidebar + topbar + subnav layout wrapper"
```

---

### Task 6: Rewire `App.tsx` to the shell

**Files:**
- Modify: `web_v2/src/App.tsx` (imports at 67–74; `renderSyncPanel` at 489–504; `renderDrilldownPanels` at 506–534; `renderStatsContent` at 536–605; entire render section at 901–1127)

- [ ] **Step 1: Update imports**

Remove lines 67 and 74:

```tsx
import { ProductNav } from './components/ProductNav'
import type { ProductPage } from './components/ProductNav'
```

Add:

```tsx
import { AppShell } from './components/AppShell'
import { SubNav } from './components/SubNav'
import { ANALYSIS_TABS, type ProductPage } from './navigation'
```

- [ ] **Step 2: Simplify `renderSyncPanel` wrapper** (line 489–504) — it will now live inside shell content, so drop the page-width wrapper class:

```tsx
  function renderSyncPanel() {
    return syncStatus ? (
      <div className="sync-panel-shell">
        <SyncStatusPanel
          status={syncStatus}
          onSync={handleRunSync}
          syncState={syncRunState}
          onSaveSession={handleSaveGarminSession}
          sessionSaveState={sessionSaveState}
          sessionSaveError={sessionSaveError}
          adminTokenValue={adminToken}
          onAdminTokenChange={handleAdminTokenChange}
        />
      </div>
    ) : null
  }
```

- [ ] **Step 3: Change `renderDrilldownPanels` outer wrapper** (line 509) from `<div className="app-shell">` to a fragment `<>` (closing `</div>` at line 532 → `</>`). The shell already provides the width container.

- [ ] **Step 4: Add inner analysis tabs in `renderStatsContent`** — replace lines 537–540:

```tsx
    if (activePage === 'courses') return <CourseStats data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
    if (activePage === 'holes' || activePage === 'clubs' || activePage === 'issues') {
      const stats =
        activePage === 'holes' ? (
          <HoleStats data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
        ) : activePage === 'clubs' ? (
          <ClubStats data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
        ) : (
          <IssueStats data={data} onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)} />
        )
      return (
        <>
          <SubNav items={ANALYSIS_TABS} activePage={activePage} onNavigate={navigate} variant="inner" label="Analysis dimensions" />
          {stats}
        </>
      )
    }
```

- [ ] **Step 5: Replace the whole render section (current lines 901–1127) with a `renderActivePage()` helper + a single AppShell return.** Exact new code:

```tsx
  function renderActivePage() {
    if (overviewState.status === 'loading') {
      return (
        <section className="panel empty-state">
          <h1>Loading history</h1>
        </section>
      )
    }

    if (overviewState.status === 'error') {
      return (
        <>
          {renderSyncPanel()}
          <section className="panel empty-state">
            <h1>History API unavailable</h1>
            <p>{overviewState.message}</p>
            <button type="button" onClick={() => void refreshOverviewState()}>
              Retry history
            </button>
          </section>
        </>
      )
    }

    if (activePage === 'rounds') {
      if (roundsState.status === 'ready') {
        return (
          <>
            <HistoryTimeline
              data={roundsState.data}
              filters={roundsFilters}
              onFilterChange={(next) => {
                setRoundsFilters(next)
                void loadRoundsState(next)
              }}
              onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
              onOpenRoundDetail={(roundRef) => void handleSelectRoundDetail(roundRef)}
            />
            {renderDrilldownPanels()}
          </>
        )
      }
      if (roundsState.status === 'error') {
        return (
          <section className="panel empty-state">
            <h1>Rounds unavailable</h1>
            <p>{roundsState.message}</p>
            <button type="button" onClick={() => void loadRoundsState()}>
              Retry rounds
            </button>
          </section>
        )
      }
      return (
        <section className="panel empty-state">
          <h1>Loading rounds</h1>
        </section>
      )
    }

    if (statsPages.includes(activePage)) {
      if (statsState.status === 'ready') {
        return (
          <>
            {renderStatsContent(statsState.data)}
            <HistoryDrilldownPanel
              state={drilldownState}
              onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
              onRetrySource={(sourceRef) => void handleSelectSourceRef(sourceRef)}
              onCreateAnnotationForSource={handleCreateAnnotationForSource}
            />
            {holeEvidenceState.status === 'idle' ? null : (
              <HoleEvidencePanel
                state={holeEvidenceState}
                ensureState={geometryEnsureState}
                onEnsureGeometry={(target) => void handleEnsureHoleGeometry(target)}
              />
            )}
          </>
        )
      }
      if (statsState.status === 'error') {
        return (
          <section className="panel empty-state">
            <h1>History stats unavailable</h1>
            <p>{statsState.message}</p>
            <button type="button" onClick={() => void loadStatsState()}>
              Retry history stats
            </button>
          </section>
        )
      }
      return (
        <section className="panel empty-state">
          <h1>Loading history stats</h1>
        </section>
      )
    }

    if (activePage === 'prep') {
      return <CoursePrepPanel />
    }

    if (activePage === 'caddie') {
      return (
        <CaddiePage
          decisionState={decisionState}
          auditState={decisionAuditState}
          weatherState={weatherState}
          contextState={caddieContextState}
          mediaState={mediaState}
          onRequestDecision={(request) => void handleRequestCaddieDecision(request)}
          onCreateAudit={(decision, actualShot) => void handleCreateDecisionAudit(decision, actualShot)}
          onLoadWeather={(params) => void handleLoadWeather(params)}
          onLoadCaddieContext={(params) => void handleLoadCaddieContext(params)}
          onLoadMediaContext={(target) => void handleLoadMediaContext(target)}
          onAttachMedia={handleAttachMedia}
          onAnalyzeMedia={(mediaId) => void handleAnalyzeMedia(mediaId)}
          onRedactMedia={(mediaId) => void handleRedactMedia(mediaId)}
          onConfirmVisionFinding={(findingId, confirmationState) => void handleConfirmVisionFinding(findingId, confirmationState)}
          onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
          selectedSourceRef={selectedCaddieSourceRef}
        />
      )
    }

    if (activePage === 'settings') {
      return (
        <SettingsPage
          onNavigate={navigate}
          settings={productSettingsState.status === 'ready' ? productSettingsState.data : null}
          settingsError={productSettingsState.status === 'error' ? productSettingsState.message : null}
        />
      )
    }

    if (activePage === 'corrections') {
      if (annotationsState.status === 'ready') {
        return (
          <CorrectionsPage
            key={correctionTarget ? `${correctionTarget.targetType}:${correctionTarget.targetId}` : 'manual-corrections'}
            data={annotationsState.data}
            initialTarget={correctionTarget ?? undefined}
            onCreateAnnotation={handleCreateAnnotation}
          />
        )
      }
      if (annotationsState.status === 'error') {
        return (
          <section className="panel empty-state">
            <h1>Corrections unavailable</h1>
            <p>{annotationsState.message}</p>
          </section>
        )
      }
      return (
        <section className="panel empty-state">
          <h1>Loading corrections</h1>
        </section>
      )
    }

    return (
      <>
        <HistoryOverview
          data={overviewState.data}
          onSelectRef={(sourceRef) => void handleSelectSourceRef(sourceRef)}
          onOpenRoundDetail={(roundRef) => void handleSelectRoundDetail(roundRef)}
        />
        {renderDrilldownPanels()}
      </>
    )
  }

  return (
    <AppShell activePage={activePage} onNavigate={navigate}>
      {renderActivePage()}
    </AppShell>
  )
```

Notes: the global `renderSyncPanel()` calls disappear from every happy path (the sync panel still renders inside the `sync-quality` workspace at lines 571–582, and on the overview error screen above so the admin-token recovery flow keeps working). The `caddie` branch no longer renders `<CoursePrepPanel />` — it moved to the new `prep` branch.

- [ ] **Step 6: Type-check** — `HistoryOverview`/`HistoryTimeline` still declare `onNavigate`; that's removed in Task 7, so run only the compiler for now and expect exactly these two prop errors (missing required `onNavigate` on `HistoryTimeline`):

```bash
npx tsc -b 2>&1 | head -20
```
Expected: error(s) only about `onNavigate` on HistoryTimeline usage. Anything else: fix before proceeding.

- [ ] **Step 7: Commit (compiles after Task 7; commit both together if you prefer atomicity — otherwise commit now with the known-red note skipped)**. Preferred: proceed to Task 7 and commit jointly.

---

### Task 7: Strip internal nav from `HistoryOverview` / `HistoryTimeline`

**Files:**
- Modify: `web_v2/src/components/HistoryOverview.tsx` (lines 1–23: imports, props, wrapper)
- Modify: `web_v2/src/components/HistoryTimeline.tsx` (lines 1–25: imports, props, wrapper)
- Modify: `web_v2/src/components/HistoryOverview.test.tsx` (delete nav assertions at lines 70–74; remove `onNavigate` props in renders)
- Modify: `web_v2/src/components/HistoryTimeline.test.tsx` (delete line 43 `'Overview'` button assertion; remove `onNavigate` props in renders)

- [ ] **Step 1: HistoryOverview — remove ProductNav + onNavigate**

Line 4: delete `import { ProductNav, type ProductPage } from './ProductNav'`.
Props interface: delete `onNavigate?: (page: ProductPage) => void`.
Function signature: `export function HistoryOverview({ data, onSelectRef, onOpenRoundDetail }: HistoryOverviewProps) {`.
Render: replace `<main className="app-shell">` with `<>`, delete line 23 `<ProductNav activePage="overview" onNavigate={onNavigate} />`, and replace the closing `</main>` with `</>`.

- [ ] **Step 2: HistoryTimeline — same surgery**

Line 2: delete the ProductNav import. Props: delete `onNavigate: (page: ProductPage) => void`. Signature drops `onNavigate`. Replace `<main className="app-shell">`/`</main>` with `<>`/`</>` and delete line 25's `<ProductNav … />`.

- [ ] **Step 3: Update the two component test files**

- `HistoryOverview.test.tsx`: delete lines 70–74 (the five `getByRole('button', { name: 'History'|'Rounds'|'Courses'|'Sync & Data Quality'|'Settings' })` assertions). Run `grep -n "onNavigate" src/components/HistoryOverview.test.tsx` and remove the prop from every render call.
- `HistoryTimeline.test.tsx`: delete line 43 (`'Overview'` button). Same `onNavigate` grep-and-remove.

- [ ] **Step 4: Verify compile + these test files pass**

```bash
npx tsc -b
npx vitest run src/components/HistoryOverview.test.tsx src/components/HistoryTimeline.test.tsx
```
Expected: tsc clean; both test files PASS.

- [ ] **Step 5: Commit Tasks 6+7 together**

```bash
git add web_v2/src/App.tsx web_v2/src/components/HistoryOverview.tsx web_v2/src/components/HistoryTimeline.tsx web_v2/src/components/HistoryOverview.test.tsx web_v2/src/components/HistoryTimeline.test.tsx
git commit -m "feat(web): render every page inside AppShell; nav lives only in the shell"
```

---

### Task 8: Update `App.test.tsx` to the new IA

**Files:**
- Modify: `web_v2/src/App.test.tsx` (~27 nav-related call sites)

**Navigation mapping (old one-click → new clicks):**

| Old assertion/click | New interaction |
|---|---|
| button `History` | sidebar `历史` (lands on 趋势总览) |
| button `Rounds` | `历史` → subnav `球局` |
| button `Courses` | `历史` → `球场` |
| button `Holes` | `历史` → `强弱分析` |
| button `Clubs` | `历史` → `强弱分析` → inner `按杆` |
| button `Issues` | `历史` → `强弱分析` → inner `问题` |
| button `Reports` | `历史` → `报告` |
| button `Caddie` | sidebar `实战` |
| button `Corrections` | sidebar `设置` → `订正` |
| button `Sync & Data Quality` | sidebar `设置` (default sub IS sync) |
| button `Settings` | sidebar `设置` → `后端配置` |
| sync-panel text (`Garmin CN`, `ready`, `Review history`) asserted on overview | navigate to `设置` first — the panel no longer renders on product pages |

- [ ] **Step 1: Run the suite to enumerate failures**

```bash
npx vitest run src/App.test.tsx 2>&1 | tail -40
```
Expected: multiple failures, all "Unable to find … role button with name 'History'/…" or missing `Garmin CN` on overview.

- [ ] **Step 2: Rewrite the main navigation test block (currently lines ~974–989).** Worked example — replace:

```tsx
    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    expect(await screen.findByText('Garmin CN')).toBeInTheDocument()
    expect(screen.getAllByText('ready').length).toBeGreaterThan(0)
    expect(screen.getByText('Overview')).toBeInTheDocument()
    ;['History', 'Rounds', 'Courses', 'Holes', 'Clubs', 'Issues', 'Caddie', 'Corrections', 'Sync & Data Quality', 'Reports', 'Settings'].forEach(
      (label) => expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    expect(screen.queryByRole('button', { name: 'Stats' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Quality' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Rounds' }))
```

with:

```tsx
    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '概览' })).toHaveAttribute('aria-current', 'page')
    ;['概览', '历史', '备战', '实战', '设置'].forEach(
      (label) => expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    expect(screen.queryByRole('button', { name: 'Overview' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sync & Data Quality' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    expect(await screen.findByText('Garmin CN')).toBeInTheDocument()
    expect(screen.getAllByText('ready').length).toBeGreaterThan(0)

    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    ;['趋势总览', '球局', '强弱分析', '球场', '报告'].forEach(
      (label) => expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    await userEvent.click(screen.getByRole('button', { name: '球局' }))
```

(The follow-up assertions — heading `Rounds`, `May 2026`, fetch calls — stay unchanged.)

- [ ] **Step 3: Apply the mapping table to every remaining failure.** Known call sites: lines ~1310 & ~1338 (`Settings` → `设置`+`后端配置`), ~1372 & ~1416 (`Reports` → `历史`+`报告`), ~1445 (`Sync & Data Quality` → `设置`), ~1761 & ~1867 (`Caddie` → `实战`). For each, the heading expectation that follows (e.g. `findByRole('heading', { name: 'Settings' })`) is unchanged — only the click path changes. Re-run after each fix:

```bash
npx vitest run src/App.test.tsx 2>&1 | tail -15
```

- [ ] **Step 4: Full unit suite green**

```bash
npm test -- --run
```
Expected: all files pass (including CaddiePage/CoursePrepPanel standalone tests, untouched).

- [ ] **Step 5: Commit**

```bash
git add web_v2/src/App.test.tsx
git commit -m "test(web): App navigation tests follow the sidebar + subnav IA"
```

---

### Task 9: Delete `ProductNav`, migrate type imports

**Files:**
- Delete: `web_v2/src/components/ProductNav.tsx`
- Modify: `web_v2/src/components/SettingsPage.tsx` (line 1)

- [ ] **Step 1: SettingsPage type import** — replace line 1:

```tsx
import type { ProductPage } from '../navigation'
```

- [ ] **Step 2: Delete the file and prove zero references**

```bash
git rm web_v2/src/components/ProductNav.tsx
grep -rn "ProductNav" web_v2/src web_v2/e2e || echo "no references"
```
Expected: `no references`.

- [ ] **Step 3: Compile + lint + commit**

```bash
npx tsc -b && npm run lint
git add -A web_v2/src
git commit -m "refactor(web): delete ProductNav; ProductPage type lives in navigation.ts"
```

---

### Task 10: Update the Playwright smoke to the new IA

**Files:**
- Modify: `web_v2/e2e/history-visual.smoke.spec.ts` (the screen loop + `Review history` assertion in the test body; mocks unchanged)

- [ ] **Step 1: Replace the `for (const screen of [...])` loop and the trailing `Review history` assertion** with:

```ts
  await page.getByRole('button', { name: '历史' }).click()
  for (const [tab, heading] of [
    ['趋势总览', 'Statistics Overview'],
    ['球局', 'Rounds'],
    ['强弱分析', 'Hole Stats'],
    ['球场', 'Course Stats'],
    ['报告', 'Reports'],
  ] as const) {
    await page.getByRole('button', { name: tab }).click()
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
    await assertNoViewportOverflow(page)
    await expect(page.locator('text=/unavailable|failed/i')).toHaveCount(0)
  }

  await page.getByRole('button', { name: '强弱分析' }).click()
  await page.getByRole('button', { name: '按杆' }).click()
  await expect(page.getByRole('heading', { name: 'Club Stats', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '问题' }).click()
  await expect(page.getByRole('heading', { name: 'Issue Stats', exact: true })).toBeVisible()
  await assertNoViewportOverflow(page)

  await page.getByRole('button', { name: '备战' }).click()
  await expect(page.getByRole('heading', { name: '赛前球场攻略' })).toBeVisible()
  await assertNoViewportOverflow(page)

  await page.getByRole('button', { name: '实战' }).click()
  await expect(page.getByRole('heading', { name: 'Caddie', exact: true })).toBeVisible()
  await assertNoViewportOverflow(page)

  await page.getByRole('button', { name: '设置' }).click()
  await expect(page.getByRole('heading', { name: 'Sync & Data Quality', exact: true })).toBeVisible()
  await expect(page.getByText('Review history')).toBeVisible()
  await page.getByRole('button', { name: '订正' }).click()
  await expect(page.getByRole('heading', { name: 'Corrections', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '后端配置' }).click()
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible()
  await assertNoViewportOverflow(page)
  await expect(failedResponses).toEqual([])
  await expect(browserErrors).toEqual([])
  await captureSmokeScreenshot(page, testInfo, 'settings')
```

(Keep the existing overview block at the top and the helpers/mocks untouched. `赛前球场攻略` is CoursePrepPanel's existing `<h2>`; it fetches only on submit, so no new route mocks are needed.)

- [ ] **Step 2: Run e2e locally**

```bash
npx playwright install --with-deps chromium 2>/dev/null || npx playwright install chromium
npm run test:e2e
```
Expected: 1 passed (webServer auto-starts vite on 5174).

- [ ] **Step 3: Commit**

```bash
git add web_v2/e2e/history-visual.smoke.spec.ts
git commit -m "test(e2e): smoke walks the sidebar + subnav IA incl. 备战/强弱分析"
```

---

### Task 11: Full verification + push

- [ ] **Step 1: The exact CI-frontend sequence**

```bash
cd web_v2
npm test -- --run && npm run lint && npm run build && npm run test:e2e
```
Expected: every stage passes.

- [ ] **Step 2: Repo-wide sanity** (backend untouched — prove it)

```bash
git -C .. diff --stat integration/v2...HEAD -- ':!web_v2' ':!docs'
```
Expected: empty (only web_v2 + docs changed).

- [ ] **Step 3: Push branch and open PR** (gh CLI absent — use the GitHub API with env `GH_TOKEN`)

```bash
git push -u origin superpowers/web-redesign-w1a
```
PR: base `integration/v2`, head `superpowers/web-redesign-w1a`, title `feat(web): W1a — product shell (Chinese sidebar IA + design tokens)`. Body summarizes: shell components, IA mapping table, sync-panel demotion, zero feature changes, CI sequence run locally. The user merges.

---

## Self-Review (done at plan-writing time)

- **Spec coverage:** D1 (sidebar) → Tasks 3/6; §4 IA table → navigation.ts + App rewiring (every old page has a home; verified against the table above); §6 tokens → Task 2; D4 (备战 first-class) → prep branch; plumbing demotion → sync-panel policy + settings subnav. 概览/历史 new content + range param + D2/D3 are explicitly W1b (not in this plan).
- **Placeholders:** none — every step has full code or exact commands.
- **Type consistency:** `ProductPage` keeps its 12 ids + new `'prep'`; `SubNavItem.activeFor` used by SubNav and navigation tests consistently; `AppShell` props match App usage.
- **Known interim quirks (accepted):** page h1s stay English until W1b; analysis = three old pages behind inner tabs until W1b merges them; dead `.topbar` CSS left in place (W1b cleanup).
