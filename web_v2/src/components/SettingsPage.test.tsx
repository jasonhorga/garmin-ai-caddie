import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ProductSettingsResponse } from '../types'
import { SettingsPage } from './SettingsPage'

// Minimal product-settings payload — the consumer page only reads the Garmin
// data-source state; the rich AI/OAuth/live-app sections are no longer rendered.
const connectedSettings: ProductSettingsResponse = {
  schema: 'ai-caddie-product-settings-v1',
  dataSources: [{ id: 'garmin_cn_web_session', label: 'Garmin CN Web Session', track: 'primary', state: 'available' }],
  aiProviders: { activeProvider: 'static', factBindingRequired: true, providers: [] },
  liveApps: {},
  privacy: {},
  endpoints: {},
}

describe('SettingsPage', () => {
  it('renders the consumer settings cards and navigates to owned tools', async () => {
    const onNavigate = vi.fn()
    const onSignOut = vi.fn()
    const user = userEvent.setup()
    render(<SettingsPage onNavigate={onNavigate} onSignOut={onSignOut} currentPlayer={{ id: 'me', name: '老王', isOwner: true, avatar: null }} />)

    expect(screen.getByRole('heading', { name: '账号' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '连接 Garmin' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '我的球杆' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '数据更正' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '隐私' })).toBeInTheDocument()

    // 账号: signed-in identity + sign-out.
    const account = screen.getByLabelText('账号')
    expect(within(account).getByText('老王')).toBeInTheDocument()
    await user.click(within(account).getByRole('button', { name: '退出登录' }))
    expect(onSignOut).toHaveBeenCalledTimes(1)

    // 我的球杆 / 数据更正 jump to the existing tools.
    await user.click(screen.getByRole('button', { name: '管理你的球杆' }))
    await user.click(screen.getByRole('button', { name: '打开数据更正' }))
    expect(onNavigate).toHaveBeenNthCalledWith(1, 'club-bag')
    expect(onNavigate).toHaveBeenNthCalledWith(2, 'corrections')

    // 隐私 is plain language only — no engineering checkboxes.
    const privacy = screen.getByLabelText('隐私')
    expect(within(privacy).getByText('你的数据只属于你。')).toBeInTheDocument()
    expect(screen.queryByText('管理员保护写入')).not.toBeInTheDocument()
    expect(screen.queryByText('状态响应不含密钥')).not.toBeInTheDocument()

    // The engineering control plane is gone.
    expect(screen.queryByText('AI 引擎')).not.toBeInTheDocument()
    expect(screen.queryByText('NVIDIA NIM')).not.toBeInTheDocument()
    expect(screen.queryByText('OAuth 可行性')).not.toBeInTheDocument()
    expect(screen.queryByText('实战应用')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('管理令牌')).not.toBeInTheDocument()
  })

  it('shows the Garmin connection status from the product-settings data source', () => {
    const { rerender } = render(<SettingsPage onNavigate={vi.fn()} settings={connectedSettings} />)
    const garmin = screen.getByLabelText('连接 Garmin')
    expect(within(garmin).getByText('已连接')).toHaveClass('quality-good')
    expect(within(garmin).getByText('在 iPhone App 上连接或重新登录 Garmin。')).toBeInTheDocument()

    // No data source / unknown state → 未连接.
    rerender(<SettingsPage onNavigate={vi.fn()} settings={null} />)
    expect(within(screen.getByLabelText('连接 Garmin')).getByText('未连接')).toHaveClass('quality-missing')
  })

  it('falls back to a generic account label when no player is resolved yet', () => {
    render(<SettingsPage onNavigate={vi.fn()} />)
    expect(within(screen.getByLabelText('账号')).getByText('已登录')).toBeInTheDocument()
  })
})
