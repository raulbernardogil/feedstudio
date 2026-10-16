import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api } from './api'

/** Poll a background job until it finishes, then invalidate related caches. */
export function useJob(jobId: number | null, invalidate: string[][] = []) {
  const qc = useQueryClient()
  const query = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => api.job(jobId as number),
    enabled: jobId !== null,
    refetchInterval: (q) => {
      const status = q.state.data?.status
      return status === 'succeeded' || status === 'failed' ? false : 1000
    },
  })
  const status = query.data?.status
  useEffect(() => {
    if (status === 'succeeded' || status === 'failed') {
      for (const key of invalidate) void qc.invalidateQueries({ queryKey: key })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])
  return query.data ?? null
}
