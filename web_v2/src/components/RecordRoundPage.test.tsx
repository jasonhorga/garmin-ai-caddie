import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { RoundIngestRequestBody, RoundIngestResult } from '../types'
import { RecordRoundPage } from './RecordRoundPage'

function ingestResult(over: Partial<RoundIngestResult> = {}): RoundIngestResult {
  return { id: 555, playerId: 'me', source: 'manual', holesCompleted: 1, strokes: 5, shotCount: 2, idempotent: false, ...over }
}

function renderRecord(over: Partial<Parameters<typeof RecordRoundPage>[0]> = {}) {
  const onIngest = vi.fn(async (_playerId: string, _body: RoundIngestRequestBody) => ingestResult())
  const onExit = vi.fn()
  const getPosition = vi.fn(async () => ({ latitude: 39.91, longitude: 116.41, accuracy: 4 }))
  render(
    <RecordRoundPage
      playerId="me"
      playerName="我"
      courseOptions={null}
      onIngest={onIngest}
      onExit={onExit}
      getPosition={getPosition}
      {...over}
    />,
  )
  return { onIngest, onExit, getPosition }
}

describe('RecordRoundPage', () => {
  it('records a shot via GPS, captures a score, and submits a manual round', async () => {
    const { onIngest } = renderRecord()

    // setup → recording
    await userEvent.type(screen.getByLabelText('球场名称'), '北京丽宫')
    await userEvent.click(screen.getByRole('button', { name: '开始记分' }))

    expect(screen.getByRole('heading', { name: '第 1 洞' })).toBeInTheDocument()

    // pick a club and record a GPS shot
    await userEvent.selectOptions(screen.getByLabelText('球杆'), '7i')
    await userEvent.click(screen.getByRole('button', { name: /记一杆/ }))
    expect(await screen.findByRole('status')).toHaveTextContent('已记录第 1 杆')
    expect(within(screen.getByLabelText('本洞击球')).getByText(/第1杆 · 7i/)).toBeInTheDocument()

    // enter the hole score and submit
    await userEvent.type(screen.getByLabelText('本洞杆数'), '5')
    await userEvent.click(screen.getByRole('button', { name: '结束并提交' }))

    expect(await screen.findByRole('heading', { name: '已提交 ✅' })).toBeInTheDocument()
    expect(onIngest).toHaveBeenCalledTimes(1)
    const [playerId, body] = onIngest.mock.calls[0]
    expect(playerId).toBe('me')
    expect(body.meta).toMatchObject({ courseName: '北京丽宫', holesCompleted: 1 })
    expect(body.events).toEqual([
      { hole: 1, kind: 'club', payload: { clubName: '7i', source: 'web' } },
      { hole: 1, kind: 'location', payload: { latitude: 39.91, longitude: 116.41, horizontalAccuracyM: 4, source: 'web' } },
      { hole: 1, kind: 'score', payload: { strokes: 5 } },
    ])
  })

  it('surfaces a geolocation error without losing the session', async () => {
    renderRecord({ getPosition: vi.fn(async () => Promise.reject(new Error('定位权限被拒绝,请在浏览器允许定位'))) })

    await userEvent.click(screen.getByRole('button', { name: '开始记分' }))
    await userEvent.click(screen.getByRole('button', { name: /记一杆/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent('定位权限被拒绝')
    // still on the recording screen, can retry
    expect(screen.getByRole('heading', { name: '第 1 洞' })).toBeInTheDocument()
  })

  it('refuses to submit an empty round', async () => {
    const { onIngest } = renderRecord()
    await userEvent.click(screen.getByRole('button', { name: '开始记分' }))
    await userEvent.click(screen.getByRole('button', { name: '结束并提交' }))

    expect(screen.getByRole('alert')).toHaveTextContent('还没有记录任何一杆或成绩')
    expect(onIngest).not.toHaveBeenCalled()
  })

  it('advances holes and submits multi-hole events in order', async () => {
    const { onIngest } = renderRecord()
    await userEvent.click(screen.getByRole('button', { name: '开始记分' }))

    await userEvent.type(screen.getByLabelText('本洞杆数'), '4')
    await userEvent.click(screen.getByRole('button', { name: '下一洞 →' }))
    expect(screen.getByRole('heading', { name: '第 2 洞' })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('本洞杆数'), '6')
    await userEvent.click(screen.getByRole('button', { name: '结束并提交' }))

    await screen.findByRole('heading', { name: '已提交 ✅' })
    const body = onIngest.mock.calls[0][1]
    expect(body.events).toEqual([
      { hole: 1, kind: 'score', payload: { strokes: 4 } },
      { hole: 2, kind: 'score', payload: { strokes: 6 } },
    ])
    expect(body.meta).toMatchObject({ holesCompleted: 2 })
  })
})
