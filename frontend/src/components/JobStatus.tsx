import { CheckCircle2, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Job } from '../lib/types'
import { ProgressBar } from './ui'

/** Presentational: live state of a background job. */
export function JobStatus({ job }: { job: Job | null }) {
  const { t } = useTranslation()
  if (!job) return null
  const done = job.status === 'succeeded' || job.status === 'failed'
  return (
    <div className="space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm" aria-live="polite">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">
          {t(`jobs.${job.kind}`)} #{job.id} — {t(`jobs.${job.status}`)}
        </span>
        {job.status === 'succeeded' && <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden />}
        {job.status === 'failed' && <XCircle className="h-4 w-4 text-rose-600" aria-hidden />}
      </div>
      {!done && <ProgressBar value={job.progress > 0.05 ? job.progress : null} />}
      {job.message && <p className="text-xs text-slate-600">{job.message}</p>}
      {job.error && (
        <p className="text-xs text-rose-700">
          {job.error.message}
          {job.error.line ? ` (línea ${job.error.line})` : ''}
        </p>
      )}
    </div>
  )
}
