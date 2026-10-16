import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button, Input, Select, Textarea } from '../../components/ui'
import type { Action, ActionType } from '../../lib/types'
import { FieldSelect } from './ConditionBuilder'
import { ACTION_TYPES, newAction } from './ruleModel'
import { TemplateInput } from './TemplateInput'

/** Presentational: ordered list of actions; each receives the output of the previous one. */
export function ActionList({ actions, onChange, fields }: { actions: Action[]; onChange: (a: Action[]) => void; fields: string[] }) {
  const { t } = useTranslation()
  const update = (i: number, a: Action) => onChange(actions.map((x, j) => (j === i ? a : x)))
  const move = (i: number, d: number) => {
    const next = [...actions]
    const [item] = next.splice(i, 1)
    next.splice(i + d, 0, item)
    onChange(next)
  }
  return (
    <div className="space-y-2">
      {actions.map((action, i) => (
        <div key={i} className="rounded-md border border-slate-200 bg-white p-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold">{i + 1}</span>
            <Select value={action.type} onChange={(e) => update(i, newAction(e.target.value as ActionType))} aria-label={`Tipo de acción ${i + 1}`}>
              {ACTION_TYPES.map((type) => <option key={type} value={type}>{t(`actions.${type}`)}</option>)}
            </Select>
            <div className="ml-auto flex">
              <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Subir acción"><ArrowUp className="h-3.5 w-3.5" /></Button>
              <Button size="sm" variant="ghost" disabled={i === actions.length - 1} onClick={() => move(i, 1)} aria-label="Bajar acción"><ArrowDown className="h-3.5 w-3.5" /></Button>
              <Button size="sm" variant="ghost" disabled={actions.length === 1} onClick={() => onChange(actions.filter((_, j) => j !== i))} aria-label="Eliminar acción"><Trash2 className="h-3.5 w-3.5" /></Button>
            </div>
          </div>
          <ActionFields action={action} onChange={(a) => update(i, a)} fields={fields} />
        </div>
      ))}
      <Button size="sm" onClick={() => onChange([...actions, newAction('set_value')])}>
        <Plus className="h-3.5 w-3.5" /> Añadir acción
      </Button>
    </div>
  )
}

function Check({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-slate-600">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /> {label}
    </label>
  )
}

