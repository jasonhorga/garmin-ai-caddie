import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CoursePrepOverlay, CoursePrepResponse } from '../types'
import { CoursePrepPanel } from './CoursePrepPanel'
import { routeIntervalReadout, routeYardageReadout } from './coursePrepPanelLogic'

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

afterEach(() => {
  vi.restoreAllMocks()
})

describe('routeYardageReadout', () => {
  it('uses route cumulative distance instead of straight-line chord distance', () => {
    const readout = routeYardageReadout(overlay, 100)

    expect(readout.distT).toBe(109)
    expect(readout.toGreen).toBe(109)
  })

  it('reports hazard yardage from the ball along the same route', () => {
    expect(routeYardageReadout(overlay, 120, 180).hazard).toBe(66)
  })
})

describe('routeIntervalReadout', () => {
  it('reports carry to enter and clear water when the ball is before the interval', () => {
    expect(routeIntervalReadout(overlay, 70, 100, 130)).toEqual({
      toStart: 33,
      toClear: 66,
      isBehind: true,
      isInside: false,
      isCleared: false,
    })
  })

  it('reports remaining carry when the ball is inside the water interval', () => {
    expect(routeIntervalReadout(overlay, 110, 100, 130)).toEqual({
      toStart: 0,
      toClear: 22,
      isBehind: false,
      isInside: true,
      isCleared: false,
    })
  })

  it('marks intervals behind the ball as cleared', () => {
    expect(routeIntervalReadout(overlay, 150, 100, 130)).toEqual({
      toStart: 0,
      toClear: 0,
      isBehind: false,
      isInside: false,
      isCleared: true,
    })
  })
})

describe('CoursePrepPanel', () => {
  it('renders product Chinese copy, route-based hazard yardages, and no uncertainty markers', async () => {
    const response: CoursePrepResponse = {
      schema: 'ai-caddie-course-prep-v1',
      globalId: 31870,
      holeCount: 1,
      clubs: [{ name: '1W', m: 200, yd: 219 }],
      holes: [{
        hole: 1,
        par: 4,
        par_source: 'played',
        blue_yards: 219,
        route_len_m: 200,
        steps: [{ club: null, note: '开球落点约 87y' }],
        cautions: [],
        landing_m: 80,
        tee_club: null,
        hazards: { water_carry: [[100, 130]], bunkers: [[160, 10]] },
        map: {
          image: 'data:image/jpeg;base64,',
          overlay,
        },
      }],
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(response), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))

    render(<CoursePrepPanel />)
    await userEvent.click(screen.getByRole('button', { name: '加载' }))

    expect(await screen.findByRole('heading', { name: '赛前球场攻略' })).toBeInTheDocument()
    expect(screen.getByText(/默认蓝T/)).toBeInTheDocument()
    expect(screen.getAllByText(/Par 来源/).length).toBeGreaterThan(0)
    expect(screen.getByText('219y 蓝T')).toBeInTheDocument()
    expect(screen.getByText('水 进22y / 过55y')).toBeInTheDocument()
    expect(screen.getByText('沙87y')).toBeInTheDocument()
    expect(screen.getByText('开球落点约 87y')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '1W 219y' }))
    expect(screen.getByText('水已过')).toBeInTheDocument()
    expect(screen.getByText('沙已过')).toBeInTheDocument()
    expect(screen.queryByText('沙44y')).not.toBeInTheDocument()

    expect(screen.queryByText(/碳/)).not.toBeInTheDocument()
    expect(screen.queryByText(/\?/)).not.toBeInTheDocument()
  })
})
