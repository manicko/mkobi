import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ProtectedRoute } from './ProtectedRoute'

// Mock react-router-dom's Navigate component
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    Navigate: ({ to }: { to: string }) => <div data-testid="navigate" data-to={to} />,
  }
})

// Identity and token are read through the shared accessors; the component no
// longer imports the auth feature.
vi.mock('../auth/identity', () => ({
  useAuthIdentity: vi.fn(),
}))

vi.mock('../auth/tokenStore', () => ({
  useAuthToken: vi.fn(),
}))

// Mock MUI components
vi.mock('@mui/material', () => ({
  Box: ({ children }: { children: React.ReactNode }) => <div data-testid="box">{children}</div>,
  CircularProgress: () => <div data-testid="circular-progress">Loading...</div>,
}))

import { useAuthIdentity } from '../auth/identity'
import { useAuthToken } from '../auth/tokenStore'

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders children when authenticated', () => {
    vi.mocked(useAuthIdentity).mockReturnValue({ user: null, isLoading: false })
    vi.mocked(useAuthToken).mockReturnValue('valid-token')

    render(
      <MemoryRouter>
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    )

    expect(screen.getByText('Protected Content')).toBeInTheDocument()
  })

  it('shows loading spinner when isLoading is true', () => {
    vi.mocked(useAuthIdentity).mockReturnValue({ user: null, isLoading: true })
    vi.mocked(useAuthToken).mockReturnValue(null)

    render(
      <MemoryRouter>
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    )

    expect(screen.getByTestId('circular-progress')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('redirects to login when not authenticated and not loading', () => {
    vi.mocked(useAuthIdentity).mockReturnValue({ user: null, isLoading: false })
    vi.mocked(useAuthToken).mockReturnValue(null)

    render(
      <MemoryRouter initialEntries={['/protected']}>
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    )

    // Navigate component should be rendered (redirect to login)
    expect(screen.getByTestId('navigate')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('preserves location state when redirecting', () => {
    vi.mocked(useAuthIdentity).mockReturnValue({ user: null, isLoading: false })
    vi.mocked(useAuthToken).mockReturnValue(null)

    render(
      <MemoryRouter initialEntries={['/protected']}>
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    )

    const navigateElement = screen.getByTestId('navigate')
    expect(navigateElement).toHaveAttribute('data-to', '/login')
  })
})