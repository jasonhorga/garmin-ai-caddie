import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { RoundHoleShotMapResponse } from '../types'
import { ReviewHoleCanvas } from './ReviewHoleCanvas'

describe('ReviewHoleCanvas', () => {
  it('uses the overlay dimensions even when the fallback bitmap has a different intrinsic ratio', () => {
    const data = {
      schema: 'ai-caddie-round-hole-shotmap-v1',
      found: true,
      roundRef: 'round-1',
      hole: 1,
      par: 4,
      map: {
        image:
          'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
        overlay: { w: 300, h: 470, ppm: 1, ln: 400, route: [] },
      },
      shots: [],
      missingData: [],
    } as unknown as RoundHoleShotMapResponse

    render(<ReviewHoleCanvas hole={1} par={4} score={4} state={{ status: 'ready', data }} />)

    const canvas = screen.getByLabelText('第1洞落点图')
    expect(canvas.querySelector('.review-canvas-frame')).toHaveStyle('aspect-ratio: 300 / 470')
  })
})
