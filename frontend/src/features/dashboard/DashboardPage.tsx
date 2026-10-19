import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { JobStatus } from '../../components/JobStatus'
import { Badge, Card, EmptyState, ErrorBox, PageHeader, Spinner, Stat } from '../../components/ui'
import { api } from '../../lib/api'
import { formatDate, formatNumber } from '../../lib/format'

const STEPS = [
  ['Añadir fuente XML', '/sources'],
  ['Revisar atributos detectados', '/sources'],
  ['Crear canal publicitario', '/channels'],
  ['Crear reglas de optimización', '/rules'],
  ['Previsualizar resultados', '/rules'],
  ['Generar y validar el feed', '/channels'],
  ['Revisar diagnóstico', '/validation'],
  ['Publicar o descargar', '/channels'],
  ['Programar actualizaciones y Google Drive', '/sources'],
] as const

export function DashboardPage() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard, refetchInterval: 10_000 })
  if (isLoading) return <Spinner />
  if (error) return <ErrorBox error={error} onRetry={() => void refetch()} />
  if (!data) return null
  return (
    <>
      <PageHeader title="Dashboard" description="Estado actual de fuentes, catálogos y publicaciones. Los indicadores de validación corresponden al catálogo original (antes de reglas)." />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Fuentes" value={formatNumber(data.sources)} />
        <Stat label="Productos importados" value={formatNumber(data.products)} />
        <Stat label="Productos válidos" value={formatNumber(data.valid)} tone="ok" hint="Sin errores ni advertencias" />
        <Stat label="Con advertencias" value={formatNumber(data.warnings)} tone="warn" />
        <Stat label="Con errores" value={formatNumber(data.errors)} tone="bad" />
        <Stat label="Reglas activas" value={formatNumber(data.active_rules)} />
        <Stat label="Última sincronización" value={<span className="text-base">{formatDate(data.last_sync)}</span>} />
        <Stat label="Próxima actualización" value={<span className="text-base">{data.next_sync ? formatDate(data.next_sync) : 'No programada'}</span>} hint={data.next_sync ? 'Actualización automática de fuentes' : <Link className="text-brand-600 underline" to="/sources">Programar en Fuentes XML</Link>} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Estado de publicación por canal" className="lg:col-span-2">
          {data.channels.length === 0 ? (
            <EmptyState title="Sin canales">
              <Link className="text-brand-600 underline" to="/channels">
                Crea un canal de Google Merchant Center
              </Link>
            </EmptyState>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-1">Canal</th>
                  <th>Publicado</th>
                  <th>Última versión</th>
                  <th>Errores</th>
                  <th>Advertencias</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.channels.map((c) => (
                  <tr key={c.id}>
                    <td className="py-2 font-medium">{c.name}</td>
                    <td>{c.published_version ? <Badge tone="succeeded">v{c.published_version.number} · {formatNumber(c.published_version.items)} productos</Badge> : <Badge>Sin publicar</Badge>}</td>
                    <td>{c.latest_version ? <Badge tone={c.latest_version.status}>v{c.latest_version.number} · {c.latest_version.status}</Badge> : '—'}</td>
                    <td>{c.latest_version ? formatNumber(c.latest_version.errors) : '—'}</td>
                    <td>{c.latest_version ? formatNumber(c.latest_version.warnings) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title="Flujo de trabajo">
          <ol className="space-y-1.5 text-sm">
            {STEPS.map(([label, to], i) => (
              <li key={label} className="flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-700">{i + 1}</span>
                <Link to={to} className="text-slate-700 hover:text-brand-700 hover:underline">
                  {label}
                </Link>
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <Card title="Ejecuciones recientes" className="mt-6">
        {data.recent_jobs.length === 0 ? <p className="text-sm text-slate-500">Aún no hay ejecuciones.</p> : (
          <div className="grid gap-3 md:grid-cols-2">
            {data.recent_jobs.map((j) => (
              <JobStatus key={j.id} job={j} />
            ))}
          </div>
        )}
      </Card>
    </>
  )
}