function ActionFields({ action: a, onChange, fields }: { action: Action; onChange: (a: Action) => void; fields: string[] }) {
  switch (a.type) {
    case 'set_value':
    case 'set_if_empty':
    case 'prepend':
    case 'append':
      return (
        <div>
          <TemplateInput value={a.template} onChange={(template) => onChange({ ...a, template })} fields={fields}
            placeholder={a.type === 'prepend' ? '{brand} ' : a.type === 'append' ? '[ - {color}][ - Talla {size}]' : 'Texto fijo o plantilla con {atributos}'} />
          <p className="mt-1 text-xs text-slate-500">
            {a.type === 'set_value' && 'Sustituye el valor. Un resultado vacío elimina el atributo.'}
            {a.type === 'set_if_empty' && 'Solo se aplica si el atributo está vacío o no existe.'}
            {a.type === 'prepend' && 'Se antepone al valor actual (incluye el espacio final si lo necesitas).'}
            {a.type === 'append' && 'Se añade al final del valor actual.'}
          </p>
        </div>
      )
    case 'replace':
      return (
        <div className="flex flex-wrap items-center gap-2">
          <Input className="w-56" value={a.find} onChange={(e) => onChange({ ...a, find: e.target.value })} placeholder="buscar" aria-label="Texto a buscar" />
          <span className="text-sm text-slate-500">→</span>
          <Input className="w-56" value={a.replace_with} onChange={(e) => onChange({ ...a, replace_with: e.target.value })} placeholder="reemplazar por" aria-label="Reemplazo" />
          <Check checked={!!a.use_regex} onChange={(use_regex) => onChange({ ...a, use_regex })} label="Regex (\\1 = grupo)" />
          <Check checked={!!a.case_sensitive} onChange={(case_sensitive) => onChange({ ...a, case_sensitive })} label="Distinguir mayúsculas" />
        </div>
      )
    case 'remove_text':
      return (
        <div className="flex flex-wrap items-center gap-2">
          <Input className="w-72" value={a.find} onChange={(e) => onChange({ ...a, find: e.target.value })} placeholder="texto a eliminar" aria-label="Texto a eliminar" />
          <Check checked={!!a.use_regex} onChange={(use_regex) => onChange({ ...a, use_regex })} label="Regex" />
          <Check checked={!!a.case_sensitive} onChange={(case_sensitive) => onChange({ ...a, case_sensitive })} label="Distinguir mayúsculas" />
        </div>
      )
    case 'capitalize':
      return (
        <Select value={a.mode} onChange={(e) => onChange({ ...a, mode: e.target.value as 'sentence' | 'words' })} aria-label="Modo de capitalización">
          <option value="sentence">Primera letra de la frase</option>
          <option value="words">Cada palabra</option>
        </Select>
      )
    case 'truncate':
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          Máximo
          <Input type="number" min={1} className="w-24" value={a.max_length} onChange={(e) => onChange({ ...a, max_length: Number(e.target.value) })} aria-label="Longitud máxima" />
          caracteres, cortando por
          <Select value={a.strategy} onChange={(e) => onChange({ ...a, strategy: e.target.value as 'word' | 'char' })} aria-label="Estrategia de recorte">
            <option value="word">palabra completa</option>
            <option value="char">carácter</option>
          </Select>
          sufijo
          <Input className="w-16" value={a.ellipsis ?? ''} onChange={(e) => onChange({ ...a, ellipsis: e.target.value })} placeholder="…" aria-label="Sufijo de recorte" />
        </div>
      )
    case 'copy_from':
      return <FieldSelect value={a.field} fields={fields} onChange={(field) => onChange({ ...a, field })} label="Atributo origen" />
    case 'map_values':
      return (
        <div className="space-y-1">
          <Textarea rows={Math.min(10, a.mappings.length + 1)} value={a.mappings.map((m) => `${m.from} => ${m.to}`).join('\n')}
            onChange={(e) => onChange({ ...a, mappings: e.target.value.split('\n').map((line) => { const [from, ...rest] = line.split('=>'); return { from: (from ?? '').trim(), to: rest.join('=>').trim() } }) })}
            aria-label="Diccionario de valores" placeholder={'black => Negro\nnavy => Azul marino'} />
          <p className="text-xs text-slate-500">Una línea por valor: <code>origen =&gt; destino</code>. Los valores que no aparecen se mantienen.</p>
          <Check checked={!!a.case_sensitive} onChange={(case_sensitive) => onChange({ ...a, case_sensitive })} label="Distinguir mayúsculas" />
        </div>
      )
    case 'normalize_price':
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          Decimales
          <Input type="number" min={0} max={4} className="w-20" value={a.decimals} onChange={(e) => onChange({ ...a, decimals: Number(e.target.value) })} aria-label="Decimales" />
          Moneda por defecto
          <Input className="w-20 uppercase" maxLength={3} value={a.default_currency ?? ''} onChange={(e) => onChange({ ...a, default_currency: e.target.value.toUpperCase() || null })} placeholder="CLP" aria-label="Moneda por defecto" />
          <span className="text-xs text-slate-500">949.990,00 CLP → 949990.00 CLP</span>
        </div>
      )
    case 'regex_extract':
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Input className="w-64 font-mono" value={a.pattern} onChange={(e) => onChange({ ...a, pattern: e.target.value })} placeholder="(\d+) cm" aria-label="Patrón" />
          grupo
          <Input type="number" min={0} className="w-16" value={a.group} onChange={(e) => onChange({ ...a, group: Number(e.target.value) })} aria-label="Grupo" />
          <Check checked={a.keep_if_no_match ?? true} onChange={(keep_if_no_match) => onChange({ ...a, keep_if_no_match })} label="Conservar valor si no coincide" />
        </div>
      )
    case 'add_to_segment':
      return <Input className="w-64" value={a.segment} onChange={(e) => onChange({ ...a, segment: e.target.value })} placeholder="verano-2026" aria-label="Segmento" />
    case 'exclude':
      return <p className="text-xs text-slate-500">El producto no se exportará en este canal (o en ninguno si la regla es global). Se conserva en el catálogo interno.</p>
    default:
      return <p className="text-xs text-slate-500">Sin opciones adicionales.</p>
  }
}
