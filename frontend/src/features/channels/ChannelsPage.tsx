import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Download, Play, Plus, RotateCcw, Send, ShieldCheck, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { JobStatus } from '../../components/JobStatus'
import { Badge, Button, Card, Dialog, EmptyState, ErrorBox, Field, Input, PageHeader, Spinner, Switch } from '../../components/ui'
import { ApiError, api, download } from '../../lib/api'
import { formatBytes, formatDate, formatNumber } from '../../lib/format'
import type { Channel, FeedVersion } from '../../lib/types'
import { useJob } from '../../lib/useJob'
import { useWorkspace } from '../../lib/workspace'
import { DriveDestinations } from './DriveDestinations'

const channelSchema = z.object({
  name: z.string().trim().min(1, 'Indica un nombre').max(200),
  title: z.string().trim().max(200).optional(),
  link: z.union([z.literal(''), z.string().trim().regex(/^https:\/\//, 'Usa una URL segura que empiece por https://')]).optional(),
  description: z.string().trim().max(1000).optional(),
  auto_publish: z.boolean(),
})
type ChannelForm = z.infer<typeof channelSchema>

const GOOGLE_NOTICES: Record<string, { tone: string; text: string }> = {
  connected: { tone: 'border-emerald-200 bg-emerald-50 text-emerald-800', text: 'Cuenta de Google conectada. Ya puedes añadir un destino de Google Drive a tus canales.' },
  denied: { tone: 'border-amber-200 bg-amber-50 text-amber-800', text: 'No se concedió el acceso a Google Drive.' },
  error: { tone: 'border-rose-200 bg-rose-50 text-rose-800', text: 'No se pudo completar la conexión con Google. Inténtalo de nuevo.' },
  no_refresh_token: { tone: 'border-rose-200 bg-rose-50 text-rose-800', text: 'Google no devolvió un token de acceso permanente. Revoca el acceso de Feed Studio en tu cuenta de Google y vuelve a conectar.' },
}

export function ChannelsPage() {
  const ws = useWorkspace()
  const [creating, setCreating] = useState(false)
  const [params, setParams] = useSearchParams()
  const notice = GOOGLE_NOTICES[params.get('google') ?? '']
  if (!ws.loading && !ws.source) return <EmptyState title="Sin fuente">Primero añade una fuente XML.</EmptyState>
  return (
    <>
      <PageHeader
        title="Canales de exportación"
        description="Cada canal genera versiones independientes del feed con sus propias reglas. Una versión se publica en una URL estable y revocable; si una generación falla, se mantiene la última versión publicada."
        actions={<Button variant="primary" onClick={() => setCreating(true)}><Plus className="h-4 w-4" /> Nuevo canal</Button>}
      />
      {notice && (
        <div className={`mb-4 flex items-start justify-between gap-3 rounded-md border p-3 text-sm ${notice.tone}`} role="status">
          {notice.text}
          <button onClick={() => { params.delete('google'); setParams(params) }} aria-label="Cerrar aviso">×</button>
        </div>
      )}
      <div className="mb-4 rounded-md border border-sky-200 bg-sky-50 p-3 text-sm text-sky-800">
        Disponible ahora: Google Merchant Center (XML RSS 2.0) y descarga CSV auxiliar. Meta y Pinterest están planificados para la fase 3 y todavía no se pueden crear.
      </div>
      {ws.channels.length === 0 ? <EmptyState title="Sin canales">Crea un canal de Google Merchant Center para generar el feed.</EmptyState> : (
        <div className="space-y-6">
          {ws.channels.map((c) => <ChannelCard key={c.id} channel={c} />)}
        </div>
      )}
      {ws.source && <CreateChannelDialog open={creating} onOpenChange={setCreating} sourceId={ws.source.id} />}
    </>
  )
}

function CreateChannelDialog({ open, onOpenChange, sourceId }: { open: boolean; onOpenChange: (o: boolean) => void; sourceId: number }) {
  const qc = useQueryClient()
  const ws = useWorkspace()
  const form = useForm<ChannelForm>({ resolver: zodResolver(channelSchema), defaultValues: { name: 'Google Merchant Center', title: '', link: '', description: '', auto_publish: true } })
  const create = useMutation({
    mutationFn: (v: ChannelForm) => api.createChannel({ source_id: sourceId, name: v.name, kind: 'google', settings: { title: v.title || undefined, link: v.link || undefined, description: v.description || undefined }, auto_publish: v.auto_publish }),
    onSuccess: (c) => {
      void qc.invalidateQueries({ queryKey: ['channels'] })
      ws.setChannelId(c.id)
      form.reset()
      onOpenChange(false)
    },
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Nuevo canal de Google Merchant Center" description="Los datos del <channel> se escriben en la cabecera del XML.">
      <form className="space-y-3" onSubmit={form.handleSubmit((v) => create.mutate(v))}>
        <Field label="Nombre" error={form.formState.errors.name?.message}><Input {...form.register('name')} /></Field>
        <Field label="Título del feed"><Input {...form.register('title')} placeholder="Nombre de la tienda" /></Field>
        <Field label="URL de la tienda" error={form.formState.errors.link?.message}><Input {...form.register('link')} placeholder="https://www.mitienda.com" /></Field>
        <Field label="Descripción"><Input {...form.register('description')} /></Field>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" {...form.register('auto_publish')} />
          <span>Publicar automáticamente en cada actualización programada (se mantiene la protección contra caídas bruscas de productos)</span>
        </label>
        <ErrorBox error={create.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" onClick={() => onOpenChange(false)}>Cancelar</Button>
          <Button type="submit" variant="primary" loading={create.isPending}>Crear canal</Button>
        </div>
      </form>
    </Dialog>
  )
}

function ChannelCard({ channel }: { channel: Channel }) {
  const qc = useQueryClient()
  const [jobId, setJobId] = useState<number | null>(null)
  const [forceFor, setForceFor] = useState<{ version: FeedVersion; detail: Record<string, unknown> } | null>(null)
  const job = useJob(jobId, [['versions', String(channel.id)], ['channels'], ['dashboard']])
  const versions = useQuery({ queryKey: ['versions', String(channel.id)], queryFn: () => api.versions(channel.id) })
  const publications = useQuery({ queryKey: ['publications', channel.id], queryFn: () => api.publications(channel.id) })
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['versions', String(channel.id)] })
    void qc.invalidateQueries({ queryKey: ['publications', channel.id] })
    void qc.invalidateQueries({ queryKey: ['channels'] })
    void qc.invalidateQueries({ queryKey: ['dashboard'] })
  }
  const generate = useMutation({ mutationFn: () => api.generate(channel.id), onSuccess: (r) => { setJobId(r.job.id); refresh() } })
  const publish = useMutation({
    mutationFn: ({ version, force }: { version: FeedVersion; force: boolean }) => api.publish(version.id, force),
    onSuccess: () => { setForceFor(null); refresh() },
    onError: (err, vars) => {
      if (err instanceof ApiError && err.code === 'publish_blocked' && !vars.force) setForceFor({ version: vars.version, detail: err.details as Record<string, unknown> })
    },
  })
  const rotate = useMutation({ mutationFn: () => api.rotateToken(channel.id), onSuccess: refresh })
  const remove = useMutation({ mutationFn: () => api.deleteChannel(channel.id), onSuccess: () => void qc.invalidateQueries() })
  const running = job && (job.status === 'queued' || job.status === 'running')
  const autoPublish = useMutation({ mutationFn: (value: boolean) => api.updateChannel(channel.id, { auto_publish: value }), onSuccess: refresh })

  return (
    <Card
      title={<span>{channel.name} <Badge tone="running">Google Merchant Center</Badge></span>}
      actions={
        <>
          <Button size="sm" variant="primary" onClick={() => generate.mutate()} loading={generate.isPending || !!running}><Play className="h-3.5 w-3.5" /> Generar y validar</Button>
          <Button size="sm" variant="ghost" onClick={() => { if (confirm(`¿Eliminar el canal "${channel.name}", sus reglas y versiones?`)) remove.mutate() }} aria-label="Eliminar canal"><Trash2 className="h-3.5 w-3.5" /></Button>
        </>
      }
    >
      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-500">URL pública:</span>
        <code className="break-all rounded bg-slate-100 px-2 py-0.5 text-xs">{channel.public_url}</code>
        <Button size="sm" variant="ghost" onClick={() => void navigator.clipboard.writeText(channel.public_url)} aria-label="Copiar URL"><Copy className="h-3.5 w-3.5" /></Button>
        <Button size="sm" variant="ghost" onClick={() => { if (confirm('La URL actual dejará de funcionar. ¿Continuar?')) rotate.mutate() }}><RotateCcw className="h-3.5 w-3.5" /> Revocar y regenerar</Button>
        {channel.published_version ? <Badge tone="succeeded">Publicada v{channel.published_version.number}</Badge> : <Badge>Sin publicar (la URL responde 404)</Badge>}
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <Switch checked={channel.auto_publish} onCheckedChange={(v) => autoPublish.mutate(v)} label="Publicar automáticamente en cada actualización programada" />
        <span className="text-xs text-slate-500">La programación se configura en Fuentes XML → Actualización automática.</span>
      </div>
      <ErrorBox error={generate.error ?? (publish.error instanceof ApiError && publish.error.code === 'publish_blocked' ? null : publish.error) ?? rotate.error ?? autoPublish.error} />
      {jobId && <div className="mb-4"><JobStatus job={job} /></div>}

      {versions.isLoading ? <Spinner /> : (versions.data?.items.length ?? 0) === 0 ? <p className="text-sm text-slate-500">Aún no hay versiones. Pulsa “Generar y validar”.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1.5">Versión</th>
                <th>Fecha</th>
                <th>Estado</th>
                <th className="text-right">Exportados</th>
                <th className="text-right">Excluidos</th>
                <th className="text-right">Modificados</th>
                <th className="text-right">Errores</th>
                <th className="text-right">Advertencias</th>
                <th className="text-right">Tamaño</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {versions.data?.items.map((v) => (
                <tr key={v.id}>
                  <td className="py-2 font-medium">v{v.number} {v.published && <Badge tone="succeeded">publicada</Badge>}</td>
                  <td>{formatDate(v.created_at)}</td>
                  <td><Badge tone={v.status}>{v.status}</Badge>{v.error && <span className="ml-1 text-xs text-rose-700">{v.error.message}</span>}</td>
                  <td className="text-right tabular-nums">{formatNumber(v.item_count)}</td>
                  <td className="text-right tabular-nums">{formatNumber(v.excluded_count)}</td>
                  <td className="text-right tabular-nums">{formatNumber(v.changed_count)}</td>
                  <td className="text-right tabular-nums text-rose-700">{formatNumber(v.error_count)}</td>
                  <td className="text-right tabular-nums text-amber-700">{formatNumber(v.warning_count)}</td>
                  <td className="text-right">{formatBytes(v.size_bytes)}</td>
                  <td className="whitespace-nowrap text-right">
                    {v.status === 'ready' && (
                      <>
                        <Link to={`/validation?version=${v.id}`} className="inline-flex items-center gap-1 px-2 text-xs text-brand-700 hover:underline"><ShieldCheck className="h-3.5 w-3.5" /> Diagnóstico</Link>
                        <Button size="sm" variant="ghost" onClick={() => void download(`/api/feed-versions/${v.id}/download`, `google-v${v.number}.xml`, { format: 'xml' })}><Download className="h-3.5 w-3.5" /> XML</Button>
                        <Button size="sm" variant="ghost" onClick={() => void download(`/api/feed-versions/${v.id}/download`, `google-v${v.number}.csv`, { format: 'csv' })}>CSV</Button>
                        {!v.published && (
                          <Button size="sm" onClick={() => publish.mutate({ version: v, force: false })} loading={publish.isPending && publish.variables?.version.id === v.id}>
                            <Send className="h-3.5 w-3.5" /> {channel.published_version_id && v.id < channel.published_version_id ? 'Restaurar' : 'Publicar'}
                          </Button>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <DriveDestinations channel={channel} />
      {publications.data && publications.data.items.length > 0 && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-slate-600">Historial de publicaciones ({publications.data.items.length})</summary>
          <ul className="mt-2 space-y-1 text-xs text-slate-600">
            {publications.data.items.map((p) => <li key={p.id}>{formatDate(p.published_at)} · {p.action === 'rollback' ? 'Restauración' : 'Publicación'} de la versión #{p.version_id} · {p.published_by}</li>)}
          </ul>
        </details>
      )}
      <Dialog open={!!forceFor} onOpenChange={(o) => !o && setForceFor(null)} title="Publicación bloqueada por seguridad"
        description="La nueva versión reduce drásticamente el número de productos respecto a la publicada.">
        {forceFor && (
          <div className="space-y-4 text-sm">
            <p>Productos publicados actualmente: <strong>{formatNumber(forceFor.detail.current_items as number)}</strong>. Nueva versión: <strong>{formatNumber(forceFor.detail.new_items as number)}</strong>.</p>
            <p>Revisa las reglas de exclusión y la fuente antes de continuar.</p>
            <div className="flex justify-end gap-2">
              <Button onClick={() => setForceFor(null)}>Cancelar</Button>
              <Button variant="danger" onClick={() => publish.mutate({ version: forceFor.version, force: true })} loading={publish.isPending}>Publicar de todos modos</Button>
            </div>
          </div>
        )}
      </Dialog>
    </Card>
  )
}
