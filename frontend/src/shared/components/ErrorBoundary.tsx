import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { ErrorPage } from './ErrorPage'
import { axiosInstance } from '../api/axiosInstance'

interface ErrorBoundaryProps {
  children?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

const logger = {
  error: (...args: unknown[]): void => {
    // The boundary is the last line of defence; its own failure must be
    // visible in the console rather than silently swallowed.
    console.error(...args)
  },
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    if (import.meta.env.DEV) {
      logger.error('[ErrorBoundary]', error)
      return
    }
    void this.reportError(error, errorInfo.componentStack ?? null)
  }

  /**
   * POST the error to the live first-party `/client-errors` route.
   *
   * The request goes through the shared axios client, which already carries the
   * API base URL, so the path is relative. `skipErrorToast` keeps a failed
   * report from raising a toast of its own — the boundary is already showing
   * the error. A failure is logged, never silently discarded: a swallowed
   * failure would make the one component whose job is reporting failures the
   * one place failures vanish.
   */
  private async reportError(error: Error, componentStack: string | null): Promise<void> {
    const payload = {
      error: { name: error.name, message: error.message, stack: error.stack },
      componentStack,
      url: window.location.href,
      userAgent: navigator.userAgent,
      timestamp: new Date().toISOString(),
    }
    try {
      await axiosInstance.post('/client-errors', payload, { skipErrorToast: true })
    } catch (reportingError: unknown) {
      logger.error('[ErrorBoundary] failed to report client error', reportingError)
    }
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return <ErrorPage variant="500" error={this.state.error} />
    }
    // Support both children (direct) and Outlet (nested routes in React Router v6)
    return this.props.children ?? <Outlet />
  }
}
