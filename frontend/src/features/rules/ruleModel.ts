import { z } from 'zod'
import type { Action, ActionType, Condition, ConditionGroup, ConditionOperator, RuleDefinition } from '../../lib/types'

export const UNARY: ConditionOperator[] = ['is_empty', 'not_empty', 'exists', 'not_exists']
export const OPERATORS: ConditionOperator[] = [
  'contains', 'not_contains', 'equals', 'not_equals', 'starts_with', 'ends_with', 'is_empty', 'not_empty',
  'exists', 'not_exists', 'greater_than', 'less_than', 'between', 'matches_regex', 'in_list', 'not_in_list',
]
export const ACTION_TYPES: ActionType[] = [
  'set_value', 'set_if_empty', 'prepend', 'append', 'replace', 'remove_text', 'uppercase', 'lowercase', 'capitalize',
  'collapse_whitespace', 'strip_html', 'truncate', 'copy_from', 'map_values', 'normalize_price', 'regex_extract',
  'exclude', 'add_to_segment',
]
export const PRODUCT_LEVEL: ActionType[] = ['exclude', 'add_to_segment']
export const TEMPLATE_ACTIONS: ActionType[] = ['set_value', 'set_if_empty', 'prepend', 'append']

export function isGroup(node: Condition | ConditionGroup): node is ConditionGroup {
  return 'conditions' in node
}

export function newCondition(field = 'title'): Condition {
  return { field, operator: 'contains', value: '', case_sensitive: false }
}

export function newAction(type: ActionType): Action {
  switch (type) {
    case 'set_value':
    case 'set_if_empty':
    case 'prepend':
    case 'append':
      return { type, template: '' }
    case 'replace':
      return { type, find: '', replace_with: '', use_regex: false, case_sensitive: false }
    case 'remove_text':
      return { type, find: '', use_regex: false, case_sensitive: false }
    case 'capitalize':
      return { type, mode: 'sentence' }
    case 'truncate':
      return { type, max_length: 150, strategy: 'word', ellipsis: '' }
    case 'copy_from':
      return { type, field: '' }
    case 'map_values':
      return { type, mappings: [{ from: '', to: '' }], case_sensitive: false }
    case 'normalize_price':
      return { type, decimals: 2, default_currency: null }
    case 'regex_extract':
      return { type, pattern: '', group: 0, case_sensitive: false, keep_if_no_match: true }
    case 'add_to_segment':
      return { type, segment: '' }
    default:
      return { type } as Action
  }
}

export function emptyRule(): RuleDefinition {
  return {
    name: '',
    description: null,
    enabled: true,
    priority: 100,
    target: 'title',
    condition: null,
    actions: [newAction('prepend')],
    evaluate_on: 'current',
    on_missing_variable: 'skip_rule',
    fallback_value: '',
  }
}

/** Client-side checks for fast feedback. The backend schema remains authoritative. */
const definitionSchema = z.object({
  name: z.string().trim().min(1, 'La regla necesita un nombre'),
  priority: z.number().int().min(0).max(100000),
  actions: z.array(z.any()).min(1, 'Añade al menos una acción'),
}).passthrough()

export function validateDefinition(d: RuleDefinition): string[] {
  const errors: string[] = []
  const parsed = definitionSchema.safeParse(d)
  if (!parsed.success) errors.push(...parsed.error.issues.map((i) => i.message))
  const needsTarget = d.actions.some((a) => !PRODUCT_LEVEL.includes(a.type))
  if (needsTarget && !d.target) errors.push('Las acciones de valor requieren un atributo destino')
  d.actions.forEach((a, i) => {
    if ('template' in a && TEMPLATE_ACTIONS.includes(a.type) && a.type !== 'set_value' && !a.template) errors.push(`Acción ${i + 1}: la plantilla está vacía`)
    if ((a.type === 'replace' || a.type === 'remove_text') && !a.find) errors.push(`Acción ${i + 1}: indica el texto a buscar`)
    if (a.type === 'copy_from' && !a.field) errors.push(`Acción ${i + 1}: indica el atributo origen`)
    if (a.type === 'add_to_segment' && !a.segment) errors.push(`Acción ${i + 1}: indica el segmento`)
    if (a.type === 'regex_extract' && !a.pattern) errors.push(`Acción ${i + 1}: indica el patrón`)
  })
  return errors
}

/** Remove UI-only empties before sending to the API. */
export function cleanDefinition(d: RuleDefinition): RuleDefinition {
  const cleanNode = (n: Condition | ConditionGroup): Condition | ConditionGroup => {
    if (isGroup(n)) return { operator: n.operator, conditions: n.conditions.map(cleanNode) }
    const out: Condition = { field: n.field, operator: n.operator, case_sensitive: !!n.case_sensitive }
    if (UNARY.includes(n.operator)) return out
    if (n.operator === 'in_list' || n.operator === 'not_in_list') return { ...out, values: (n.values ?? []).filter(Boolean) }
    if (n.value_field) return { ...out, value_field: n.value_field }
    return { ...out, value: n.value ?? '', ...(n.operator === 'between' ? { value_to: n.value_to ?? '' } : {}) }
  }
  const actions = d.actions.map((a) => (a.type === 'map_values' ? { ...a, mappings: a.mappings.filter((m) => m.from) } : a))
  const productOnly = actions.every((a) => PRODUCT_LEVEL.includes(a.type))
  return {
    ...d,
    name: d.name.trim(),
    target: productOnly ? null : d.target,
    condition: d.condition && d.condition.conditions.length ? (cleanNode(d.condition) as ConditionGroup) : null,
    actions,
  }
}
