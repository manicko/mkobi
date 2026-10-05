import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TableChart } from './TableChart'

/**
 * Renders a single-cell table and returns the text of the data cell. The
 * display value is asserted through the DOM because `getDisplayValue` is a
 * module-private helper; the cell content is its only observable surface.
 */
function renderCell(value: unknown): string {
  const { container } = render(<TableChart data={{ rows: [{ col: value }] }} />)
  const cell = container.querySelector('tbody td')
  return cell?.textContent ?? ''
}

describe('TableChart', () => {
  it('renders absent cells (null and undefined) as the marker', () => {
    // `undefined` and `null` are distinguishable inside the reader but render
    // as the same gap, so both assertions expect the same marker.
    render(<TableChart data={{ rows: [{ a: null, b: undefined }] }} />)
    expect(screen.getAllByText('—')).toHaveLength(2)
  })

  it('renders a zero cell as 0, not the marker', () => {
    // Discriminates a real zero from absence: today both are indistinguishable.
    expect(renderCell(0)).toBe('0')
  })

  it('renders an empty-string cell as empty, distinct from the marker', () => {
    expect(renderCell('')).toBe('')
  })

  it('renders a non-numeric string through String()', () => {
    expect(renderCell('abc')).toBe('abc')
  })

  it('renders an object cell as JSON', () => {
    expect(renderCell({ a: 1 })).toBe('{"a":1}')
  })

  it('renders a date-shaped string through formatDate', () => {
    expect(renderCell('2024-06-15T10:30:00Z')).toBe('15/06/2024')
  })

  it('renders the shared no-rows message when there are no rows', () => {
    render(<TableChart data={{ rows: [] }} />)
    expect(screen.getByText('No data available for this chart')).toBeInTheDocument()
  })
})
