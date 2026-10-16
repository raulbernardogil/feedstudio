import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Diff } from '../../components/Diff'
import { Badge, Button, Drawer, EmptyState, ErrorBox, Input, LevelBadge, PageHeader, Pagination, Select, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { text } from '../../lib/format'
import type { FeedItemRow } from '../../lib/types'
import { useWorkspace } from '../../lib/workspace'
import { AttributeList } from '../catalog/AttributeList'

type View = 'all' | 'changed' | 'errors' | 'excluded'

export function PreviewPage() {
  const ws = useWorkspace()
  const [params, setParams] = useSearchParams()
  const versions = useQuery({ queryKey: ['versions', String(ws.channelId)], queryFn: () => api.versions(ws.channelId as number), enabled: !!ws.channelId })
  const ready = (versions.data?.items ?? []).filter((v) => v.status === 'ready')
  const versionId = params.get('version') ? Number(params.get('version')) : ready[0]?.id ?? null
  const issueCode = params.get('issue_code') ?? ''
  const [view, setView] = useState<View>('all')
  const [ruleId, setRuleId] = useState<number | ''>('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [inspect, setInspect] = useState<FeedItemRow | null>(null)
  const rules = useQuery({ queryKey: ['rules', ws.sourceId, ws.channelId], queryFn: () => api.rules(ws.sourceId as number, ws.channelId), enabled: !!ws.sourceId })

  useEffect(() => setPage(1), [view, ruleId, q, issueCode, pageSize, versionId])

  const query = {
    page, page_size: pageSize, q,
    only_changed: view === 'changed' || undefined,
    only_errors: view === 'errors' || undefined,
    excluded: view === 'excluded' ? true : undefined,
    rule_id: ruleId || undefined,
    issue_code: issueCode || undefined,
  }
  const items = useQuery({ queryKey: ['version-items', versionId, query], queryFn: () => api.versionItems(versionId as number, query), enabled: !!versionId, placeholderData: keepPreviousData })

  if (!ws.loading && !ws.channel) return <EmptyState title="Sin canal">Crea un canal y genera una versión para comparar antes y después.</EmptyState>
  if (versions.isSuccess && !versionId) return <EmptyState title="Sin versiones generadas">En “Canales de exportación”, pulsa “Generar y validar”.</EmptyState>

  return (
    <>
      <PageHeader
        title="Vista previa antes / después"
        description="Resultado materializado de la versión generada: exactamente lo que contiene el XML exportado, con la regla responsable de cada cambio."
        actions={
          <Select value={versionId ?? ''} onChange={(e) => setParams({ version: e.target.value })} aria-label="Versión">
            {ready.map((v) => <option key={v.id} value={v.id}>{ws.channel?.name} · versión {v.number}{v.published ? ' (publicada)' : ''}</option>)}
          </Select>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-md border border-slate-300 bg-white p-0.5 text-sm" role="tablist">
          {([['all', 'Todos'], ['changed', 'Solo modificados'], ['errors', 'Solo con errores'], ['excluded', 'Excluidos']] as [View, string][]).map(([v, label]) => (
            <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)} className={`rounded px-3 py-1 ${view === v ? 'bg-brand-600 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>{label}</button>
          ))}
        </div>
        <Select value={ruleId} onChange={(e) => setRuleId(e.target.value ? Number(e.target.value) : '')} aria-label="Filtrar por regla">
          <option value="">Todas las reglas</option>
          {rules.data?.items.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </Select>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setQ(search) }}>
          <Input className="w-64" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="SKU o texto" aria-label="Buscar" />
          <Button type="submit"><Search className="h-4 w-4" /></Button>
        </form>
        {issueCode && (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2.5 py-1 text-xs text-rose-700">
            Incidencia: <code>{issueCode}</code>
            <button onClick={() => { params.delete('issue_code'); setParams(params) }} aria-label="Quitar filtro">×</button>
          </span>
        )}
      </div>
      <ErrorBox error={items.error} />
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2">SKU</th>
                <th className="px-3 py-2">Atributo</th>
                <th className="px-3 py-2">Original</th>
                <th className="px-3 py-2">Transformado</th>
                <th className="px-3 py-2">Regla</th>
                <th className="px-3 py-2">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 align-top">
              {items.data?.items.map((item) => {
                const fieldsChanged = [...new Set(item.changes.map((c) => c.field))]
                const rows = fieldsChanged.length ? fieldsChanged : [null]
                return rows.map((field, idx) => {
                  const rulesFor = item.changes.filter((c) => c.field === field).map((c) => c.rule_name)
                  return (
                    <tr key={`${item.id}-${field ?? 'none'}`} className="cursor-pointer hover:bg-brand-50/40" onClick={() => setInspect(item)}>
                      {idx === 0 && <td rowSpan={rows.length} className="px-3 py-2 font-mono text-xs">{item.external_id}</td>}
                      <td className="px-3 py-2 font-mono text-xs">{field ?? <span className="text-slate-400">—</span>}</td>
                      {field ? (
                        <>
                          <td className="max-w-xs px-3 py-2 text-slate-500"><div className="max-h-28 overflow-hidden">{text(item.original, field) || <em>vacío</em>}</div></td>
                          <td className="max-w-md px-3 py-2"><div className="max-h-28 overflow-hidden"><Diff before={text(item.original, field) || null} after={text(item.transformed, field) || null} /></div></td>
                          <td className="px-3 py-2 text-xs">{rulesFor.join(' → ')}</td>
                        </>
                      ) : (
                        <td colSpan={3} className="px-3 py-2 text-xs text-slate-400">Sin cambios: {text(item.transformed, 'title')}</td>
                      )}
                      {idx === 0 && (
                        <td rowSpan={rows.length} className="px-3 py-2">
                          <LevelBadge level={item.issue_level} />
                          {item.issues.slice(0, 2).map((i, n) => <div key={n} className="mt-1 text-xs text-slate-500">{i.message}</div>)}
                          {item.issues.length > 2 && <div className="text-xs text-slate-400">+{item.issues.length - 2} más</div>}
                        </td>
                      )}
                    </tr>
                  )
                })
              })}
            </tbody>
          </table>
          {items.isLoading && <Spinner />}
          {items.data?.items.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No hay productos con estos criterios.</p>}
        </div>
        <Pagination page={page} pageSize={pageSize} total={items.data?.total ?? 0} onPage={setPage} onPageSize={setPageSize} />
      </div>
      <Drawer open={!!inspect} onOpenChange={(o) => !o && setInspect(null)} title={`Producto ${inspect?.external_id ?? ''}`}>
        {inspect && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <LevelBadge level={inspect.issue_level} />
              {inspect.excluded && <Badge tone="excluded">Excluido del canal</Badge>}
            </div>
            {inspect.changes.length > 0 && (
              <div>
                <h3 className="mb-1 text-sm font-semibold">Traza de cambios</h3>
                <ol className="space-y-1 text-sm">
                  {inspect.changes.map((c, i) => (
                    <li key={i} className="rounded border border-slate-200 p-2">
                      <span className="text-xs text-slate-500">{i + 1}. {c.rule_name} → <code>{c.field}</code></span>
                      <div><Diff before={c.before} after={c.after} /></div>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {inspect.issues.length > 0 && (
              <ul className="space-y-1 text-sm">
                {inspect.issues.map((i, n) => <li key={n}><LevelBadge level={i.severity} /> {i.message}</li>)}
              </ul>
            )}
            <h3 className="text-sm font-semibold">Producto transformado</h3>
            <AttributeList data={inspect.transformed} changed={new Set(inspect.changes.map((c) => c.field))} />
            <details>
              <summary className="cursor-pointer text-sm font-semibold">Producto original</summary>
              <AttributeList data={inspect.original} />
            </details>
          </div>
        )}
      </Drawer>
    </>
  )
}
