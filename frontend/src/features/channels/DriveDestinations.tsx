import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CloudUpload, ExternalLink, HardDrive, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { JobStatus } from '../../components/JobStatus'
import { Badge, Button, ErrorBox, Input, Select, Switch } from '../../components/ui'
import { api } from '../../lib/api'
import { formatDate } from '../../lib/format'
import type { Channel } from '../../lib/types'
import { useJob } from '../../lib/useJob'

/** Container: Google Drive destinations of a channel (upload after each publication). */
export function DriveDestinations({ channel }: { channel: Channel }) {
  const qc = useQueryClient()
  const google = useQuery({ queryKey: ['google'], queryFn: api.googleStatus })
  const destinations = useQuery({ queryKey: ['destinations', channel.id], queryFn: () => api.destinations(channel.id) })
  const [fileName, setFileName] = useState(`${channel.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'feed'}.xml`)
  const [folder, setFolder] = useState('')
  const [accountId, setAccountId] = useState<number | ''>('')
  const [jobId, setJobId] = useState<number | null>(null)
  const job = useJob(jobId, [['destinations', String(channel.id)], ['destinations']])
  const refresh = () => void qc.invalidateQueries({ queryKey: ['destinations', channel.id] })

  const connect = useMutation({ mutationFn: api.googleAuthorize, onSuccess: ({ url }) => { window.location.href = url } })
  const create = useMutation({
    mutationFn: () => api.createDestination(channel.id, { google_account_id: Number(accountId || accounts[0]?.id), file_name: fileName, folder: folder || null }),
    onSuccess: () => { setFolder(''); refresh() },
  })
  const toggle = useMutation({ mutationFn: (d: { id: number; enabled: boolean }) => api.updateDestination(d.id, { enabled: d.enabled }), onSuccess: refresh })
  const remove = useMutation({ mutationFn: api.deleteDestination, onSuccess: refresh })
  const deliver = useMutation({ mutationFn: api.deliverNow, onSuccess: (r) => setJobId(r.job.id) })

  if (google.isLoading) return null
  const accounts = (google.data?.accounts ?? []).filter((a) => a.status === 'active')
  const invalid = (google.data?.accounts ?? []).filter((a) => a.status === 'invalid')
  const items = destinations.data?.items ?? []

  return (
    <div className="mt-5 rounded-md border border-slate-200 p-3">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700"><HardDrive className="h-4 w-4" /> Google Drive</h3>
      {!google.data?.configured ? (
        <p className="text-sm text-slate-500">
          La subida a Google Drive no está configurada en el servidor. Hay que crear un cliente OAuth de Google y definir
          <code className="mx-1">FEEDSTUDIO_GOOGLE_CLIENT_ID</code>, <code className="mx-1">FEEDSTUDIO_GOOGLE_CLIENT_SECRET</code> y
          <code className="mx-1">FEEDSTUDIO_SECRET_KEY</code> (ver <code>docs/google-drive.md</code>).
        </p>
      ) : (
        <>
          <p className="mb-3 text-xs text-slate-500">
            Tras cada publicación (manual o programada) el XML se sube a Drive actualizando siempre el mismo archivo, así su enlace no cambia.
            Feed Studio solo puede ver los archivos que él mismo crea (permiso <code>drive.file</code>).
          </p>
          {invalid.length > 0 && (
            <p className="mb-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
              Google revocó o caducó el acceso de {invalid.map((a) => a.email).join(', ')}. Vuelve a conectar la cuenta.
            </p>
          )}
          {items.length > 0 && (
            <ul className="mb-3 divide-y divide-slate-100 text-sm">
              {items.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-2 py-2">
                  <span className="font-medium">{d.file_name}</span>
                  {d.folder_id ? <span className="text-xs text-slate-500">carpeta {d.folder_id}</span> : <span className="text-xs text-slate-500">Mi unidad</span>}
                  {d.last_status === 'succeeded' && <Badge tone="succeeded">subido {formatDate(d.last_delivered_at)}</Badge>}
                  {d.last_status === 'failed' && <Badge tone="failed">error</Badge>}
                  {!d.last_status && <Badge>pendiente de la próxima publicación</Badge>}
                  {d.remote_url && <a href={d.remote_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-xs text-brand-700 hover:underline">abrir en Drive <ExternalLink className="h-3 w-3" /></a>}
                  <span className="ml-auto flex items-center gap-2">
                    <Switch checked={d.enabled} onCheckedChange={(enabled) => toggle.mutate({ id: d.id, enabled })} label={d.enabled ? 'Activo' : 'Pausado'} />
                    <Button size="sm" onClick={() => deliver.mutate(d.id)} disabled={!channel.published_version_id} title={channel.published_version_id ? 'Subir la versión publicada ahora' : 'Publica una versión primero'}>
                      <CloudUpload className="h-3.5 w-3.5" /> Subir ahora
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => { if (confirm(`¿Dejar de subir a «${d.file_name}»? El archivo de Drive no se borra.`)) remove.mutate(d.id) }} aria-label="Eliminar destino"><Trash2 className="h-3.5 w-3.5" /></Button>
                  </span>
                  {d.last_error && <p className="w-full text-xs text-rose-700">{d.last_error}</p>}
                </li>
              ))}
            </ul>
          )}
          {accounts.length === 0 ? (
            <Button size="sm" variant="primary" onClick={() => connect.mutate()} loading={connect.isPending}>Conectar Google Drive</Button>
          ) : (
            <form className="flex flex-wrap items-center gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); create.mutate() }}>
              <Select value={accountId || accounts[0].id} onChange={(e) => setAccountId(Number(e.target.value))} aria-label="Cuenta de Google">
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.email ?? `Cuenta ${a.id}`}</option>)}
              </Select>
              <Input className="w-56" value={fileName} onChange={(e) => setFileName(e.target.value)} placeholder="feed.xml" aria-label="Nombre del archivo" required />
              <Input className="w-72" value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="Carpeta (URL o ID, opcional)" aria-label="Carpeta de Drive" />
              <Button size="sm" type="submit" loading={create.isPending}>Añadir destino</Button>
              <Button size="sm" variant="ghost" type="button" onClick={() => connect.mutate()}>Conectar otra cuenta</Button>
            </form>
          )}
        </>
      )}
      <ErrorBox error={connect.error ?? create.error ?? deliver.error ?? toggle.error ?? remove.error} />
      {jobId && <div className="mt-2"><JobStatus job={job} /></div>}
    </div>
  )
}
