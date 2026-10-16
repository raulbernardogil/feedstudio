import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { ConditionBuilder } from '../features/rules/ConditionBuilder'
import { cleanDefinition, emptyRule, validateDefinition } from '../features/rules/ruleModel'
import { diffWords } from '../lib/diff'
import type { ConditionGroup } from '../lib/types'

describe('diffWords', () => {
  it('marks inserted words', () => {
    expect(diffWords('Zapatillas Runner', 'Velox Zapatillas Runner')).toEqual([
      { type: 'ins', text: 'Velox ' },
      { type: 'same', text: 'Zapatillas Runner' },
    ])
  })
  it('handles identical strings', () => {
    expect(diffWords('a b', 'a b')).toEqual([{ type: 'same', text: 'a b' }])
  })
})

describe('rule model', () => {
  it('requires a target for value actions', () => {
    const d = { ...emptyRule(), name: 'x', target: null }
    expect(validateDefinition(d)).toContain('Las acciones de valor requieren un atributo destino')
  })

  it('cleans conditions and drops target for product-level actions', () => {
    const d = cleanDefinition({
      ...emptyRule(),
      name: ' Excluir ',
      condition: { operator: 'and', conditions: [{ field: 'availability', operator: 'is_empty', value: 'ignored' }] },
      actions: [{ type: 'exclude' }],
    })
    expect(d.name).toBe('Excluir')
    expect(d.target).toBeNull()
    expect(d.condition?.conditions[0]).toEqual({ field: 'availability', operator: 'is_empty', case_sensitive: false })
  })

  it('removes an empty condition group', () => {
    expect(cleanDefinition({ ...emptyRule(), name: 'x', condition: { operator: 'and', conditions: [] } }).condition).toBeNull()
  })
})

function Harness() {
  const [group, setGroup] = useState<ConditionGroup>({ operator: 'and', conditions: [{ field: 'title', operator: 'contains', value: '' }] })
  return (
    <>
      <ConditionBuilder group={group} onChange={setGroup} fields={['title', 'brand']} />
      <pre data-testid="state">{JSON.stringify(group)}</pre>
    </>
  )
}

describe('ConditionBuilder', () => {
  it('adds nested groups and conditions', () => {
    render(<Harness />)
    fireEvent.click(screen.getByText('Grupo anidado'))
    const state = JSON.parse(screen.getByTestId('state').textContent ?? '{}') as ConditionGroup
    expect(state.conditions).toHaveLength(2)
    expect(state.conditions[1]).toMatchObject({ operator: 'or' })
  })
})
