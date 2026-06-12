import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DataQualityChips } from './DataQualityChips'

// Round-card badges showed raw backend labels (「shots 缺失」「shots 齐全」) —
// the label must render through the zh badge dictionary, in the visible chip
// and in the aria-label alike.
describe('DataQualityChips', () => {
  it('renders badge labels through the zh dictionary in chip and aria-label', () => {
    render(
      <DataQualityChips
        badges={[
          { label: 'shots', state: 'missing', value: 'missing', reason: 'no shot file' },
          { label: 'shot rows', state: 'good', value: '1234', reason: 'normalized rows loaded' },
        ]}
      />,
    )

    expect(screen.getByText('击球')).toBeInTheDocument()
    expect(screen.getByText('缺失')).toBeInTheDocument()
    expect(screen.getByText('击球明细')).toBeInTheDocument()
    expect(screen.getByText('1234')).toBeInTheDocument()
    expect(screen.queryByText('shots')).not.toBeInTheDocument()
    expect(screen.queryByText('shot rows')).not.toBeInTheDocument()
    expect(screen.getByLabelText('击球: 缺失, missing - no shot file')).toHaveClass('quality-missing')
  })

  it('passes unknown badge labels through raw', () => {
    render(<DataQualityChips badges={[{ label: 'mystery', state: 'good', value: 'ready', reason: 'n/a' }]} />)

    expect(screen.getByText('mystery')).toBeInTheDocument()
    expect(screen.getByText('齐全')).toBeInTheDocument()
  })

  it('renders nothing when there are no badges', () => {
    const { container } = render(<DataQualityChips badges={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
