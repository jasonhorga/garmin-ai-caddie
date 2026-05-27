import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SettingsPage } from './SettingsPage'

describe('SettingsPage', () => {
  it('renders product control groups and navigates to owned surfaces', async () => {
    const onNavigate = vi.fn()
    const user = userEvent.setup()
    render(<SettingsPage onNavigate={onNavigate} />)

    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Data Sources' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'AI Providers' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Live Apps' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Privacy & Retention' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Manual Corrections' })).toBeInTheDocument()

    const dataSources = screen.getByLabelText('Data source settings')
    expect(within(dataSources).getByText('CN Web Session')).toHaveClass('setting-primary')
    expect(within(dataSources).getByText('OAuth feasibility')).toHaveClass('setting-secondary')
    expect(within(dataSources).getByText('No Garmin password storage')).toBeInTheDocument()

    const aiProviders = screen.getByLabelText('AI provider settings')
    expect(within(aiProviders).getByText('Static')).toBeInTheDocument()
    expect(within(aiProviders).getByText('NVIDIA NIM')).toBeInTheDocument()
    expect(within(aiProviders).getByText('Gemini API')).toBeInTheDocument()
    expect(within(aiProviders).getByRole('checkbox', { name: 'Fact binding required' })).toBeChecked()

    const liveApps = screen.getByLabelText('Live app settings')
    expect(within(liveApps).getByText('iOS offline package')).toBeInTheDocument()
    expect(within(liveApps).getByText('Watch bridge')).toBeInTheDocument()
    expect(within(liveApps).getByText('Photo / video context')).toBeInTheDocument()

    const privacy = screen.getByLabelText('Privacy settings')
    expect(within(privacy).getByRole('checkbox', { name: 'Admin protected writes' })).toBeChecked()
    expect(within(privacy).getByRole('checkbox', { name: 'Media redaction' })).toBeChecked()
    expect(within(privacy).getByRole('checkbox', { name: 'Local snapshots survive reauth' })).toBeChecked()

    await user.click(screen.getByRole('button', { name: 'Open sync controls' }))
    await user.click(screen.getByRole('button', { name: 'Open caddie controls' }))
    await user.click(screen.getByRole('button', { name: 'Open report controls' }))
    await user.click(screen.getByRole('button', { name: 'Open corrections' }))

    expect(onNavigate).toHaveBeenNthCalledWith(1, 'sync-quality')
    expect(onNavigate).toHaveBeenNthCalledWith(2, 'caddie')
    expect(onNavigate).toHaveBeenNthCalledWith(3, 'reports')
    expect(onNavigate).toHaveBeenNthCalledWith(4, 'corrections')
  })
})
