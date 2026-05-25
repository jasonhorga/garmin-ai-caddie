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
})
