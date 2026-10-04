import { z } from 'zod'

const BLOCKED_DOMAINS = ['tempmail.com', 'throwaway.email']

// Login form schema
export const loginSchema = z.object({
  email: z.email({ error: 'Invalid email format' }),
  password: z.string().min(1, { error: 'Password is required' }),
})

export type LoginFormData = z.infer<typeof loginSchema>

// Registration form schema
export const registerSchema = z.object({
  email: z.email({ error: 'Invalid email format' }).refine((email) => {
    const domain = email.split('@')[1]
    return domain && !BLOCKED_DOMAINS.includes(domain)
  }, { error: 'This email domain is not allowed' }),
})

export type RegisterFormData = z.infer<typeof registerSchema>

// Dashboard creation schema
export const createDashboardSchema = z.object({
  name: z.string()
    .min(3, { error: 'Name must be at least 3 characters' })
    .max(100, { error: 'Name must be at most 100 characters' })
    .regex(/^[a-zA-Z0-9\s-]+$/, {
      error: 'Name can only contain letters, numbers, spaces, and hyphens',
    }),
  description: z.string().max(200, { error: 'Description must be at most 200 characters' }).optional(),
  layout: z.enum(['single-column', 'two-columns', 'grid']).optional(),
})

export type CreateDashboardFormData = z.infer<typeof createDashboardSchema>

// Dashboard update schema
export const updateDashboardSchema = z.object({
  name: z.string().min(1, { error: 'Dashboard name is required' }).max(100, { error: 'Dashboard name is too long' }).optional(),
  description: z.string().max(500, { error: 'Description is too long' }).optional(),
})

export type UpdateDashboardFormData = z.infer<typeof updateDashboardSchema>

// Grant dashboard access schema
export const grantAccessSchema = z.object({
  user_id: z.uuid({ error: 'Invalid user ID' }),
  permission: z.enum(['view', 'edit', 'admin']),
})

export type GrantAccessFormData = z.infer<typeof grantAccessSchema>

// Change password schema
export const changePasswordSchema = z.object({
  current_password: z.string().min(1, { error: 'Current password is required' }),
  new_password: z.string()
    .min(8, { error: 'Password must be at least 8 characters' })
    .regex(/[0-9]/, { error: 'Password must contain at least one digit' }),
  confirm_password: z.string().min(1, { error: 'Password confirmation is required' }),
}).refine((data) => data.new_password === data.confirm_password, {
  error: 'Passwords do not match',
  path: ['confirm_password'],
})

export type ChangePasswordFormData = z.infer<typeof changePasswordSchema>
