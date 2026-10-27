import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ShareRoundControl } from './ShareRoundControl'

const response = {
  schema: 'ai-caddie-round-share-v1' as const,
  url: '/api/v2/share/share-token',
  pageUrl: '/s/share-token',
  expiresAt: '2026-06-19T00:00:00Z',
  shareId: 'share-1',
}

describe('ShareRoundControl', () => {
  afterEach(() => {
    Reflect.deleteProperty(navigator, 'share')
    Reflect.deleteProperty(navigator, 'clipboard')
    Reflect.deleteProperty(document, 'execCommand')
  })

  function mockShare(implementation: () => Promise<void>): void {
    Object.defineProperty(navigator, 'share', { configurable: true, value: vi.fn(implementation) })
  }

  it('creates a page URL, shows it, and can revoke it', async () => {
    const onShare = vi.fn(async () => response)
    const onRevoke = vi.fn(async () => ({ revoked: 1 }))
    render(<ShareRoundControl onShare={onShare} onRevoke={onRevoke} />)
    await userEvent.click(screen.getByRole('button', { name: '分享' }))
    expect(await screen.findByDisplayValue(`${window.location.origin}/s/share-token`)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '取消分享' }))
    await waitFor(() => expect(onRevoke).toHaveBeenCalledTimes(1))
    expect(screen.queryByLabelText('分享链接')).not.toBeInTheDocument()
  })

  it('reports creation failures without inventing a fallback URL', async () => {
    const onShare = vi.fn(async () => { throw new Error('创建失败') })
    render(<ShareRoundControl onShare={onShare} />)
    await userEvent.click(screen.getByRole('button', { name: '分享' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('创建失败')
    expect(screen.queryByLabelText('分享链接')).not.toBeInTheDocument()
  })

  it('keeps the URL visible when navigator.share succeeds', async () => {
    const share = vi.fn(async () => undefined)
    mockShare(share)
    render(<ShareRoundControl onShare={vi.fn(async () => response)} />)
    await userEvent.click(screen.getByRole('button', { name: '分享' }))
    expect(await screen.findByDisplayValue(`${window.location.origin}/s/share-token`)).toBeInTheDocument()
    expect(share).toHaveBeenCalledWith({ title: 'AI Caddie 球局记分卡', url: `${window.location.origin}/s/share-token` })
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('keeps the URL visible when the share sheet is dismissed', async () => {
    mockShare(async () => { throw new DOMException('dismissed', 'AbortError') })
    render(<ShareRoundControl onShare={vi.fn(async () => response)} />)
    await userEvent.click(screen.getByRole('button', { name: '分享' }))
    expect(await screen.findByDisplayValue(`${window.location.origin}/s/share-token`)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps the URL visible when navigator.share fails for another reason', async () => {
    mockShare(async () => { throw new DOMException('gesture expired', 'NotAllowedError') })
    render(<ShareRoundControl onShare={vi.fn(async () => response)} />)
    await userEvent.click(screen.getByRole('button', { name: '分享' }))
    expect(await screen.findByDisplayValue(`${window.location.origin}/s/share-token`)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('does not claim copied when both copy methods fail', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn(async () => { throw new Error('permission denied') }) },
    })
    Object.defineProperty(document, 'execCommand', { configurable: true, value: vi.fn(() => false) })
    render(<ShareRoundControl onShare={vi.fn(async () => response)} />)
    await userEvent.click(screen.getByRole('button', { name: '分享' }))
    expect(await screen.findByDisplayValue(`${window.location.origin}/s/share-token`)).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '复制' }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
