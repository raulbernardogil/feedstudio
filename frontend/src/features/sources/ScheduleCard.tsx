import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, Play, Plus, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { JobStatus } from '../../components/JobStatus'
import { Button, Card, ErrorBox, Input, Select } from '../../components/ui'
import { api } from '../../lib/api'
import { formatDate } from '../../lib/format'
import type { ScheduleConfig, Source } from '../../lib/types'
import { useJob } from '../../lib/useJob'

const HOURS = [1, 2, 3, 4, 6, 8, 12, 24]

function timezones(): string[] {
  try {
    return (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf('timeZone')
  } catch {
    return ['UTC', 'Europe/Madrid', 'America/Santiago', 'America/Mexico_City', 'America/Bogota', 'America/Argentina/Buenos_Aires']
  }
}

/** Container: automatic refresh schedule + "run now" for a source. */
export function ScheduleCard({ source }: { source: Source }) {
  const qc = useQueryClient()
  const current = source.schedule_config ?? { mode: 'manual' }
  const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone
  const [mode, setMode] = useState<ScheduleConfig['mode']>(current.mode)
  const [hours, setHours] = useState<number>(current.every_hours ?? 2)
  const [times, setTimes] = useState<string[]>(current.times?.length ? current.times : ['08:00'])
  const [newTime, setNewTime] = useState('20:00')
  const [tz, setTz] = useState<string>(current.timezone && current.timezone !== 'UTC' ? current.timezone : browserTz)
  const [jobId, setJobId] = useState<number | null>(null)
  const job = useJob(jobId, [['sources'], ['versions'], ['channels'], ['dashboard'], ['products'], ['jobs']])
  const zones = useMemo(timezones, [])
  const isUrl = source.kind === 'url'

  const save = useMutation({
    mutationFn: () => {
      const body: ScheduleConfig =
        mode === 'interval' ? { mode, every_hours: hours, timezone: tz } : mode === 'daily' ? { mode, times, timezone: tz } : { mode: 'manual' }
      return api.setSchedule(source.id, body)
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['sources'] }),
  })
  const run = useMutation({ mutationFn: () => api.runSource(source.id), onSuccess: (r) => setJobId(r.job.id) })
  const dirty = JSON.stringify({ mode, hours, times, tz }) !== JSON.stringify({ mode: current.mode, hours: current.every_hours ?? 2, times: current.times?.length ? current.times : ['08:00'], tz: current.timezone && current.timezone !== 'UTC' ? current.timezone : browserTz })

  return (
    <Card
      title={<span className="inline-flex items-center gap-2"><CalendarClock className="h-4 w-4" /> Actualización automática</span>}
      actions={
        <Button size="sm" onClick={() => run.mutate()} loading={run.isPending || job?.status === 'running' || job?.status === 'queued'}>
          <Play className="h-3.5 w-3.5" /> Ejecutar ahora
        </Button>
      }
    >
      <p className="mb-3 text-sm text-slate-600">
        Cada ejecución {isUrl ? 'descarga el XML de la URL, ' : 'reutiliza el último XML subido, '}aplica las reglas, valida, genera una versión de cada canal y
        —en los canales con publicación automática— la publica y la sube a sus destinos (Google Drive).
      </p>
      {!isUrl && (
        <p className="mb-3 rounded-md border border-amber-200 bg-amber-50 p-2 text-sm text-amber-800">
          Esta fuente es un archivo subido: no se puede volver a descargar sola. Para programar actualizaciones crea la fuente con una URL HTTPS.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <Select value={mode} onChange={(e) => setMode(e.target.value as ScheduleConfig['mode'])} disabled={!isUrl} aria-label="Frecuencia">
          <option value="manual">Manual</option>
          <option value="interval">Cada X horas</option>
          <option value="daily">A horas fijas</option>
        </Select>
        {mode === 'interval' && (
          <Select value={hours} onChange={(e) => setHours(Number(e.target.value))} aria-label="Horas">
            {HOURS.map((h) => <option key={h} value={h}>{h === 1 ? 'Cada hora' : `Cada ${h} horas`}</option>)}
          </Select>
        )}
        {mode === 'daily' && (
          <div className="flex flex-wrap items-center gap-1.5">
            {times.map((t) => (
              <span key={t} className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2 py-0.5 text-xs text-brand-700">
                {t}
                <button onClick={() => setTimes(times.filter((x) => x !== t))} disabled={times.length === 1} aria-label={`Quitar ${t}`}><X className="h-3 w-3" /></button>
              </span>
            ))}
            <Input type="time" className="w-28" value={newTime} onChange={(e) => setNewTime(e.target.value)} aria-label="Nueva hora" />
            <Button size="sm" variant="ghost" disabled={!newTime || times.includes(newTime) || times.length >= 24} onClick={() => setTimes([...times, newTime].sort())}>
              <Plus className="h-3.5 w-3.5" /> Hora
            </Button>
          </div>
        )}
        {mode !== 'manual' && (
          <Select value={tz} onChange={(e) => setTz(e.target.value)} aria-label="Zona horaria" className="max-w-56">
            {zones.map((z) => <option key={z} value={z}>{z}</option>)}
          </Select>
        )}
        <Button size="sm" variant="primary" onClick={() => save.mutate()} disabled={!isUrl || !dirty} loading={save.isPending}>Guardar programación</Button>
      </div>
      <dl className="mt-3 grid grid-cols-1 gap-1 text-sm text-slate-600 sm:grid-cols-3">
        <div><dt className="inline text-slate-400">Programación: </dt><dd className="inline font-medium">{source.schedule_label}</dd></div>
        <div><dt className="inline text-slate-400">Próxima ejecución: </dt><dd className="inline font-medium">{formatDate(source.next_run_at)}</dd></div>
        <div><dt className="inline text-slate-400">Última programada: </dt><dd className="inline">{formatDate(source.last_scheduled_run_at)}</dd></div>
      </dl>
      <ErrorBox error={save.error ?? run.error} />
      {jobId && <div className="mt-3"><JobStatus job={job} /></div>}
    </Card>
  )
}
