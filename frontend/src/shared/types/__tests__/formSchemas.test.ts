import { describe, it, expect } from 'vitest'
import {
  loginSchema,
  registerSchema,
  createDashboardSchema,
  updateDashboardSchema,
  grantAccessSchema,
  changePasswordSchema,
} from '../formSchemas'

describe('loginSchema', () => {
  it('accepts valid email and password', () => {
    const result = loginSchema.safeParse({ email: 'user@example.com', password: '123456' })
    expect(result.success).toBe(true)
  })

  it('rejects invalid email', () => {
    const result = loginSchema.safeParse({ email: 'not-an-email', password: '123456' })
    expect(result.success).toBe(false)
  })

  it('accepts password with 1 or more characters', () => {
    const result = loginSchema.safeParse({ email: 'user@example.com', password: '12345' })
    expect(result.success).toBe(true)
  })

  it('rejects empty email', () => {
    const result = loginSchema.safeParse({ email: '', password: '123456' })
    expect(result.success).toBe(false)
  })

  it('rejects empty password', () => {
    const result = loginSchema.safeParse({ email: 'user@example.com', password: '' })
    expect(result.success).toBe(false)
  })
})

describe('registerSchema', () => {
  it('accepts valid email', () => {
    const result = registerSchema.safeParse({ email: 'user@example.com' })
    expect(result.success).toBe(true)
  })

  it('rejects invalid email format', () => {
    const result = registerSchema.safeParse({ email: 'not-an-email' })
    expect(result.success).toBe(false)
  })

  it('rejects blocked domain tempmail.com', () => {
    const result = registerSchema.safeParse({ email: 'user@tempmail.com' })
    expect(result.success).toBe(false)
  })

  it('rejects blocked domain throwaway.email', () => {
    const result = registerSchema.safeParse({ email: 'user@throwaway.email' })
    expect(result.success).toBe(false)
  })

  it('accepts non-blocked domain', () => {
    const result = registerSchema.safeParse({ email: 'user@gmail.com' })
    expect(result.success).toBe(true)
  })
})

describe('createDashboardSchema', () => {
  it('accepts valid name', () => {
    const result = createDashboardSchema.safeParse({ name: 'My Dashboard' })
    expect(result.success).toBe(true)
  })

  it('accepts name with description', () => {
    const result = createDashboardSchema.safeParse({ name: 'My Dashboard', description: 'A description' })
    expect(result.success).toBe(true)
  })

  it('rejects empty name', () => {
    const result = createDashboardSchema.safeParse({ name: '' })
    expect(result.success).toBe(false)
  })

  it('rejects name longer than 100 characters', () => {
    const result = createDashboardSchema.safeParse({ name: 'a'.repeat(101) })
    expect(result.success).toBe(false)
  })

  it('rejects description longer than 500 characters', () => {
    const result = createDashboardSchema.safeParse({ name: 'Valid', description: 'a'.repeat(501) })
    expect(result.success).toBe(false)
  })

  it('accepts optional description as undefined', () => {
    const result = createDashboardSchema.safeParse({ name: 'Valid', description: undefined })
    expect(result.success).toBe(true)
  })
})

describe('updateDashboardSchema', () => {
  // EB-5 (EXT-007): the backend `DashboardUpdate` now declares
  // `extra="forbid"`, so any key the writer emits beyond its declared fields is
  // a request-boundary 422. The write path is
  // `adminApi.ts::updateDashboard` -> `PUT /dashboards/{dashboard_id}`, and the
  // form schema is the closed writer surface that feeds it. Pinning the key set
  // here catches a writer that gains an undeclared key; mocking the transport
  // would catch the same regression only at far greater cost.
  const DASHBOARD_UPDATE_DECLARED_KEYS = ['name', 'description', 'config', 'layout_id'] as const

  it('pins the writer key set to declared DashboardUpdate fields', () => {
    const writerKeys = Object.keys(updateDashboardSchema.shape)
    // The form writes a closed subset of the backend's declared fields.
    for (const key of writerKeys) {
      expect(DASHBOARD_UPDATE_DECLARED_KEYS).toContain(key)
    }
    // And it is exactly the two keys the SPA writer sends.
    expect(new Set(writerKeys)).toEqual(new Set(['name', 'description']))
  })

  it('accepts partial update with name only', () => {
    const result = updateDashboardSchema.safeParse({ name: 'Updated Name' })
    expect(result.success).toBe(true)
  })

  it('accepts partial update with description only', () => {
    const result = updateDashboardSchema.safeParse({ description: 'Updated description' })
    expect(result.success).toBe(true)
  })

  it('accepts empty object (all fields optional)', () => {
    const result = updateDashboardSchema.safeParse({})
    expect(result.success).toBe(true)
  })

  it('rejects empty name', () => {
    const result = updateDashboardSchema.safeParse({ name: '' })
    expect(result.success).toBe(false)
  })
})

describe('grantAccessSchema', () => {
  it('accepts valid UUID and permission', () => {
    const result = grantAccessSchema.safeParse({
      user_id: '550e8400-e29b-41d4-a716-446655440000',
      permission: 'view',
    })
    expect(result.success).toBe(true)
  })

  it('accepts all valid permission values', () => {
    for (const permission of ['view', 'edit', 'admin'] as const) {
      const result = grantAccessSchema.safeParse({
        user_id: '550e8400-e29b-41d4-a716-446655440000',
        permission,
      })
      expect(result.success).toBe(true)
    }
  })

  it('rejects invalid permission value', () => {
    const result = grantAccessSchema.safeParse({
      user_id: '550e8400-e29b-41d4-a716-446655440000',
      permission: 'superadmin',
    })
    expect(result.success).toBe(false)
  })

  it('rejects invalid UUID format', () => {
    const result = grantAccessSchema.safeParse({
      user_id: 'not-a-uuid',
      permission: 'view',
    })
    expect(result.success).toBe(false)
  })
})

describe('changePasswordSchema', () => {
  it('accepts matching passwords', () => {
    const result = changePasswordSchema.safeParse({
      current_password: 'oldpass123',
      new_password: 'newpassword123',
      confirm_password: 'newpassword123',
    })
    expect(result.success).toBe(true)
  })

  it('imposes no complexity rule beyond what the server declares', () => {
    // The server is authoritative for password rules. The client previously
    // required an uppercase letter; that rule is dropped. A password without
    // an uppercase letter is accepted client-side and the server decides.
    const result = changePasswordSchema.safeParse({
      current_password: 'oldpass123',
      new_password: 'nouppercase123',
      confirm_password: 'nouppercase123',
    })
    expect(result.success).toBe(true)
  })

  it('rejects when new_password and confirm_password do not match', () => {
    const result = changePasswordSchema.safeParse({
      current_password: 'oldpass123',
      new_password: 'newpassword123',
      confirm_password: 'differentpassword',
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const confirmError = result.error.issues.find((i) => i.path.includes('confirm_password'))
      expect(confirmError?.message).toBe('Passwords do not match')
    }
  })

  it('rejects new_password shorter than 8 characters', () => {
    const result = changePasswordSchema.safeParse({
      current_password: 'oldpass123',
      new_password: 'short',
      confirm_password: 'short',
    })
    expect(result.success).toBe(false)
  })

  it('rejects empty current_password', () => {
    const result = changePasswordSchema.safeParse({
      current_password: '',
      new_password: 'newpassword123',
      confirm_password: 'newpassword123',
    })
    expect(result.success).toBe(false)
  })
})
