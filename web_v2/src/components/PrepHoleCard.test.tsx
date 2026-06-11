import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CoursePrepClub, CoursePrepHole, CoursePrepOverlay } from '../types'
import { PrepHoleCard } from './PrepHoleCard'

const overlay: CoursePrepOverlay = {
  w: 200,
  h: 200,
  ppm: 1,
  ln: 200,
  route: [
    [0, 0, 0],
    [100, 0, 100],
    [100, 100, 200],
  ],
}

const clubs: CoursePrepClub[] = [{ name: '1W', m: 200, yd: 219 }]

function mappedHole(overrides: Partial<CoursePrepHole> = {}): CoursePrepHole {
  return {
    hole: 1,
    par: 4,
    par_source: 'courseview',
    blue_yards: 219,
    route_len_m: 200,
    route: [
      [0, 0, 0],
      [100, 0, 100],
      [100, 100, 200],
    ],
    geometryCoverage: 'ready',
    sourceRefs: ['course:31870', 'geometry:31870:1'],
    missingData: [],
    candidateRoutes: [{ id: 'stock', club: '1W', carryM: 200, riskScore: 1 }],
    carryTargets: [{ kind: 'landing', distanceM: 80 }],
    steps: [{ club: null, note: '开球落点约 87y' }],
    cautions: [],
    landing_m: 80,
    tee_club: null,
    hazards: { water_carry: [[100, 130]], bunkers: [[160, 10]] },
    map: { image: 'data:image/jpeg;base64,', overlay },
    ...overrides,
  }
}

