import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RoleBasedAccess } from './RoleBasedAccess'

// Identity is read through the shared accessor; the component no longer imports
// the auth feature.
vi.mock('../auth/identity', () => ({
  useAuthIdentity: vi.fn(),
}))

import { useAuthIdentity } from '../auth/identity'

const createMockUser = (role: string) => ({
  user: {
    id: '1',
    email: `${role}@test.com`,
    role: role as 'admin' | 'editor' | 'viewer',
    display_name: role.charAt(0).toUpperCase() + role.slice(1),
    created_at: '',
    force_password_change: false,
  },
  isLoading: false,
})

describe('RoleBasedAccess', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders children when user has required role', () => {
    vi.mocked(useAuthIdentity).mockReturnValue(createMockUser('admin'))

    render(
      <RoleBasedAccess roles={['admin', 'editor']}>
        <div>Admin Content</div>
      </RoleBasedAccess>
    )

    expect(screen.getByText('Admin Content')).toBeInTheDocument()
  })

  it('renders children when user has single required role', () => {
    vi.mocked(useAuthIdentity).mockReturnValue(createMockUser('editor'))

    render(
      <RoleBasedAccess roles={['admin', 'editor']}>
        <div>Editor Content</div>
      </RoleBasedAccess>
    )

    expect(screen.getByText('Editor Content')).toBeInTheDocument()
  })

  it('renders fallback when user does not have required role', () => {
    vi.mocked(useAuthIdentity).mockReturnValue(createMockUser('viewer'))

    render(
      <RoleBasedAccess roles={['admin', 'editor']} fallback={<div>Access Denied</div>}>
        <div>Protected Content</div>
      </RoleBasedAccess>
    )

    expect(screen.getByText('Access Denied')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('renders AccessDenied as default fallback when user does not have required role', () => {
    vi.mocked(useAuthIdentity).mockReturnValue(createMockUser('viewer'))

    render(
      <RoleBasedAccess roles={['admin']}>
        <div>Protected Content</div>
      </RoleBasedAccess>
    )

    // Default fallback is AccessDenied component
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
    expect(screen.getByText(/No access/)).toBeInTheDocument()
  })

  it('renders fallback when user is null', () => {
    vi.mocked(useAuthIdentity).mockReturnValue({ user: null, isLoading: false })

    render(
      <RoleBasedAccess roles={['admin']} fallback={<div>Login Required</div>}>
        <div>Protected Content</div>
      </RoleBasedAccess>
    )

    expect(screen.getByText('Login Required')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('accepts single role string', () => {
    vi.mocked(useAuthIdentity).mockReturnValue(createMockUser('admin'))

    render(
      <RoleBasedAccess roles={['admin']}>
        <div>Admin Only Content</div>
      </RoleBasedAccess>
    )

    expect(screen.getByText('Admin Only Content')).toBeInTheDocument()
  })

  it('matches any role in the roles array', () => {
    vi.mocked(useAuthIdentity).mockReturnValue(createMockUser('editor'))

    render(
      <RoleBasedAccess roles={['admin', 'editor', 'viewer']}>
        <div>All Roles Content</div>
      </RoleBasedAccess>
    )

    expect(screen.getByText('All Roles Content')).toBeInTheDocument()
  })

  it('renders different content for different roles', () => {
    vi.mocked(useAuthIdentity).mockReturnValue(createMockUser('admin'))

    render(
      <RoleBasedAccess roles={['admin']} fallback={<div>Not Admin</div>}>
        <button>Admin Button</button>
      </RoleBasedAccess>
    )

    expect(screen.getByRole('button', { name: 'Admin Button' })).toBeInTheDocument()
    expect(screen.queryByText('Not Admin')).not.toBeInTheDocument()
  })
})