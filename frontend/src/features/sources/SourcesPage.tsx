import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Plus, RefreshCw, Trash2, Upload } from 'lucide-react'
import { useState } from 'react'
import { JobStatus } from '../../components/JobStatus'
import { Badge, Button, Card, EmptyState, ErrorBox, PageHeader, Spinner, Stat } from '../../components/ui'
import { api, download } from '../../lib/api'
import { formatBytes, formatDate, formatNumber } from '../../lib/format'
import type { Source } from '../../lib/types'
import { useJob } from '../../lib/useJob'
import { useWorkspace } from '../../lib/workspace'
import { AddSourceDialog } from './AddSourceDialog'

export function SourcesPage() {
  const ws = useWorkspace()
  const [adding, setAdding] = useState(false)
  return (
    <>
      <PageHeader
        title="Fuentes XML"
        description="Cada importación crea un snapshot inmutable del XML original. El catálogo activo es el último snapshot válido: si una importación falla, se conserva el anterior."
        actions={
          <Button variant="primary" onClick={() => setAdding(true)}>
            <Plus className="h-4 w-4" /> Añadir fuente
          </Button>
        }
      />
      {ws.loading ? <Spinner /> : ws.sources.length === 0 ? (
        <EmptyState title="Todavía no hay fuentes">Sube un archivo XML o indica una URL HTTPS para empezar.</EmptyState>
      ) : (
        <div className="space-y-6">
          <div className="flex flex-wrap gap-2">
            {ws.sources.map((s) => (
              <Button key={s.id} variant={s.id === ws.sourceId ? 'primary' : 'secondary'} size="sm" onClick={() => ws.setSourceId(s.id)}>
                {s.name}
              </Button>
            ))}
          </div>
          {ws.source && <SourceDetail source={ws.source} />}
        </div>
      )}
      <AddSourceDialog open={adding} onOpenChange={setAdding} />
    </>
  )
}

function SourceDetail({ source }: { source: Source }) {
  const qc = useQueryClient()
  const ws = useWorkspace()
  const [uploading, setUploading] = useState(false)
  const [jobId, setJobId] = useState<number | null>(null)
  const job = useJob(jobId, [['sources'], ['schema'], ['snapshots'], ['products'], ['dashboard'], ['catalog-issues']])
  const schema = useQuery({ queryKey: ['schema', source.id], queryFn: () => api.schema(source.id) })
  const snapshots = useQuery({ queryKey: ['snapshots', source.id], queryFn: () => api.snapshots(source.id) })
  const refresh = useMutation({ mutationFn: () => api.refreshSource(source.id), onSuccess: (r) => setJobId(r.job.id) })
  const remove = useMutation({
    mutationFn: () => api.deleteSource(source.id),
    onSuccess: () => {
      ws.setSourceId(null)
      void qc.invalidateQueries()
    },
  })
  const snap = source.active_snapshot
  const stats = (snap?.stats ?? {}) as { fields?: number; parse_seconds?: number; added?: number; removed?: number }

  return (
    <div className="space-y-6">
      <Card
        title={<span>{source.name} <Badge>{source.kind === 'url' ? 'URL' : 'Archivo'}</Badge></span>}
        actions={
          <>
            {source.kind === 'url' ? (
              <Button size="sm" onClick={() => refresh.mutate()} loading={refresh.isPending}>
                <RefreshCw className="h-3.5 w-3.5" /> Actualizar desde URL
              </Button>
            ) : (
              <Button size="sm" onClick={() => setUploading(true)}>
                <Upload className="h-3.5 w-3.5" /> Subir nueva versión
              </Button>
            )}
            {snap && (
              <Button size="sm" variant="ghost" onClick={() => void download(`/api/catalogs/${source.id}/original`, snap.original_filename ?? `original-${snap.id}.xml`)}>
                <Download className="h-3.5 w-3.5" /> XML original
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => { if (confirm(`¿Eliminar la fuente "${source.name}" con sus reglas, canales y versiones?`)) remove.mutate() }}>
              <Trash2 className="h-3.5 w-3.5" /> Eliminar
            </Button>
          </>
        }
      >
        {source.url && <p className="mb-3 break-all text-xs text-slate-500">{source.url}</p>}
        <ErrorBox error={refresh.error ?? remove.error} />
        {jobId && <div className="mb-3"><JobStatus job={job} /></div>}
        {snap ? (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="Productos" value={formatNumber(snap.product_count)} />
            <Stat label="Atributos" value={formatNumber(stats.fields)} />
            <Stat label="Formato" value={<span className="text-base uppercase">{snap.format}</span>} hint={`Nodo: ${snap.item_tag}`} />
            <Stat label="Tamaño" value={<span className="text-base">{formatBytes(snap.size_bytes)}</span>} hint={`Análisis: ${stats.parse_seconds ?? '—'} s`} />
            <Stat label="Cambios" value={<span className="text-base">{stats.added !== undefined ? `+${stats.added} / −${stats.removed}` : 'Primera carga'}</span>} hint={formatDate(snap.created_at)} />
          </div>
        ) : (
          <p className="text-sm text-slate-500">Aún no hay ningún snapshot válido.</p>
        )}
      </Card>

      <Card title="Atributos detectados">
        {schema.isLoading ? <Spinner /> : <ErrorBox error={schema.error} />}
        {schema.data && schema.data.fields.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-1.5">Clave interna</th>
                  <th>Elemento XML original</th>
                  <th>Estructura</th>
                  <th>Tipo aparente</th>
                  <th className="text-right">Cobertura</th>
                  <th className="text-right">Vacíos</th>
                  <th>Ejemplos</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {schema.data.fields.map((f) => (
                  <tr key={f.key} className="align-top">
                    <td className="py-1.5 font-mono text-xs font-semibold">{f.key}</td>
                    <td className="max-w-56 truncate font-mono text-xs text-slate-500" title={f.qname}>{f.qname}</td>
                    <td><Badge>{f.kind === 'list' ? `lista (máx. ${f.max_repeat})` : f.kind === 'nested' ? 'anidado' : 'escalar'}</Badge></td>
                    <td className="text-xs">{f.inferred_type}</td>
                    <td className="text-right tabular-nums">{(f.coverage * 100).toFixed(1)}%</td>
                    <td className="text-right tabular-nums">{formatNumber(f.empty_count)}</td>
                    <td className="max-w-md truncate text-xs text-slate-500" title={f.samples.join(' | ')}>{f.samples.slice(0, 3).join(' | ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Historial de snapshots">
        {snapshots.data && (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1.5">#</th>
                <th>Estado</th>
                <th>Fecha</th>
                <th className="text-right">Productos</th>
                <th className="text-right">Tamaño</th>
                <th>SHA-256</th>
                <th>Detalle</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {snapshots.data.items.map((s) => (
                <tr key={s.id}>
                  <td className="py-1.5">{s.id}{s.id === source.active_snapshot_id && <Badge tone="succeeded">activo</Badge>}</td>
                  <td><Badge tone={s.status}>{s.status}</Badge></td>
                  <td>{formatDate(s.created_at)}</td>
                  <td className="text-right tabular-nums">{formatNumber(s.product_count)}</td>
                  <td className="text-right">{formatBytes(s.size_bytes)}</td>
                  <td className="font-mono text-xs text-slate-500">{s.sha256?.slice(0, 12) ?? '—'}</td>
                  <td className="text-xs text-rose-700">{s.error ? `${s.error.message}${s.error.line ? ` (línea ${s.error.line})` : ''}` : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <AddSourceDialog open={uploading} onOpenChange={setUploading} existingSourceId={source.id} />
    </div>
  )
}
