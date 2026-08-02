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
})
