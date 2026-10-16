import { ArrowDown, ArrowUp, Plus, RotateCcw, X } from 'lucide-react'
import { useState } from 'react'
import { Button, Dialog, Select } from '../../components/ui'
import type { SchemaField } from '../../lib/types'
import type { ColumnSpec } from './columns'
import { DEFAULT_COLUMNS, STATUS_COLUMN } from './columns'

/** Presentational: add, remove and reorder table columns. */
export function ColumnPicker({ open, onOpenChange, columns, onChange, fields }: {
  open: boolean
  onOpenChange: (o: boolean) => void
  columns: ColumnSpec[]
  onChange: (c: ColumnSpec[]) => void
  fields: SchemaField[]
}) {
  const [toAdd, setToAdd] = useState('')
  const used = new Set(columns.map((c) => c.key))
  const available = fields.filter((f) => !used.has(f.key))
  const move = (i: number, d: number) => {
    const next = [...columns]
    const [item] = next.splice(i, 1)
    next.splice(i + d, 0, item)
    onChange(next)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Columnas de la tabla" description="Puedes mostrar cualquier atributo detectado en el catálogo.">
      <ul className="divide-y divide-slate-100 rounded-md border border-slate-200">
        {columns.map((c, i) => (
          <li key={c.key} className="flex items-center gap-2 px-3 py-1.5 text-sm">
            <span className="flex-1">
              {c.label} {c.key !== STATUS_COLUMN && c.label !== c.key && <code className="text-xs text-slate-400">{c.key}</code>}
            </span>
            <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Subir ${c.label}`}><ArrowUp className="h-3.5 w-3.5" /></Button>
            <Button size="sm" variant="ghost" disabled={i === columns.length - 1} onClick={() => move(i, 1)} aria-label={`Bajar ${c.label}`}><ArrowDown className="h-3.5 w-3.5" /></Button>
            <Button size="sm" variant="ghost" onClick={() => onChange(columns.filter((x) => x.key !== c.key))} aria-label={`Quitar ${c.label}`}><X className="h-3.5 w-3.5" /></Button>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <Select className="flex-1" value={toAdd} onChange={(e) => setToAdd(e.target.value)} aria-label="Atributo a añadir">
          <option value="">Añadir atributo…</option>
          {available.map((f) => (
            <option key={f.key} value={f.key}>{f.key} ({(f.coverage * 100).toFixed(0)}%)</option>
          ))}
          {!used.has(STATUS_COLUMN) && <option value={STATUS_COLUMN}>Estado de validación</option>}
        </Select>
        <Button disabled={!toAdd} onClick={() => { onChange([...columns, { key: toAdd, label: toAdd === STATUS_COLUMN ? 'Estado' : toAdd }]); setToAdd('') }}>
          <Plus className="h-4 w-4" /> Añadir
        </Button>
        <Button variant="ghost" onClick={() => onChange(DEFAULT_COLUMNS)} title="Restablecer columnas"><RotateCcw className="h-4 w-4" /></Button>
      </div>
    </Dialog>
  )
}
