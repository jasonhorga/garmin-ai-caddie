import { useCallback, useEffect, useRef, useState } from 'react'
import { signInWithApple } from '../api'
import { saveSession } from '../sessionStore'

// The consumer entry screen: everyone signs in with Apple. Loads Apple's "Sign
// in with Apple JS" lazily, exchanges the returned identity token for a session
// (POST /api/v2/auth/apple), persists it, then re-enters the app. Real sign-in
// needs the funnel domain registered with Apple + the Services ID configured
// (VITE_AI_CADDIE_APPLE_CLIENT_ID) at deploy time — until then the button shows
// but the click reports a friendly error.

const APPLE_JS = 'https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js'

interface AppleAuthSignInResult {
  authorization?: { id_token?: string }
  user?: { name?: { firstName?: string; lastName?: string } }
}

declare global {
  interface Window {
    AppleID?: {
      auth: {
        init: (config: Record<string, unknown>) => void
        signIn: () => Promise<AppleAuthSignInResult>
      }
    }
  }
}

function loadAppleJs(): Promise<void> {
  if (window.AppleID) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${APPLE_JS}"]`)
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('apple js failed to load')))
      return
    }
    const script = document.createElement('script')
    script.src = APPLE_JS
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('apple js failed to load'))
    document.head.appendChild(script)
  })
}

export function AppleSignInPage({ onSignedIn }: { onSignedIn: () => void }): React.ReactElement {
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const inited = useRef(false)

  useEffect(() => {
    // Only load Apple's JS when a Services ID is configured (deploy-time). In dev/CI it's unset,
    // so skip the CDN load entirely — the button still renders; a click reports a friendly error,
    // and there's no failed-resource console noise in the test/dev environment.
    const clientId = String(import.meta.env.VITE_AI_CADDIE_APPLE_CLIENT_ID ?? '').trim()
    if (!clientId) return
    let cancelled = false
    loadAppleJs()
      .then(() => {
        if (cancelled || inited.current || !window.AppleID) return
        const redirectURI = String(import.meta.env.VITE_AI_CADDIE_APPLE_REDIRECT ?? window.location.origin).trim()
        window.AppleID.auth.init({ clientId, scope: 'name email', redirectURI, usePopup: true })
        inited.current = true
      })
      .catch(() => {
        /* Apple JS blocked/unconfigured — the button still renders; the click reports an error */
      })
    return () => {
      cancelled = true
    }
  }, [])

  const onSignIn = useCallback(async () => {
    setStatus('loading')
    try {
      if (!window.AppleID) throw new Error('apple sign-in unavailable')
      const result = await window.AppleID.auth.signIn()
      const idToken = result.authorization?.id_token
      if (!idToken) throw new Error('no identity token')
      const name = result.user?.name
        ? [result.user.name.firstName, result.user.name.lastName].filter(Boolean).join(' ').trim() || undefined
        : undefined
      const session = await signInWithApple(idToken, name)
      saveSession({ token: session.token, playerId: session.playerId, expiresAt: session.expiresAt })
      onSignedIn()
    } catch {
      setStatus('error')
    }
  }, [onSignedIn])

  return (
    <main className="signin-page" aria-label="登录" style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <div style={{ textAlign: 'center', maxWidth: 340 }}>
        <div style={{ width: 56, height: 56, borderRadius: 16, background: 'var(--green, #1a7040)', margin: '0 auto 18px' }} aria-hidden="true" />
        <h1 style={{ fontSize: 26, margin: '0 0 8px' }}>AI Caddie</h1>
        <p style={{ color: '#667085', margin: '0 0 24px' }}>用 Apple 登录,开始你的高尔夫。</p>
        <button
          type="button"
          className="signin-apple-button"
          onClick={() => void onSignIn()}
          disabled={status === 'loading'}
          style={{ width: '100%', padding: '12px 16px', borderRadius: 10, border: 'none', background: '#000', color: '#fff', fontSize: 16, cursor: 'pointer' }}
        >
          {status === 'loading' ? '登录中…' : ' 通过 Apple 登录'}
        </button>
        {status === 'error' ? (
          <p className="signin-error" role="alert" style={{ color: '#b4533a', marginTop: 14, fontSize: 14 }}>
            登录失败,请重试。
          </p>
        ) : null}
      </div>
    </main>
  )
}
