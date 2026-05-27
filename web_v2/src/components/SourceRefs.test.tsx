import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SourceRefs } from './SourceRefs'

describe('SourceRefs', () => {
  it('renders clickable source refs when a selector is provided', async () => {
    const onSelectRef = vi.fn()

    render(<SourceRefs refs={['900001', '900001:7', '900001:7:2']} onSelectRef={onSelectRef} />)

    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001:7:2' }))

    expect(onSelectRef).toHaveBeenCalledWith('900001:7:2')
  })

  it('renders a dash when there are no refs', () => {
    render(<SourceRefs refs={[]} />)

    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('keeps overflow refs expandable instead of dropping drill-down sources', async () => {
    const onSelectRef = vi.fn()

    render(<SourceRefs refs={['900001:1', '900001:2', '900001:3']} maxVisible={2} onSelectRef={onSelectRef} />)

    expect(screen.getByRole('button', { name: 'Open source 900001:1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900001:2' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open source 900001:3' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Show 1 more source ref' }))
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001:3' }))

    expect(onSelectRef).toHaveBeenCalledWith('900001:3')
  })
})
