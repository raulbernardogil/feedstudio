import type { Attributes, Value } from './types'

export function displayValue(values: Value[] | undefined): string {
  if (!values || values.length === 0) return ''
  return values
    .map((v) => (typeof v === 'string' ? v : Object.entries(v).map(([k, vs]) => `${k}=${displayValue(vs)}`).join('; ')))
    .join(', ')
}

export function text(attrs: Attributes | undefined, key: string): string {
  return displayValue(attrs?.[key])
}

const dateFmt = new Intl.DateTimeFormat('es', { dateStyle: 'short', timeStyle: 'short' })
const numFmt = new Intl.NumberFormat('es')

export function formatDate(iso: string | null | undefined): string {
  return iso ? dateFmt.format(new Date(iso)) : '—'
}

export function formatNumber(n: number | null | undefined): string {
  return n === null || n === undefined ? '—' : numFmt.format(n)
}

export function formatBytes(n: number | null | undefined): string {
  if (!n) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export function truncate(s: string, max = 80): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s
}
