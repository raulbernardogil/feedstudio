import { useRef } from 'react'
import { Input } from '../../components/ui'

/** Template text box with clickable variables taken from the detected attributes. */
export function TemplateInput({ value, onChange, fields, placeholder }: { value: string; onChange: (v: string) => void; fields: string[]; placeholder?: string }) {
  const ref = useRef<HTMLInputElement>(null)
  const insert = (token: string) => {
    const el = ref.current
    const start = el?.selectionStart ?? value.length
    const end = el?.selectionEnd ?? value.length
    const next = value.slice(0, start) + token + value.slice(end)
    onChange(next)
    requestAnimationFrame(() => {
      el?.focus()
      el?.setSelectionRange(start + token.length, start + token.length)
    })
  }
  const common = ['brand', 'title', 'color', 'size', 'material', 'product_type', 'gender'].filter((f) => fields.includes(f))
  const others = fields.filter((f) => !common.includes(f))
  return (
    <div className="space-y-1.5">
      <Input ref={ref} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder ?? '{brand} {title}[ - {color}]'} className="font-mono" aria-label="Plantilla" />
      <div className="flex flex-wrap items-center gap-1">
        {common.map((f) => (
          <button key={f} type="button" onClick={() => insert(`{${f}}`)} className="rounded bg-brand-50 px-1.5 py-0.5 font-mono text-xs text-brand-700 hover:bg-brand-100">{`{${f}}`}</button>
        ))}
        {others.length > 0 && (
          <select className="rounded border border-slate-200 px-1 py-0.5 text-xs" value="" onChange={(e) => e.target.value && insert(`{${e.target.value}}`)} aria-label="Insertar otra variable">
            <option value="">+ variable…</option>
            {others.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        )}
        <button type="button" onClick={() => insert('[ - {color}]')} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-600 hover:bg-slate-200" title="Sección opcional: se omite entera si falta alguna variable">
          [opcional]
        </button>
      </div>
    </div>
  )
}