function unmappedHole(): CoursePrepHole {
  return {
    hole: 2,
    par: 4,
    par_source: 'estimate',
    blue_yards: 0,
    route_len_m: 0,
    route: [],
    geometryCoverage: 'missing',
    sourceRefs: ['course:31870', 'geometry:31870:2'],
    missingData: [{ label: 'geometry', reason: 'prodgeometry geometry is missing for this hole' }],
    candidateRoutes: [],
    carryTargets: [],
    steps: [],
    cautions: [],
    landing_m: null,
    tee_club: null,
    hazards: { water_carry: [], bunkers: [] },
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PrepHoleCard', () => {
  // Migrated from CoursePrepPanel.test: map overlay render with route-based
  // hazard yardages from the initial landing position, zh copy, no uncertainty.
  it('renders the map overlay with par badge, hazard yardages, steps, and route options', () => {
    render(<PrepHoleCard hole={mappedHole()} clubs={clubs} />)

    expect(screen.getByText('Par 来源：CourseView')).toBeInTheDocument()
    expect(screen.getByText('219y 蓝T')).toBeInTheDocument()
    expect(screen.getByText('水 进22y / 过55y')).toBeInTheDocument()
    expect(screen.getByText('沙87y')).toBeInTheDocument()
    expect(screen.getByText(/距T 87y · 到果岭 131y/)).toBeInTheDocument()
    expect(screen.getByText('开球落点约 87y')).toBeInTheDocument()
    expect(screen.getByText('stock 219y')).toBeInTheDocument()
    expect(screen.getByText('course:31870')).toBeInTheDocument()
    expect(screen.queryByText(/碳/)).not.toBeInTheDocument()
    expect(screen.queryByText(/\?/)).not.toBeInTheDocument()
  })

  // Migrated from CoursePrepPanel.test: club chip snaps the ball to club carry.
  it('snaps the ball to a club carry distance when its chip is clicked', async () => {
    render(<PrepHoleCard hole={mappedHole()} clubs={clubs} />)

    await userEvent.click(screen.getByRole('button', { name: '1W 219y' }))

    expect(screen.getByText('水已过')).toBeInTheDocument()
    expect(screen.getByText('沙已过')).toBeInTheDocument()
    expect(screen.queryByText('沙44y')).not.toBeInTheDocument()
  })

  it('updates the yardage readout when the ball is dragged on the overlay', () => {
    const { container } = render(<PrepHoleCard hole={mappedHole()} clubs={clubs} />)
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
    vi.spyOn(svg!, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: 200,
      bottom: 200,
      width: 200,
      height: 200,
      toJSON: () => ({}),
    } as DOMRect)

    fireEvent.pointerDown(svg!, { clientX: 100, clientY: 0 })

    expect(screen.getByText(/距T 109y · 到果岭 109y/)).toBeInTheDocument()
  })

  it('lists cautions when the hole has them', () => {
    render(<PrepHoleCard hole={mappedHole({ cautions: ['水障碍距开球 109y,留意开球落点'] })} clubs={clubs} />)

    expect(screen.getByText('水障碍距开球 109y,留意开球落点')).toBeInTheDocument()
  })

  // Migrated from CoursePrepPanel.test: holes without geometry degrade gracefully.
  it('shows the missing-geometry fallback and zh missing-data badge when there is no map', () => {
    const { container } = render(<PrepHoleCard hole={unmappedHole()} clubs={clubs} />)

    expect(screen.getByText('（此洞暂无几何图）')).toBeInTheDocument()
    expect(screen.getByText('几何缺失')).toBeInTheDocument()
    expect(screen.queryByText(/missing/)).not.toBeInTheDocument()
    expect(screen.getByLabelText('第2洞缺失数据')).toBeInTheDocument()
    expect(container.querySelector('svg')).toBeNull()
  })

  it('unmapped missing-data labels fall back to {label}缺失', () => {
    const hole = unmappedHole()
    hole.missingData = [{ label: 'hazards', reason: 'prodgeometry hazard file missing' }, { reason: 'no label' }]
    render(<PrepHoleCard hole={hole} clubs={clubs} />)

    expect(screen.getByText('hazards缺失')).toBeInTheDocument()
    expect(screen.getByText('数据缺失')).toBeInTheDocument()
  })

  it('labels the route-option and source-ref chip groups in zh', () => {
    render(<PrepHoleCard hole={mappedHole()} clubs={clubs} />)

    expect(screen.getByLabelText('第1洞路线选项')).toBeInTheDocument()
    expect(screen.getByLabelText('第1洞数据来源')).toBeInTheDocument()
  })

  it('renders your-shot scatter dots colored by shot type with white outline, club/round titles and the legend', () => {
    const hole = mappedHole({
      yourShots: [
        { x: 50, y: 10, club: '1W', shotType: 'TEE', roundId: '900101' },
        { x: 90, y: 40, club: '7I', shotType: 'APPROACH', roundId: '900102' },
        { x: 60, y: 20, club: null, shotType: 'TEE', roundId: '900103' },
      ],
    })
    const { container } = render(<PrepHoleCard hole={hole} clubs={clubs} />)

    const dots = Array.from(container.querySelectorAll('circle[r="4.5"]'))
    expect(dots).toHaveLength(3)
    // APPROACH is --eagle (deep blue distinguishable on water); TEE stays --green.
    expect(dots.map((dot) => dot.getAttribute('fill'))).toEqual(['var(--green)', 'var(--eagle)', 'var(--green)'])
    expect(dots.every((dot) => dot.getAttribute('fill-opacity') === '0.7')).toBe(true)
    expect(dots.every((dot) => dot.getAttribute('stroke') === '#fff')).toBe(true)
    expect(dots.every((dot) => dot.getAttribute('stroke-width') === '1.5')).toBe(true)
    expect(dots[0].getAttribute('cx')).toBe('50')
    expect(dots[0].getAttribute('cy')).toBe('10')
    expect(dots.map((dot) => dot.querySelector('title')?.textContent)).toEqual([
      '1W · 900101',
      '7I · 900102',
      '未知杆 · 900103',
    ])

    expect(screen.getByText('你的落点:')).toBeInTheDocument()
    // The legend swatches must carry the SAME colors as their dot kinds — a
    // swapped pair would mislabel every dot on the map.
    const teeSwatch = screen.getByText('开球(落点)').previousElementSibling as HTMLElement
    expect(teeSwatch.style.background).toContain('var(--green)')
    expect(teeSwatch.style.border).toBe('1px solid rgb(68, 68, 85)') // #445, normalized by jsdom
    const approachSwatch = screen.getByText('攻果岭').previousElementSibling as HTMLElement
    expect(approachSwatch.style.background).toContain('var(--eagle)')
    expect(approachSwatch.style.border).toBe('1px solid rgb(68, 68, 85)')
  })

  it('renders no dots and no legend when yourShots is absent or empty', () => {
    const { container, rerender } = render(<PrepHoleCard hole={mappedHole()} clubs={clubs} />)

    expect(container.querySelectorAll('circle[r="4.5"]')).toHaveLength(0)
    expect(screen.queryByText('你的落点:')).not.toBeInTheDocument()

    rerender(<PrepHoleCard hole={mappedHole({ yourShots: [] })} clubs={clubs} />)

    expect(container.querySelectorAll('circle[r="4.5"]')).toHaveLength(0)
    expect(screen.queryByText('你的落点:')).not.toBeInTheDocument()
  })
})
