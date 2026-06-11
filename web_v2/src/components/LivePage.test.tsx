import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import type { CourseSearchResponse, MobileCourseOptionsResponse } from '../types'
import { LivePage } from './LivePage'

function courseOptionsFixture(): MobileCourseOptionsResponse {
  return {
    schema: 'ai-caddie-mobile-course-options-v1',
    dataMode: 'fixture',
    total: 2,
    courses: [
      {
        globalId: 31795,
        courseKey: 'black_knight',
        name: 'Black Knight B/C',
        roundCount: 2,
        holes: 18,
        geometryCoverage: 'partial',
        sourceRefs: ['900001'],
      },
      {
        globalId: 31870,
        name: '观澜湖·奥拉沙宝场',
        roundCount: 9,
        holes: 18,
        geometryCoverage: 'ready',
        sourceRefs: ['900002'],
      },
    ],
    emptyState: null,
    generatedAt: '2026-06-05T08:00:00Z',
  }
}

function renderLive(overrides: Partial<ComponentProps<typeof LivePage>> = {}) {
  const onSearchCourses = vi.fn(async (): Promise<CourseSearchResponse> => ({
    schema: 'ai-caddie-course-search-v1',
    query: '观澜湖',
    matches: [{ globalId: 99999, name: '观澜湖·世界杯场', holes: 18, city: '深圳', province: '广东', ratio: 0.92 }],
  }))
  const onRequestDecision = vi.fn()
  const props: ComponentProps<typeof LivePage> = {
    courseOptions: courseOptionsFixture(),
    adminToken: 'admin-secret',
    onSearchCourses,
    recentRounds: [],
    caddieProps: {
      decisionState: { status: 'idle' },
      onRequestDecision,
      selectedSourceRef: '900042:3',
    },
    ...overrides,
  }
  const view = render(<LivePage {...props} />)
  return { onSearchCourses, onRequestDecision, view }
}

function liveTabs() {
  return within(screen.getByRole('navigation', { name: '实战页签' }))
}

describe('LivePage tabs', () => {
  it('defaults to 决策沙盘: course-pick entry heading, finder wiring, and no CaddiePage', () => {
    renderLive()

    expect(liveTabs().getByRole('button', { name: '决策沙盘' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('heading', { name: '选择球场开始模拟' })).toBeInTheDocument()
    expect(screen.getByLabelText('搜索球场')).toBeInTheDocument()
    // courseOptions flow through to the finder's 常打球场 cards.
    expect(screen.getByText('Black Knight B/C')).toBeInTheDocument()
    // The legacy dashboard must stay OFF the default tab.
    expect(screen.queryByRole('heading', { name: 'Caddie' })).not.toBeInTheDocument()
  })

  it('hands the search query to onSearchCourses and lists matches on the sandbox entry', async () => {
    const { onSearchCourses } = renderLive()

    await userEvent.type(screen.getByLabelText('搜索球场'), '观澜湖')
    await userEvent.click(screen.getByRole('button', { name: '搜索' }))

    expect(onSearchCourses).toHaveBeenCalledWith('观澜湖')
    expect(await screen.findByText('观澜湖·世界杯场')).toBeInTheDocument()
  })

  it('最近回放 shows the placeholder until T2 lands', async () => {
    renderLive()

    await userEvent.click(liveTabs().getByRole('button', { name: '最近回放' }))

    expect(liveTabs().getByRole('button', { name: '最近回放' })).toHaveAttribute('aria-current', 'page')
    expect(liveTabs().getByRole('button', { name: '决策沙盘' })).not.toHaveAttribute('aria-current')
    expect(screen.getByText('…')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '选择球场开始模拟' })).not.toBeInTheDocument()
  })

  it('完整工具 renders the verbatim CaddiePage; 决策沙盘 returns to the entry', async () => {
    renderLive()

    await userEvent.click(liveTabs().getByRole('button', { name: '完整工具' }))

    expect(liveTabs().getByRole('button', { name: '完整工具' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('heading', { name: 'Caddie' })).toBeInTheDocument()
    // The props bundle is spread through untouched: selectedSourceRef reaches
    // CaddiePage's Source ref input exactly as it did when App rendered it.
    expect(screen.getByLabelText('Source ref')).toHaveValue('900042:3')
    expect(screen.queryByRole('heading', { name: '选择球场开始模拟' })).not.toBeInTheDocument()

    await userEvent.click(liveTabs().getByRole('button', { name: '决策沙盘' }))

    expect(screen.getByRole('heading', { name: '选择球场开始模拟' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Caddie' })).not.toBeInTheDocument()
  })
})
