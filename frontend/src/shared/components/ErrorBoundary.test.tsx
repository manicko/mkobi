import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'

const postMock = vi.hoisted(() => vi.fn())

vi.mock('../api/axiosInstance', () => ({
  axiosInstance: { post: postMock },
}))

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    Outlet: () => <div data-testid="outlet" />,
    Link: ({ children }: { children?: ReactNode }) => <a>{children}</a>,
  }
})

import { ErrorBoundary } from './ErrorBoundary'

function Boom({ message }: { message: string }): ReactNode {
  throw new Error(message)
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    postMock.mockReset()
    postMock.mockResolvedValue({ status: 204 })
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('posts a caught error to the client-errors route', async () => {
    vi.stubEnv('DEV', false)

    render(
      <ErrorBoundary>
        <Boom message="kaboom" />
      </ErrorBoundary>,
    )

    await vi.waitFor(() => expect(postMock).toHaveBeenCalledTimes(1))
    const [path, payload, config] = postMock.mock.calls[0] as [
      string,
      { error: { message: string }; componentStack: string | null },
      { skipErrorToast?: boolean },
    ]
    expect(path).toBe('/client-errors')
    expect(payload.error.message).toBe('kaboom')
    expect(config.skipErrorToast).toBe(true)
  })

  it('does not throw out of the boundary when the report fails, and logs it', async () => {
    vi.stubEnv('DEV', false)
    postMock.mockRejectedValue(new Error('network down'))

    render(
      <ErrorBoundary>
        <Boom message="kaboom" />
      </ErrorBoundary>,
    )

    // The boundary renders its fallback and remains mounted despite the failure.
    await vi.waitFor(() => expect(postMock).toHaveBeenCalledTimes(1))
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
    expect(console.error).toHaveBeenCalledWith(
      '[ErrorBoundary] failed to report client error',
      expect.any(Error),
    )
  })

  it('does not report in development builds', async () => {
    vi.stubEnv('DEV', true)

    render(
      <ErrorBoundary>
        <Boom message="dev-only" />
      </ErrorBoundary>,
    )

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(postMock).not.toHaveBeenCalled()
  })
})
