import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Badge, ErrorBox, PageHeader, Pagination, Select, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { formatDate } from '../../lib/format'

export function JobsPage() {
  const { t } = useTranslation()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [kind, setKind] = useState('')
  const jobs = useQuery({
    queryKey: ['jobs', page, pageSize, kind],
    queryFn: () => api.jobs({ page, page_size: pageSize, kind: kind || undefined }),
    placeholderData: keepPreviousData,
    refetchInterval: 5000,
  })
  return (
    <>
      <PageHeader title="Historial de ejecuciones" description="Importaciones y generaciones ejecutadas en segundo plano por el servidor." actions={
        <Select value={kind} onChange={(e) => { setKind(e.target.value); setPage(1) }} aria-label="Tipo de trabajo">
          <option value="">Todos</option>
          <option value="import">Importaciones</option>
          <option value="generate">Generaciones</option>
        </Select>
      } />
      <ErrorBox error={jobs.error} />
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Tipo</th>
              <th className="px-3 py-2">Estado</th>
              <th className="px-3 py-2">Inicio</th>
              <th className="px-3 py-2">Fin</th>
              <th className="px-3 py-2">Duración</th>
              <th className="px-3 py-2">Resultado</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {jobs.data?.items.map((j) => {
              const secs = j.started_at && j.finished_at ? (new Date(j.finished_at).getTime() - new Date(j.started_at).getTime()) / 1000 : null
              return (
                <tr key={j.id}>
                  <td className="px-3 py-2">{j.id}</td>
                  <td className="px-3 py-2">{t(`jobs.${j.kind}`)}</td>
                  <td className="px-3 py-2"><Badge tone={j.status}>{t(`jobs.${j.status}`)}</Badge></td>
                  <td className="px-3 py-2">{formatDate(j.started_at)}</td>
                  <td className="px-3 py-2">{formatDate(j.finished_at)}</td>
                  <td className="px-3 py-2 tabular-nums">{secs === null ? '—' : `${secs.toFixed(1)} s`}</td>
                  <td className="max-w-md px-3 py-2 text-xs">
                    {j.error ? <span className="text-rose-700">{j.error.message}{j.error.line ? ` (línea ${j.error.line})` : ''}</span> : j.result ? <code className="text-slate-500">{JSON.stringify(j.result)}</code> : j.message}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {jobs.isLoading && <Spinner />}
        <Pagination page={page} pageSize={pageSize} total={jobs.data?.total ?? 0} onPage={setPage} onPageSize={(s) => { setPageSize(s); setPage(1) }} />
      </div>
    </>
  )
}
