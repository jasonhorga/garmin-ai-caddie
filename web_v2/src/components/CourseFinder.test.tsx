import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { CourseSearchResponse, MobileCourseOptionsResponse } from '../types'
import { CourseFinder } from './CourseFinder'

function courseOptionsFixture(): MobileCourseOptionsResponse {
  return {
    schema: 'ai-caddie-mobile-course-options-v1',
    dataMode: 'fixture',
    total: 4,
    courses: [
      { globalId: 31795, name: '黑骑士 B/C', roundCount: 2, holes: 18, geometryCoverage: 'partial', sourceRefs: ['900001'] },
      { globalId: 31870, name: '观澜湖·奥拉沙宝场', roundCount: 9, holes: 18, geometryCoverage: 'ready', sourceRefs: ['900002'] },
      { globalId: 40001, name: '翡翠湖国际高尔夫', roundCount: 5, holes: 18, geometryCoverage: 'partial', sourceRefs: ['900003'] },
      { globalId: 40002, name: '深圳沙河', roundCount: 7, holes: 18, geometryCoverage: 'missing', sourceRefs: ['900004'] },
    ],
    emptyState: null,
    generatedAt: '2026-06-05T08:00:00Z',
  }
}

function searchResponse(): CourseSearchResponse {
  return {
    schema: 'ai-caddie-course-search-v1',
    query: '观澜湖',
    matches: [
      { globalId: 31870, name: '观澜湖·奥拉沙宝场', holes: 18, city: '深圳', province: '广东', ratio: 0.92 },
      { globalId: 31999, name: '观澜湖·世界杯场', holes: 18, city: '深圳', province: '广东', ratio: 0.88 },
    ],
  }
}

function renderFinder(overrides: Partial<Parameters<typeof CourseFinder>[0]> = {}) {
  const onSearchCourses = vi.fn(async () => searchResponse())
  const onSelectCourse = vi.fn()
  render(
    <CourseFinder
      courseOptions={courseOptionsFixture()}
      onSearchCourses={onSearchCourses}
      onSelectCourse={onSelectCourse}
      {...overrides}
    />,
  )
  return { onSearchCourses, onSelectCourse }
}

describe('CourseFinder', () => {
  it('renders the default heading and sub copy', () => {
    renderFinder()

    expect(screen.getByRole('heading', { name: '想备哪场?' })).toBeInTheDocument()
    expect(screen.getByText('搜索球场,或从常打球场直接开备战。')).toBeInTheDocument()
  })

  it('renders custom heading and sub copy when provided', () => {
    renderFinder({ heading: '选择球场开始备战', sub: '先挑一个球场。' })

    expect(screen.getByRole('heading', { name: '选择球场开始备战' })).toBeInTheDocument()
    expect(screen.getByText('先挑一个球场。')).toBeInTheDocument()
    expect(screen.queryByText('想备哪场?')).not.toBeInTheDocument()
  })

  it('sorts frequent courses by round count, caps them at three, and selects the clicked course', async () => {
    const { onSelectCourse } = renderFinder()

    const prepButtons = screen.getAllByRole('button', { name: /^去备战 / })
    expect(prepButtons.map((button) => button.getAttribute('aria-label'))).toEqual([
      '去备战 观澜湖·奥拉沙宝场',
      '去备战 深圳沙河',
      '去备战 翡翠湖国际高尔夫',
    ])
    expect(screen.getByText('打过 9 次')).toBeInTheDocument()
    expect(screen.queryByText('黑骑士 B/C')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '去备战 深圳沙河' }))
    expect(onSelectCourse).toHaveBeenCalledWith(40002, '深圳沙河')
  })

  it('hides the frequent block when courseOptions is null', () => {
    renderFinder({ courseOptions: null })

    expect(screen.queryByText('常打球场')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^去备战 / })).not.toBeInTheDocument()
    expect(screen.getByLabelText('搜索球场')).toBeInTheDocument()
  })

  it('search submit trims the query, calls onSearchCourses, and renders matches with meta', async () => {
    const { onSearchCourses } = renderFinder()

    await userEvent.type(screen.getByLabelText('搜索球场'), ' 观澜湖 ')
    await userEvent.click(screen.getByRole('button', { name: '搜索' }))

    expect(onSearchCourses).toHaveBeenCalledWith('观澜湖')
    expect(await screen.findByText('观澜湖·世界杯场')).toBeInTheDocument()
    expect(screen.getAllByText('深圳 · 18洞').length).toBe(2)
  })

  it('picking a search match selects that course with its name', async () => {
    const { onSelectCourse } = renderFinder()

    await userEvent.type(screen.getByLabelText('搜索球场'), '观澜湖{Enter}')
    await userEvent.click(await screen.findByRole('button', { name: /观澜湖·世界杯场/ }))

    expect(onSelectCourse).toHaveBeenCalledWith(31999, '观澜湖·世界杯场')
  })

  it('does not search when the query is blank', async () => {
    const { onSearchCourses } = renderFinder()

    await userEvent.type(screen.getByLabelText('搜索球场'), '   {Enter}')

    expect(onSearchCourses).not.toHaveBeenCalled()
  })

  it('shows 搜索中… while the search is in flight', async () => {
    renderFinder({ onSearchCourses: vi.fn(() => new Promise<CourseSearchResponse>(() => {})) })

    await userEvent.type(screen.getByLabelText('搜索球场'), '观澜湖{Enter}')

    expect(await screen.findByText('搜索中…')).toBeInTheDocument()
  })

  it('shows 搜索失败 with the error message when the search rejects', async () => {
    renderFinder({ onSearchCourses: vi.fn(async () => Promise.reject(new Error('boom'))) })

    await userEvent.type(screen.getByLabelText('搜索球场'), '观澜湖{Enter}')

    expect(await screen.findByText('搜索失败:boom')).toBeInTheDocument()
  })

  it('shows 没有找到球场 when the search returns no matches', async () => {
    renderFinder({
      onSearchCourses: vi.fn(async () => ({
        schema: 'ai-caddie-course-search-v1' as const,
        query: '不存在',
        matches: [],
      })),
    })

    await userEvent.type(screen.getByLabelText('搜索球场'), '不存在{Enter}')

    expect(await screen.findByText('没有找到球场')).toBeInTheDocument()
  })

  it('discards a stale search response that resolves after a newer search', async () => {
    let resolveFirst!: (value: CourseSearchResponse) => void
    const first = new Promise<CourseSearchResponse>((resolve) => {
      resolveFirst = resolve
    })
    const onSearchCourses = vi
      .fn<(name: string) => Promise<CourseSearchResponse>>()
      .mockImplementationOnce(() => first)
      .mockImplementationOnce(async () => searchResponse())
    renderFinder({ onSearchCourses })

    await userEvent.type(screen.getByLabelText('搜索球场'), '旧搜索{Enter}')
    await userEvent.clear(screen.getByLabelText('搜索球场'))
    await userEvent.type(screen.getByLabelText('搜索球场'), '观澜湖{Enter}')
    expect(await screen.findByText('观澜湖·世界杯场')).toBeInTheDocument()

    resolveFirst({
      schema: 'ai-caddie-course-search-v1',
      query: '旧搜索',
      matches: [{ globalId: 50000, name: '旧球场', holes: 18, city: '北京', province: '北京', ratio: 0.5 }],
    })
    await first

    expect(screen.getByText('观澜湖·世界杯场')).toBeInTheDocument()
    expect(screen.queryByText('旧球场')).not.toBeInTheDocument()
  })
})
