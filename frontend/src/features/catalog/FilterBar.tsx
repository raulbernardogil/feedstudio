import { Plus, X } from 'lucide-react'
import { useState } from 'react'
import { Button, Input, Select } from '../../components/ui'
import type { SchemaField } from '../../lib/types'

export interface AttributeFilter {
  field: string
  op: 'equals' | 'not_equals' | 'contains' | 'not_contains' | 'starts_with' | 'is_empty' | 'not_empty' | 'gt' | 'lt'
  value?: string
}

const OPS: { value: AttributeFilter['op']; label: string; unary?: boolean }[] = [
  { value: 'contains', label: 'contiene' },
  { value: 'not_contains', label: 'no contiene' },
  { value: 'equals', label: 'es igual a' },
  { value: 'not_equals', label: 'no es igual a' },
  { value: 'starts_with', label: 'empieza por' },
  { value: 'is_empty', label: 'está vacío', unary: true },
  { value: 'not_empty', label: 'no está vacío', unary: true },
  { value: 'gt', label: 'mayor que' },
  { value: 'lt', label: 'menor que' },
]

export const opLabel = (op: string) => OPS.find((o) => o.value === op)?.label ?? op

/** Presentational: builds server-side attribute filters. */
export function FilterBar({ fields, filters, onChange }: { fields: SchemaField[]; filters: AttributeFilter[]; onChange: (f: AttributeFilter[]) => void }) {
  const [draft, setDraft] = useState<AttributeFilter>({ field: 'brand', op: 'contains', value: '' })
  const unary = OPS.find((o) => o.value === draft.op)?.unary
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={draft.field} onChange={(e) => setDraft({ ...draft, field: e.target.value })} aria-label="Atributo del filtro">
          {fields.map((f) => <option key={f.key} value={f.key}>{f.key}</option>)}
        </Select>
        <Select value={draft.op} onChange={(e) => setDraft({ ...draft, op: e.target.value as AttributeFilter['op'] })} aria-label="Operador del filtro">
          {OPS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
        {!unary && <Input className="w-48" value={draft.value ?? ''} onChange={(e) => setDraft({ ...draft, value: e.target.value })} placeholder="valor" aria-label="Valor del filtro" />}
        <Button size="sm" onClick={() => onChange([...filters, unary ? { field: draft.field, op: draft.op } : draft])} disabled={!unary && !draft.value}>
          <Plus className="h-3.5 w-3.5" /> Filtro
        </Button>
      </div>
      {filters.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {filters.map((f, i) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-0.5 text-xs text-brand-700">
              <code>{f.field}</code> {opLabel(f.op)} {f.value && <strong>“{f.value}”</strong>}
              <button onClick={() => onChange(filters.filter((_, j) => j !== i))} aria-label="Quitar filtro"><X className="h-3 w-3" /></button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
