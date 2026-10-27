import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ShareRoundControl } from './ShareRoundControl'

const response = {
  schema: 'ai-caddie-round-share-v1' as const,
  url: '/api/v2/share/share-token',
  pageUrl: '/s/share-token',
  expiresAt: '2026-06-19T00:00:00Z',
  shareId: 'share-1',
}

describe('ShareRoundControl', () => {
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
})
