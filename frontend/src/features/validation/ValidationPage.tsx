import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Wand2 } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Card, EmptyState, ErrorBox, LevelBadge, PageHeader, Select, Spinner, Stat } from '../../components/ui'
import { api } from '../../lib/api'
import { formatNumber } from '../../lib/format'
import type { IssueSummary, Severity } from '../../lib/types'
import { useWorkspace } from '../../lib/workspace'
import { suggestRule } from '../rules/RulesPage'

const SECTIONS: { severity: Severity; title: string }[] = [
  { severity: 'error', title: 'Errores bloqueantes' },
  { severity: 'warning', title: 'Advertencias' },
  { severity: 'recommendation', title: 'Recomendaciones de optimización' },
]

export function ValidationPage() {
  const ws = useWorkspace()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const versionParam = params.get('version')
  const versions = useQuery({ queryKey: ['versions', String(ws.channelId)], queryFn: () => api.versions(ws.channelId as number), enabled: !!ws.channelId })
  const ready = (versions.data?.items ?? []).filter((v) => v.status === 'ready')
  const versionId = versionParam === 'original' ? null : versionParam ? Number(versionParam) : ready[0]?.id ?? null
  const mode: 'original' | 'version' = versionId ? 'version' : 'original'

  const original = useQuery({ queryKey: ['catalog-issues', ws.sourceId], queryFn: () => api.catalogIssues(ws.sourceId as number), enabled: !!ws.sourceId && mode === 'original' })
  const stats = useQuery({ queryKey: ['catalog-stats', ws.sourceId], queryFn: () => api.catalogStats(ws.sourceId as number), enabled: !!ws.sourceId && mode === 'original' })
  const version = useQuery({ queryKey: ['version-issues', versionId], queryFn: () => api.versionIssues(versionId as number), enabled: mode === 'version' })

  if (!ws.loading && !ws.source) return <EmptyState title="Sin fuente">Primero añade una fuente XML.</EmptyState>
  const issues: IssueSummary[] = (mode === 'version' ? version.data?.issues : original.data?.issues) ?? []
  const loading = mode === 'version' ? version.isLoading : original.isLoading

  const openProducts = (code: string) => {
    if (mode === 'version' && versionId) navigate(`/preview?version=${versionId}&issue_code=${code}`)
    else navigate(`/catalog?issue_code=${code}`)
  }
  const createRule = (issue: IssueSummary) => {
    if (!issue.suggested_rule) return
    suggestRule(issue.suggested_rule)
    navigate('/rules?suggest=1')
  }

  return (
    <>
      <PageHeader
        title="Validación y diagnóstico"
        description="Comprobaciones locales basadas en la especificación de Google Merchant Center (consultada el 2026-10-16). Superarlas no garantiza la aprobación de Google: Merchant Center aplica revisiones adicionales."
        actions={
          <Select value={versionParam ?? (versionId ? String(versionId) : 'original')} onChange={(e) => setParams({ version: e.target.value })} aria-label="Datos a diagnosticar">
            <option value="original">Catálogo original (sin reglas)</option>
            {ready.map((v) => <option key={v.id} value={v.id}>{ws.channel?.name} · versión {v.number}</option>)}
          </Select>
        }
      />
      <ErrorBox error={original.error ?? version.error} />
      {loading ? <Spinner /> : (
        <>
          {mode === 'version' && version.data ? (
            <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-5">
              <Stat label="Analizados" value={formatNumber(version.data.analyzed)} hint={`${formatNumber(version.data.excluded)} excluidos por reglas`} />
              <Stat label="Sin errores" value={formatNumber(version.data.valid)} tone="ok" />
              <Stat label="Con errores" value={formatNumber(version.data.errors)} tone="bad" hint={version.data.previous ? `Antes: ${formatNumber(version.data.previous.error_count)}` : undefined} />
              <Stat label="Con advertencias" value={formatNumber(version.data.warnings)} tone="warn" hint={version.data.previous ? `Antes: ${formatNumber(version.data.previous.warning_count)}` : undefined} />
              <Stat label="Tipos de incidencia" value={formatNumber(issues.length)} />
            </div>
          ) : original.data && (
            <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
              <Stat label="Productos analizados" value={formatNumber(original.data.product_count)} />
              <Stat label="Tipos de incidencia" value={formatNumber(issues.length)} />
              <Stat label="Productos con errores" value={formatNumber(stats.data?.levels.error ?? 0)} tone="bad" hint={`${formatNumber(stats.data?.levels.warning ?? 0)} con advertencias como máximo nivel`} />
              <Stat label="Diagnóstico" value={<span className="text-base">Datos originales</span>} hint="Genera una versión para ver el efecto de las reglas" />
            </div>
          )}
          {issues.length === 0 ? <EmptyState title="Sin incidencias detectadas" /> : SECTIONS.map(({ severity, title }) => {
            const rows = issues.filter((i) => i.severity === severity)
            if (!rows.length) return null
            return (
              <Card key={severity} title={`${title} (${rows.length})`} className="mb-4">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase text-slate-500">
                    <tr>
                      <th className="py-1.5 pr-3">Incidencia</th>
                      <th className="px-3 text-right">Productos</th>
                      {mode === 'version' && <th className="px-3 text-right">Versión anterior</th>}
                      <th className="px-3">Acción recomendada</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {rows.map((i) => (
                      <tr key={i.code} className="align-top">
                        <td className="py-2 pr-3">
                          <div className="flex items-center gap-2"><LevelBadge level={i.severity} /> <span className="font-medium">{i.title}</span></div>
                          <code className="text-xs text-slate-400">{i.code}</code>
                        </td>
                        <td className="px-3 text-right tabular-nums">{formatNumber(i.count)}</td>
                        {mode === 'version' && <td className="px-3 text-right tabular-nums text-slate-500">{i.previous_count === undefined || i.previous_count === null ? (version.data?.previous ? '0' : '—') : formatNumber(i.previous_count)}</td>}
                        <td className="max-w-md px-3 text-xs text-slate-600">
                          {i.recommendation}
                          {i.source && <a href={i.source} target="_blank" rel="noreferrer noopener" className="ml-1 inline-flex items-center text-brand-700 hover:underline">especificación <ExternalLink className="ml-0.5 h-3 w-3" /></a>}
                        </td>
                        <td className="whitespace-nowrap text-right">
                          <Button size="sm" variant="ghost" onClick={() => openProducts(i.code)}>Ver productos</Button>
                          {i.suggested_rule && <Button size="sm" onClick={() => createRule(i)}><Wand2 className="h-3.5 w-3.5" /> Crear regla</Button>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )
          })}
        </>
      )}
    </>
  )
}
