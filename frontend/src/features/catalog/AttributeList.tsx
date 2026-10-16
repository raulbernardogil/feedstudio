import clsx from 'clsx'
import type { Attributes, Value } from '../../lib/types'

function ValueView({ value }: { value: Value }) {
  if (typeof value === 'string') return <span className="whitespace-pre-wrap break-words">{value === '' ? <em className="text-slate-400">(vacío)</em> : value}</span>
  return (
    <dl className="ml-2 border-l border-slate-200 pl-2">
      {Object.entries(value).map(([k, vs]) => (
        <div key={k} className="flex gap-2">
          <dt className="font-mono text-xs text-slate-500">{k}</dt>
          <dd>{vs.map((v, i) => <ValueView key={i} value={v} />)}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Presentational: every attribute of a product, optionally highlighting changed keys. */
export function AttributeList({ data, changed }: { data: Attributes; changed?: Set<string> }) {
  return (
    <dl className="divide-y divide-slate-100 text-sm">
      {Object.entries(data).map(([key, values]) => (
        <div key={key} className={clsx('grid grid-cols-[180px_1fr] gap-3 py-1.5', changed?.has(key) && 'bg-emerald-50')}>
          <dt className="font-mono text-xs font-semibold text-slate-600">
            {key}
            {values.length > 1 && <span className="ml-1 text-slate-400">×{values.length}</span>}
          </dt>
          <dd className="space-y-1">
            {values.map((v, i) => (
              <div key={i}>
                <ValueView value={v} />
              </div>
            ))}
          </dd>
        </div>
      ))}
    </dl>
  )
}
