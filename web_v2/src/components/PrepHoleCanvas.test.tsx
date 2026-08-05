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
})
