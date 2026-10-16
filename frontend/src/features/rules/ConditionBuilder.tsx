import clsx from 'clsx'
import { FolderPlus, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button, Input, Select } from '../../components/ui'
import type { Condition, ConditionGroup, ConditionOperator } from '../../lib/types'
import { OPERATORS, UNARY, isGroup, newCondition } from './ruleModel'

interface Props {
  group: ConditionGroup
  onChange: (g: ConditionGroup) => void
  onRemove?: () => void
  fields: string[]
  depth?: number
}

/** Presentational: recursive AND/OR condition tree editor (max depth 5, enforced by the API). */
export function ConditionBuilder({ group, onChange, onRemove, fields, depth = 0 }: Props) {
  const update = (i: number, node: Condition | ConditionGroup) => onChange({ ...group, conditions: group.conditions.map((c, j) => (j === i ? node : c)) })
  const remove = (i: number) => onChange({ ...group, conditions: group.conditions.filter((_, j) => j !== i) })
  return (
    <div className={clsx('space-y-2 rounded-md border p-3', depth === 0 ? 'border-slate-200 bg-slate-50' : 'border-brand-100 bg-white')}>
      <div className="flex items-center gap-2 text-sm">
        <span className="text-slate-500">Se cumple</span>
        <Select value={group.operator} onChange={(e) => onChange({ ...group, operator: e.target.value as 'and' | 'or' })} aria-label="Operador lógico">
          <option value="and">TODAS (AND)</option>
          <option value="or">ALGUNA (OR)</option>
        </Select>
        <span className="text-slate-500">de las condiciones:</span>
        {onRemove && (
          <Button size="sm" variant="ghost" className="ml-auto" onClick={onRemove} aria-label="Eliminar grupo">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
      {group.conditions.map((node, i) =>
        isGroup(node) ? (
          <ConditionBuilder key={i} group={node} onChange={(g) => update(i, g)} onRemove={() => remove(i)} fields={fields} depth={depth + 1} />
        ) : (
          <ConditionRow key={i} condition={node} onChange={(c) => update(i, c)} onRemove={() => remove(i)} fields={fields} />
        ),
      )}
      <div className="flex gap-2">
        <Button size="sm" onClick={() => onChange({ ...group, conditions: [...group.conditions, newCondition(fields[0])] })}>
          <Plus className="h-3.5 w-3.5" /> Condición
        </Button>
        {depth < 4 && (
          <Button size="sm" variant="ghost" onClick={() => onChange({ ...group, conditions: [...group.conditions, { operator: group.operator === 'and' ? 'or' : 'and', conditions: [newCondition(fields[0])] }] })}>
            <FolderPlus className="h-3.5 w-3.5" /> Grupo anidado
          </Button>
        )}
      </div>
    </div>
  )
}

function ConditionRow({ condition, onChange, onRemove, fields }: { condition: Condition; onChange: (c: Condition) => void; onRemove: () => void; fields: string[] }) {
  const { t } = useTranslation()
  const op = condition.operator
  const unary = UNARY.includes(op)
  const list = op === 'in_list' || op === 'not_in_list'
  const compareField = condition.value_field !== undefined && condition.value_field !== null
  const textual = !unary && !list && op !== 'between' && op !== 'matches_regex' && op !== 'greater_than' && op !== 'less_than'
  return (
    <div className="flex flex-wrap items-center gap-2 rounded bg-white p-2 shadow-sm ring-1 ring-slate-200">
      <FieldSelect value={condition.field} fields={fields} onChange={(field) => onChange({ ...condition, field })} label="Atributo de la condición" />
      <Select value={op} onChange={(e) => onChange({ ...condition, operator: e.target.value as ConditionOperator })} aria-label="Operador">
        {OPERATORS.map((o) => <option key={o} value={o}>{t(`operators.${o}`)}</option>)}
      </Select>
      {textual && (
        <Select value={compareField ? 'field' : 'value'} onChange={(e) => onChange({ ...condition, value_field: e.target.value === 'field' ? fields[0] : null })} aria-label="Comparar con">
          <option value="value">valor</option>
          <option value="field">otro atributo</option>
        </Select>
      )}
      {!unary && !list && (compareField && textual ? (
        <FieldSelect value={condition.value_field ?? ''} fields={fields} onChange={(value_field) => onChange({ ...condition, value_field })} label="Atributo a comparar" />
      ) : (
        <Input className="w-48" value={condition.value ?? ''} onChange={(e) => onChange({ ...condition, value: e.target.value })} placeholder={op === 'matches_regex' ? 'expresión regular' : 'valor'} aria-label="Valor" />
      ))}
      {op === 'between' && (
        <>
          <span className="text-sm text-slate-500">y</span>
          <Input className="w-32" value={condition.value_to ?? ''} onChange={(e) => onChange({ ...condition, value_to: e.target.value })} placeholder="máximo" aria-label="Valor máximo" />
        </>
      )}
      {list && (
        <Input className="w-72" value={(condition.values ?? []).join(', ')} onChange={(e) => onChange({ ...condition, values: e.target.value.split(',').map((v) => v.trim()) })} placeholder="valor1, valor2, valor3" aria-label="Lista de valores" />
      )}
      {!unary && op !== 'greater_than' && op !== 'less_than' && op !== 'between' && (
        <label className="flex items-center gap-1 text-xs text-slate-500">
          <input type="checkbox" checked={!!condition.case_sensitive} onChange={(e) => onChange({ ...condition, case_sensitive: e.target.checked })} />
          Distinguir mayúsculas
        </label>
      )}
      <Button size="sm" variant="ghost" className="ml-auto" onClick={onRemove} aria-label="Eliminar condición">
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </div>
  )
}

export function FieldSelect({ value, fields, onChange, label, allowCustom }: { value: string; fields: string[]; onChange: (v: string) => void; label: string; allowCustom?: boolean }) {
  const known = fields.includes(value)
  return (
    <span className="inline-flex gap-1">
      <Select value={known ? value : allowCustom ? '__custom' : value} onChange={(e) => onChange(e.target.value === '__custom' ? '' : e.target.value)} aria-label={label}>
        {!known && !allowCustom && value && <option value={value}>{value}</option>}
        {fields.map((f) => <option key={f} value={f}>{f}</option>)}
        {allowCustom && <option value="__custom">Nuevo atributo…</option>}
      </Select>
      {allowCustom && !known && (
        <Input className="w-44" value={value} onChange={(e) => onChange(e.target.value)} placeholder="custom_label_0" aria-label="Nombre del nuevo atributo" />
      )}
    </span>
  )
}
