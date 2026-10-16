import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { Badge, Button, Card, Dialog, EmptyState, ErrorBox, PageHeader, Spinner, Switch } from '../../components/ui'
import { api } from '../../lib/api'
import { formatDate } from '../../lib/format'
import type { Rule, RuleDefinition } from '../../lib/types'
import { useWorkspace } from '../../lib/workspace'
import { RuleEditor } from './RuleEditor'
import { emptyRule } from './ruleModel'

const SUGGESTION_KEY = 'feedstudio.suggestedRule'

/** Store a rule template (e.g. from a diagnostic) for the editor to pick up. */
export function suggestRule(definition: Partial<RuleDefinition>) {
  sessionStorage.setItem(SUGGESTION_KEY, JSON.stringify(definition))
}

export function RulesPage() {
  const ws = useWorkspace()
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [editing, setEditing] = useState<{ rule: Rule | null; definition: RuleDefinition; channelId: number | null } | null>(null)
  const [history, setHistory] = useState<Rule | null>(null)
  const sourceId = ws.sourceId

  const rules = useQuery({ queryKey: ['rules', sourceId, ws.channelId], queryFn: () => api.rules(sourceId as number, ws.channelId), enabled: !!sourceId })
  const schema = useQuery({ queryKey: ['schema', sourceId], queryFn: () => api.schema(sourceId as number), enabled: !!sourceId })
  const fields = (schema.data?.fields ?? []).map((f) => f.key)

  useEffect(() => {
    if (params.get('suggest') && sourceId) {
      const raw = sessionStorage.getItem(SUGGESTION_KEY)
      if (raw) setEditing({ rule: null, definition: { ...emptyRule(), ...(JSON.parse(raw) as Partial<RuleDefinition>) }, channelId: null })
      sessionStorage.removeItem(SUGGESTION_KEY)
      params.delete('suggest')
      setParams(params, { replace: true })
    }
  }, [params, setParams, sourceId])

  const toggle = useMutation({
    mutationFn: (r: Rule) => api.updateRule(r.id, { channel_id: r.channel_id, definition: { ...r.definition, enabled: !r.enabled } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['rules'] }),
  })
  const remove = useMutation({ mutationFn: (r: Rule) => api.deleteRule(r.id), onSuccess: () => void qc.invalidateQueries({ queryKey: ['rules'] }) })

  if (!ws.loading && !sourceId) return <EmptyState title="Sin fuente">{t('common.noSource')}</EmptyState>
  if (editing && sourceId) {
    return (
      <>
        <PageHeader title="Editor de reglas" description="Las reglas no modifican el XML original: se aplican en orden sobre una copia lógica de cada producto." />
        <RuleEditor sourceId={sourceId} channels={ws.channels} initial={editing} fields={fields} onDone={() => setEditing(null)} />
      </>
    )
  }

  const items = rules.data?.items ?? []
  return (
    <>
      <PageHeader
        title="Editor de reglas"
        description={`Orden de ejecución: primero las reglas globales y después las del canal${ws.channel ? ` “${ws.channel.name}”` : ''}; dentro de cada grupo, por prioridad ascendente.`}
        actions={<Button variant="primary" onClick={() => setEditing({ rule: null, definition: emptyRule(), channelId: null })} disabled={!sourceId}><Plus className="h-4 w-4" /> Nueva regla</Button>}
      />
      <ErrorBox error={rules.error} />
      {rules.isLoading ? <Spinner /> : items.length === 0 ? (
        <EmptyState title="No hay reglas">Crea una regla para transformar títulos, descripciones, precios o etiquetas personalizadas.</EmptyState>
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1.5">Orden</th>
                <th>Nombre</th>
                <th>Ámbito</th>
                <th>Destino</th>
                <th>Acciones</th>
                <th>Modificada</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((r, i) => (
                <tr key={r.id} className={r.enabled ? '' : 'opacity-60'}>
                  <td className="py-2 tabular-nums">{i + 1} <span className="text-xs text-slate-400">(p{r.priority})</span></td>
                  <td className="font-medium">{r.name}{r.definition.condition && <span className="ml-1 text-xs text-slate-400">condicional</span>}</td>
                  <td>{r.channel_id ? <Badge tone="running">{ws.channels.find((c) => c.id === r.channel_id)?.name ?? `Canal ${r.channel_id}`}</Badge> : <Badge>Global</Badge>}</td>
                  <td className="font-mono text-xs">{r.definition.target ?? '—'}</td>
                  <td className="text-xs">{r.definition.actions.map((a) => t(`actions.${a.type}`)).join(' → ')}</td>
                  <td className="text-xs text-slate-500">{formatDate(r.updated_at)} · v{r.version}</td>
                  <td><Switch checked={r.enabled} onCheckedChange={() => toggle.mutate(r)} label="" /></td>
                  <td className="whitespace-nowrap text-right">
                    <Button size="sm" variant="ghost" onClick={() => setEditing({ rule: r, definition: r.definition, channelId: r.channel_id })} aria-label="Editar"><Pencil className="h-3.5 w-3.5" /></Button>
                    <Button size="sm" variant="ghost" onClick={() => setHistory(r)} aria-label="Historial de versiones"><History className="h-3.5 w-3.5" /></Button>
                    <Button size="sm" variant="ghost" onClick={() => { if (confirm(`¿Eliminar la regla "${r.name}"?`)) remove.mutate(r) }} aria-label="Eliminar"><Trash2 className="h-3.5 w-3.5" /></Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      <VersionsDialog rule={history} onClose={() => setHistory(null)} onRestore={(definition) => { if (history) setEditing({ rule: history, definition, channelId: history.channel_id }); setHistory(null) }} />
    </>
  )
}

function VersionsDialog({ rule, onClose, onRestore }: { rule: Rule | null; onClose: () => void; onRestore: (d: RuleDefinition) => void }) {
  const versions = useQuery({ queryKey: ['rule-versions', rule?.id], queryFn: () => api.ruleVersions(rule!.id), enabled: !!rule })
  return (
    <Dialog open={!!rule} onOpenChange={(o) => !o && onClose()} title={`Versiones de “${rule?.name ?? ''}”`} wide>
      {versions.isLoading && <Spinner />}
      <ul className="space-y-2">
        {versions.data?.items.map((v) => (
          <li key={v.version} className="rounded border border-slate-200 p-2 text-sm">
            <div className="flex items-center justify-between">
              <span>v{v.version} · {formatDate(v.created_at)} · {v.created_by}</span>
              <Button size="sm" onClick={() => onRestore(v.definition)}>Editar a partir de esta versión</Button>
            </div>
            <pre className="mt-1 max-h-40 overflow-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(v.definition, null, 2)}</pre>
          </li>
        ))}
      </ul>
    </Dialog>
  )
}
