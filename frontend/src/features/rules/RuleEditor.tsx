import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Eye, Save } from 'lucide-react'
import { useState } from 'react'
import { Button, Card, ErrorBox, Field, Input, Select, Spinner, Switch } from '../../components/ui'
import { api } from '../../lib/api'
import type { Channel, ConditionGroup, PreviewResult, Rule, RuleDefinition } from '../../lib/types'
import { ActionList } from './ActionEditor'
import { ConditionBuilder, FieldSelect } from './ConditionBuilder'
import { RulePreview } from './RulePreview'
import { PRODUCT_LEVEL, cleanDefinition, newCondition, validateDefinition } from './ruleModel'

interface Props {
  sourceId: number
  channels: Channel[]
  initial: { rule: Rule | null; definition: RuleDefinition; channelId: number | null }
  fields: string[]
  onDone: () => void
}

/** Container: edits a rule draft, previews it on the backend and saves it. */
export function RuleEditor({ sourceId, channels, initial, fields, onDone }: Props) {
  const qc = useQueryClient()
  const [d, setD] = useState<RuleDefinition>(initial.definition)
  const [channelId, setChannelId] = useState<number | null>(initial.channelId)
  const [localErrors, setLocalErrors] = useState<string[]>([])
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const set = <K extends keyof RuleDefinition>(key: K, value: RuleDefinition[K]) => setD((prev) => ({ ...prev, [key]: value }))
  const productOnly = d.actions.every((a) => PRODUCT_LEVEL.includes(a.type))

  const previewMutation = useMutation({
    mutationFn: (page: number) => api.previewRule({ source_id: sourceId, channel_id: channelId, rule_id: initial.rule?.id ?? null, definition: cleanDefinition({ ...d, name: d.name || 'Borrador' }), page, page_size: 10 }),
    onSuccess: setPreview,
  })
  const save = useMutation({
    mutationFn: () => {
      const definition = cleanDefinition(d)
      return initial.rule ? api.updateRule(initial.rule.id, { channel_id: channelId, definition }) : api.createRule({ source_id: sourceId, channel_id: channelId, definition })
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['rules'] })
      void qc.invalidateQueries({ queryKey: ['dashboard'] })
      onDone()
    },
  })

  const runPreview = (page = 1) => {
    const errors = validateDefinition({ ...d, name: d.name || 'Borrador' })
    setLocalErrors(errors)
    if (!errors.length) previewMutation.mutate(page)
  }
  const submit = () => {
    const errors = validateDefinition(d)
    setLocalErrors(errors)
    if (!errors.length) save.mutate()
  }
  const condition: ConditionGroup | null = d.condition

  return (
    <div className="space-y-4">
      <Card title={initial.rule ? `Editar regla · versión ${initial.rule.version}` : 'Nueva regla'}>
        <div className="grid gap-4 md:grid-cols-4">
          <Field label="Nombre" className="md:col-span-2">
            <Input value={d.name} onChange={(e) => set('name', e.target.value)} placeholder="Añadir marca al título" />
          </Field>
          <Field label="Prioridad" hint="Menor número = se ejecuta antes">
            <Input type="number" min={0} value={d.priority} onChange={(e) => set('priority', Number(e.target.value))} />
          </Field>
          <Field label="Ámbito">
            <Select className="w-full" value={channelId ?? ''} onChange={(e) => setChannelId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Global (todos los canales)</option>
              {channels.map((c) => <option key={c.id} value={c.id}>Solo canal: {c.name}</option>)}
            </Select>
          </Field>
          <Field label="Descripción (opcional)" className="md:col-span-3">
            <Input value={d.description ?? ''} onChange={(e) => set('description', e.target.value || null)} />
          </Field>
          <div className="flex items-end pb-1">
            <Switch checked={d.enabled} onCheckedChange={(v) => set('enabled', v)} label={d.enabled ? 'Activada' : 'Desactivada'} />
          </div>
        </div>
      </Card>

      <Card title="1. Condiciones (SI…)">
        {condition ? (
          <>
            <ConditionBuilder group={condition} onChange={(g) => set('condition', g)} fields={fields} />
            <div className="mt-2 flex flex-wrap items-center gap-4">
              <Button size="sm" variant="ghost" onClick={() => set('condition', null)}>Aplicar a todos los productos</Button>
              <label className="flex items-center gap-2 text-sm">
                Evaluar sobre
                <Select value={d.evaluate_on} onChange={(e) => set('evaluate_on', e.target.value as 'current' | 'original')}>
                  <option value="current">el valor transformado hasta esta regla</option>
                  <option value="original">el valor original importado</option>
                </Select>
              </label>
            </div>
          </>
        ) : (
          <div className="flex items-center gap-3 text-sm text-slate-600">
            La regla se aplica a todos los productos.
            <Button size="sm" onClick={() => set('condition', { operator: 'and', conditions: [newCondition(fields.includes('title') ? 'title' : fields[0])] })}>Añadir condiciones</Button>
          </div>
        )}
      </Card>

      <Card title="2. Acciones (ENTONCES…)">
        {!productOnly && (
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            Atributo destino
            <FieldSelect value={d.target ?? ''} fields={fields} onChange={(v) => set('target', v)} label="Atributo destino" allowCustom />
            <span className="text-xs text-slate-500">Un atributo nuevo crea un campo calculado (p. ej. custom_label_0).</span>
          </div>
        )}
        <ActionList actions={d.actions} onChange={(a) => set('actions', a)} fields={fields} />
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          Si falta una variable fuera de [secciones opcionales]:
          <Select value={d.on_missing_variable} onChange={(e) => set('on_missing_variable', e.target.value as RuleDefinition['on_missing_variable'])}>
            <option value="skip_rule">no aplicar la regla a ese producto</option>
            <option value="empty">usar cadena vacía</option>
            <option value="fallback">usar valor alternativo</option>
            <option value="error">no aplicar y registrar incidencia</option>
          </Select>
          {d.on_missing_variable === 'fallback' && <Input className="w-48" value={d.fallback_value} onChange={(e) => set('fallback_value', e.target.value)} placeholder="valor alternativo" />}
        </div>
      </Card>

      {localErrors.length > 0 && (
        <ul className="list-disc rounded-md border border-rose-200 bg-rose-50 py-2 pl-8 text-sm text-rose-800">
          {localErrors.map((e) => <li key={e}>{e}</li>)}
        </ul>
      )}
      <ErrorBox error={save.error ?? previewMutation.error} />

      <div className="flex flex-wrap justify-end gap-2">
        <Button onClick={onDone}>Cancelar</Button>
        <Button onClick={() => runPreview(1)} loading={previewMutation.isPending}><Eye className="h-4 w-4" /> Previsualizar</Button>
        <Button variant="primary" onClick={submit} loading={save.isPending}><Save className="h-4 w-4" /> Guardar regla</Button>
      </div>

      {(preview || previewMutation.isPending) && (
        <Card title="Previsualización (sin modificar el feed publicado)">
          {previewMutation.isPending && !preview ? <Spinner label="Aplicando la regla al catálogo…" /> : preview && <RulePreview result={preview} onPage={(p) => runPreview(p)} />}
        </Card>
      )}
    </div>
  )
}
