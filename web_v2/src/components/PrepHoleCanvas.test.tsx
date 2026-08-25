import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { CoursePrepHole } from '../types'
import { PrepHoleCanvas } from './PrepHoleCanvas'

describe('PrepHoleCanvas', () => {
  it('sizes the base image from the route overlay instead of the fallback bitmap', () => {
    const hole = {
      hole: 1,
      par: 4,
      par_source: 'courseview',
      blue_yards: 430,
      route_len_m: 393,
      route: [],
      geometryCoverage: 'ready',
      sourceRefs: [],
      missingData: [],
      candidateRoutes: [],
      carryTargets: [],
      steps: [],
      cautions: [],
      landing_m: 215,
      tee_club: '1D',
      hazards: { water_carry: [], bunkers: [] },
      map: {
        image:
          'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
        overlay: { w: 300, h: 470, ppm: 1, ln: 393, route: [[150, 455, 0], [150, 72, 393]] },
      },
    } as CoursePrepHole

    render(<PrepHoleCanvas hole={hole} cum={0} onCum={vi.fn()} />)

    const canvas = screen.getByLabelText('第1洞球道图')
    expect(canvas.querySelector('.prep-canvas-frame')).toHaveStyle('aspect-ratio: 300 / 470')
  })

  it('surfaces optional club distance provenance while accepting the same legacy shape', () => {
    const hole = {
      hole: 1,
      par: 4,
      par_source: 'courseview',
      blue_yards: 430,
      route_len_m: 393,
      route: [],
      geometryCoverage: 'ready',
      sourceRefs: [],
      missingData: [],
      candidateRoutes: [],
      carryTargets: [],
      steps: [],
      cautions: [],
      landing_m: 215,
      tee_club: '3W',
      hazards: { water_carry: [], bunkers: [] },
      map: { image: undefined, overlay: { w: 300, h: 470, ppm: 1, ln: 393, route: [[150, 455, 0], [150, 72, 393]] } },
    } as CoursePrepHole

    render(
      <PrepHoleCanvas
        hole={hole}
        cum={0}
        onCum={vi.fn()}
        clubs={[{ name: '3W', token: 'wood3', m: 171, yd: 187, distanceSource: 'history_median', sampleSize: 12, confidence: 'medium' }]}
      />,
    )

    const recommendation = screen.getByLabelText('地图推荐球杆')
    expect(recommendation).toHaveAttribute('data-distance-source', 'history_median')
    expect(recommendation).toHaveTextContent('依据 历史中位')
  })

  it('draws factual CourseView vectors without requesting a precise topo early', () => {
    const hole = {
      hole: 1,
      par: 4,
      par_source: 'courseview',
      blue_yards: 430,
      route_len_m: 393,
      route: [[0, 0, 0], [0, 393, 393]],
      geometryCoverage: 'partial',
      sourceRefs: [],
      missingData: [],
      candidateRoutes: [],
      carryTargets: [],
      steps: [],
      cautions: [],
      landing_m: 220,
      tee_club: '1D',
      hazards: {
        water_carry: [[120, 140]],
        bunkers: [],
        details: [{
          kind: 'water', frontM: 120, backM: 140, frontRouteM: 120, backRouteM: 140,
          frontPx: [180, 350], backPx: [180, 330], sideM: 0,
        }],
      },
      holeImageProjection: {
        available: true,
        widthPx: 360,
        heightPx: 560,
        refs: [
          { lat: 30, lon: 120, px: 180, py: 532 },
          { lat: 30, lon: 120.001, px: 300, py: 532 },
          { lat: 30.001, lon: 120, px: 180, py: 412 },
        ],
      },
      greenOutline: {
        available: true,
        source: 'courseData.GreenRadii',
        distanceUnit: null,
        pointsPx: [[170, 30], [190, 30], [180, 15]],
      },
    } as CoursePrepHole

    render(<PrepHoleCanvas hole={hole} cum={0} onCum={vi.fn()} globalId={9876} />)

    const canvas = screen.getByLabelText('第1洞球道图')
    expect(canvas.querySelector('[data-map-fact="course-data-route"]')).toBeInTheDocument()
    expect(canvas.querySelector('[data-map-fact="course-data-water"]')).toBeInTheDocument()
    expect(canvas.querySelector('[data-map-fact="course-data-green"]')).toBeInTheDocument()
    expect(canvas.querySelector('.hole-base-topo')).not.toBeInTheDocument()
    expect(canvas.querySelector('.hole-base')).toHaveClass('is-vector-only')
  })

  it('puts recommendation, green range, and measured obstacle ranges on the precise map', () => {
    const hole = {
      hole: 7,
      par: 4,
      par_source: 'courseview',
      blue_yards: 410,
      route_len_m: 375,
      route: [],
      geometryCoverage: 'ready',
      sourceRefs: [],
      missingData: [],
      candidateRoutes: [],
      carryTargets: [],
      steps: [],
      cautions: [],
      landing_m: 200,
      tee_club: '1D',
      hazards: {
        water_carry: [[120, 150]],
        bunkers: [],
        details: [{
          kind: 'water', frontM: 120, backM: 150, frontRouteM: 120, backRouteM: 150,
          frontPx: [170, 250], backPx: [175, 220], sideM: 0,
        }],
      },
      map: {
        image: 'data:image/png;base64,AAAA',
        overlay: { w: 360, h: 560, ppm: 1, ln: 375, route: [[180, 520, 0], [180, 40, 375]] },
      },
      greenDistances: { available: true, frontM: 345, middleM: 355, backM: 365 },
    } as CoursePrepHole

    render(<PrepHoleCanvas hole={hole} cum={200} onCum={vi.fn()} clubs={[{ name: '1D', m: 220, yd: 241 }]} />)

    const canvas = screen.getByLabelText('第7洞球道图')
    expect(screen.getByLabelText('果岭前中后距离')).toHaveTextContent('中 388')
    expect(Array.from(canvas.querySelectorAll('text')).some((node) => node.textContent?.includes('水已过'))).toBe(true)
    expect(Array.from(canvas.querySelectorAll('text')).some((node) => node.textContent === 'T')).toBe(true)
    expect(Array.from(canvas.querySelectorAll('text')).some((node) => node.textContent === '1D')).toBe(true)
    expect(screen.getByLabelText('地图推荐球杆')).toHaveTextContent('1D · 219码落点')
  })
})
