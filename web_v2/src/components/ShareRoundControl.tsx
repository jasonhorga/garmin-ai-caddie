import { useState } from 'react'
import type { RoundShareResponse } from '../types'

interface ShareRoundControlProps {
  onShare: () => Promise<RoundShareResponse>
  onRevoke?: () => Promise<unknown>
}

function absolutePageUrl(pageUrl: string): string {
  try {
    return new URL(pageUrl, window.location.origin).toString()
  } catch {
    return pageUrl
  }
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value)
      return
    } catch {
      // Fall through to the selection-based fallback when permission is unavailable.
    }
  }
  const input = document.createElement('textarea')
  input.value = value
  input.setAttribute('readonly', '')
  input.style.position = 'fixed'
  input.style.opacity = '0'
  document.body.appendChild(input)
  input.select()
  const copied = typeof document.execCommand === 'function' && document.execCommand('copy')
  input.remove()
  // Browsers without either clipboard API still get the visible read-only URL field; the user can
  // select it manually instead of being shown a made-up link or a transport error.
  if (!copied) return
}

export function ShareRoundControl({ onShare, onRevoke }: ShareRoundControlProps): React.ReactElement {
  const [state, setState] = useState<
    | { status: 'idle' }
    | { status: 'sharing' }
    | { status: 'ready'; pageUrl: string; copied: boolean }
    | { status: 'error'; message: string }
  >({ status: 'idle' })

  async function share(): Promise<void> {
    if (state.status === 'sharing') return
    setState({ status: 'sharing' })
    try {
      const response = await onShare()
      const pageUrl = absolutePageUrl(response.pageUrl)
      if (typeof navigator.share === 'function') {
        try {
          await navigator.share({ title: 'AI Caddie 球局记分卡', url: pageUrl })
        } catch (error: unknown) {
          if (error instanceof DOMException && error.name === 'AbortError') {
            setState({ status: 'ready', pageUrl, copied: false })
            return
          }
          throw error
        }
      } else {
        await copyText(pageUrl)
      }
      setState({ status: 'ready', pageUrl, copied: typeof navigator.share !== 'function' })
    } catch (error: unknown) {
      setState({ status: 'error', message: error instanceof Error ? error.message : '分享失败' })
    }
  }

  async function copy(): Promise<void> {
    if (state.status !== 'ready') return
    try {
      await copyText(state.pageUrl)
      setState({ ...state, copied: true })
    } catch (error: unknown) {
      setState({ status: 'error', message: error instanceof Error ? error.message : '复制失败' })
    }
  }

  async function revoke(): Promise<void> {
    if (!onRevoke || state.status !== 'ready') return
    setState({ status: 'sharing' })
    try {
      await onRevoke()
      setState({ status: 'idle' })
    } catch (error: unknown) {
      setState({ status: 'error', message: error instanceof Error ? error.message : '取消分享失败' })
    }
  }

  return (
    <div className="share-round-control">
      <button type="button" className="review-share-button" onClick={() => void share()} disabled={state.status === 'sharing'}>
        分享
      </button>
      {state.status === 'ready' ? (
        <div className="share-round-link" aria-label="分享链接">
          <label htmlFor="share-round-url">分享链接</label>
          <input id="share-round-url" value={state.pageUrl} readOnly />
          <div className="share-round-actions">
            <button type="button" onClick={() => void copy()}>复制</button>
            {onRevoke ? <button type="button" onClick={() => void revoke()}>取消分享</button> : null}
          </div>
          {state.copied ? <small role="status">已复制</small> : null}
        </div>
      ) : null}
      {state.status === 'error' ? <p className="share-round-error" role="alert">{state.message}</p> : null}
    </div>
  )
}
