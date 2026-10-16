import { AlertTriangle } from 'lucide-react'
import { Diff } from '../../components/Diff'
import { Badge, LevelBadge, Pagination } from '../../components/ui'
import { formatNumber } from '../../lib/format'
import type { PreviewResult } from '../../lib/types'

/** Presentational: backend preview of a draft rule (same engine as feed generation). */
export function RulePreview({ result, onPage }: { result: PreviewResult; onPage: (p: number) => void }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 text-sm">
        <Badge tone="info">Analizados: {formatNumber(result.scanned)}</Badge>
        <Badge tone="running">Cumplen la condición: {formatNumber(result.matched)}</Badge>
        <Badge tone="succeeded">Modificados: {formatNumber(result.affected)}</Badge>
        {result.excluded > 0 && <Badge tone="excluded">Excluidos: {formatNumber(result.excluded)}</Badge>}
        {result.truncated && <Badge tone="warning">Vista parcial: límite de análisis alcanzado</Badge>}
      </div>
      {result.conflicts.length > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-sm text-amber-800">
          <AlertTriangle className="mt-0.5 h-4 w-4" />
          <span>
            Posible conflicto: {result.conflicts.map((c) => `“${c.name}” (prioridad ${c.priority})`).join(', ')} se ejecuta después sobre el mismo atributo y puede sobrescribir este resultado.
          </span>
        </div>
      )}
      {Object.keys(result.new_issue_counts).length > 0 && (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-2 text-sm text-rose-800">
          Nuevas incidencias de validación provocadas por esta regla:{' '}
          {Object.entries(result.new_issue_counts).map(([code, n]) => <span key={code} className="mr-2"><code>{code}</code> ×{n}</span>)}
        </div>
      )}
      <div className="overflow-x-auto rounded-md border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">SKU</th>
              <th className="px-3 py-2">Original</th>
              <th className="px-3 py-2">Antes de esta regla</th>
              <th className="px-3 py-2">Cambio</th>
              <th className="px-3 py-2">Valor final</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 align-top">
            {result.items.map((row) => (
              <tr key={row.product_id}>
                <td className="px-3 py-2 font-mono text-xs">{row.external_id}</td>
                <td className="max-w-xs px-3 py-2 text-slate-500">{row.original ?? <em>vacío</em>}</td>
                <td className="max-w-xs px-3 py-2 text-slate-500">{row.before ?? <em>vacío</em>}</td>
                <td className="max-w-md px-3 py-2">
                  {row.excluded ? <Badge tone="excluded">Excluido</Badge> : <Diff before={row.before} after={row.after} />}
                  {row.new_issues.map((i, n) => <div key={n} className="mt-1"><LevelBadge level={i.severity} /> <span className="text-xs">{i.message}</span></div>)}
                  {row.rule_issues.map((i, n) => <div key={n} className="mt-1 text-xs text-amber-700">{i.message}</div>)}
                </td>
                <td className="max-w-xs px-3 py-2">{row.final ?? <em className="text-slate-400">vacío</em>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {result.items.length === 0 && <p className="p-4 text-center text-sm text-slate-500">La regla no modifica ningún producto del catálogo actual.</p>}
        <Pagination page={result.page} pageSize={result.page_size} total={result.affected} onPage={onPage} />
      </div>
    </div>
  )
}
