import { describe, it, expect, afterEach, vi } from 'vitest'
import { getApiBaseUrl, validateEnv } from './env'

describe('env', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('returns the configured VITE_API_URL when set', () => {
    vi.stubEnv('VITE_API_URL', 'https://api.example.com/api/v1')
    expect(getApiBaseUrl()).toBe('https://api.example.com/api/v1')
  })

  it('falls back to the same-origin default when VITE_API_URL is unset', () => {
    vi.stubEnv('VITE_API_URL', '')
    expect(getApiBaseUrl()).toBe('/api/v1')
  })

  it('does not throw when a development build omits VITE_API_URL', () => {
    vi.stubEnv('DEV', true)
    vi.stubEnv('VITE_API_URL', '')
    expect(() => validateEnv()).not.toThrow()
  })

  it('throws when a production build omits VITE_API_URL', () => {
    vi.stubEnv('DEV', false)
    vi.stubEnv('VITE_API_URL', '')
    expect(() => validateEnv()).toThrow(/VITE_API_URL/)
  })

  it('accepts a production build with VITE_API_URL set', () => {
    vi.stubEnv('DEV', false)
    vi.stubEnv('VITE_API_URL', 'https://api.example.com/api/v1')
    expect(() => validateEnv()).not.toThrow()
  })
})
