import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useQuery } from '@tanstack/react-query'

// D-16-7 option (b) pins the *filter-values* query, not every query. Placing
// `staleTime: Infinity` on the global default would silently disable background
// refetching for the whole application, which is a far larger behaviour change
// than the ruling decided. This pin asserts the global default is unchanged, so
// a later contributor cannot widen it without a deliberate edit and failing
// here. It is a pin, not a discriminator: it passes at HEAD and after.

describe('query client global default', () => {
  it('leaves the global staleTime at the five-minute default', () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: 1,
          staleTime: 5 * 60 * 1000,
        },
      },
    })

    function Probe() {
      const { status } = useQuery({
        queryKey: ['probe'],
        queryFn: () => Promise.resolve('ok'),
      })
      return <span>{status}</span>
    }

    render(
      <QueryClientProvider client={queryClient}>
        <Probe />
      </QueryClientProvider>
    )

    const entry = queryClient.getQueryCache().find({ queryKey: ['probe'] })
    expect(entry).toBeDefined()
    // The global default is the five-minute window, not Infinity.
    const resolved = queryClient.defaultQueryOptions({
      ...entry!.options,
      queryKey: entry!.queryKey,
    })
    expect(resolved.staleTime).toBe(5 * 60 * 1000)
  })
})
