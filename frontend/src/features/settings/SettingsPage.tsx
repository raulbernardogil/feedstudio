import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Button, Card, ErrorBox, Field, Input, PageHeader, Spinner } from '../../components/ui'
import { api, getToken, setToken } from '../../lib/api'
import { formatDate } from '../../lib/format'

const LABELS: Record<string, string> = {
  version: 'Versión', environment: 'Entorno', job_backend: 'Ejecución de trabajos', database: 'Base de datos',
  public_base_url: 'URL base pública', max_feed_mb: 'Tamaño máximo de feed (MB)', max_upload_mb: 'Tamaño máximo de subida (MB)',
  allow_http_sources: 'Permitir fuentes HTTP sin TLS', snapshot_retention: 'Snapshots con productos conservados',
  publish_drop_threshold: 'Umbral de bloqueo de publicación', auth_enabled: 'Autenticación por token',
}

export function SettingsPage() {
  const qc = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const audit = useQuery({ queryKey: ['audit'], queryFn: api.auditLogs })
  const [token, setTokenValue] = useState(getToken() ?? '')
  return (
    <>
      <PageHeader title="Configuración" description="La configuración del servidor se define mediante variables de entorno (ver .env.example). Aquí se muestra en modo lectura." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Servidor">
          {settings.isLoading ? <Spinner /> : <ErrorBox error={settings.error} />}
          {settings.data && (
            <dl className="divide-y divide-slate-100 text-sm">
              {Object.entries(settings.data).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 py-1.5">
                  <dt className="text-slate-500">{LABELS[k] ?? k}</dt>
                  <dd className="font-mono text-xs">{typeof v === 'boolean' ? (v ? 'sí' : 'no') : k === 'publish_drop_threshold' ? `${Number(v) * 100}% menos productos` : String(v)}</dd>
                </div>
              ))}
            </dl>
          )}
        </Card>
        <Card title="Token de API">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); setToken(token || null); void qc.invalidateQueries() }}>
            <Field label="Token" hint="Necesario solo si el servidor define FEEDSTUDIO_API_TOKEN. Se guarda en este navegador.">
              <Input type="password" value={token} onChange={(e) => setTokenValue(e.target.value)} autoComplete="off" />
            </Field>
            <Button type="submit">Guardar token</Button>
          </form>
        </Card>
      </div>
      <Card title="Registro de auditoría" className="mt-6">
        {audit.isLoading && <Spinner />}
        <ErrorBox error={audit.error} />
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-500">
            <tr><th className="py-1.5">Fecha</th><th>Usuario</th><th>Acción</th><th>Entidad</th><th>Detalle</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {audit.data?.items.map((a) => (
              <tr key={a.id}>
                <td className="py-1.5">{formatDate(a.created_at)}</td>
                <td>{a.actor}</td>
                <td className="font-mono text-xs">{a.action}</td>
                <td className="text-xs">{a.entity} #{a.entity_id}</td>
                <td className="max-w-md truncate font-mono text-xs text-slate-500">{a.detail ? JSON.stringify(a.detail) : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  )
}
