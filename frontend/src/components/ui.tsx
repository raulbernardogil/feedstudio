import * as DialogPrimitive from '@radix-ui/react-dialog'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import clsx from 'clsx'
import { AlertTriangle, ChevronLeft, ChevronRight, Loader2, X } from 'lucide-react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { forwardRef } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../lib/api'
import type { IssueLevel } from '../lib/types'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean; size?: 'sm' | 'md' }>(
  function Button({ variant = 'secondary', loading, size = 'md', className, children, disabled, ...props }, ref) {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={clsx(
          'inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-50',
          size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-2 text-sm',
          variant === 'primary' && 'bg-brand-600 text-white hover:bg-brand-700',
          variant === 'secondary' && 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
          variant === 'ghost' && 'text-slate-600 hover:bg-slate-100',
          variant === 'danger' && 'bg-rose-600 text-white hover:bg-rose-700',
          className,
        )}
        {...props}
      >
        {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
        {children}
      </button>
    )
  },
)

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  return (
    <input
      ref={ref}
      className={clsx(
        'rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm shadow-sm placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500',
        // Full width unless the caller sets an explicit width.
        !/\bw-/.test(className ?? '') && 'w-full',
        className,
      )}
      {...props}
    />
  )
})

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...props }, ref) {
  return (
    <textarea
      ref={ref}
      className={clsx('w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 font-mono text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500', className)}
      {...props}
    />
  )
})

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...props }, ref) {
  return (
    <select
      ref={ref}
      className={clsx('rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500', className)}
      {...props}
    >
      {children}
    </select>
  )
})

export function Field({ label, hint, error, children, className }: { label: string; hint?: ReactNode; error?: string; children: ReactNode; className?: string }) {
  return (
    <label className={clsx('block space-y-1', className)}>
      <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</span>
      {children}
      {hint && !error && <span className="block text-xs text-slate-500">{hint}</span>}
      {error && <span className="block text-xs text-rose-600">{error}</span>}
    </label>
  )
}

export function Switch({ checked, onCheckedChange, label }: { checked: boolean; onCheckedChange: (v: boolean) => void; label: string }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
      <SwitchPrimitive.Root
        checked={checked}
        onCheckedChange={onCheckedChange}
        className="relative h-5 w-9 rounded-full bg-slate-300 transition data-[state=checked]:bg-brand-600"
      >
        <SwitchPrimitive.Thumb className="block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow transition data-[state=checked]:translate-x-[18px]" />
      </SwitchPrimitive.Root>
      {label}
    </label>
  )
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={clsx('rounded-lg border border-slate-200 bg-white shadow-sm', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-slate-500">{description}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  )
}

const levelStyles: Record<string, string> = {
  valid: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  recommendation: 'bg-sky-50 text-sky-700 ring-sky-200',
  warning: 'bg-amber-50 text-amber-700 ring-amber-200',
  error: 'bg-rose-50 text-rose-700 ring-rose-200',
  excluded: 'bg-slate-100 text-slate-600 ring-slate-200',
  succeeded: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  failed: 'bg-rose-50 text-rose-700 ring-rose-200',
  running: 'bg-brand-50 text-brand-700 ring-brand-100',
  queued: 'bg-slate-100 text-slate-600 ring-slate-200',
  ready: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  building: 'bg-brand-50 text-brand-700 ring-brand-100',
  processing: 'bg-brand-50 text-brand-700 ring-brand-100',
  pending: 'bg-slate-100 text-slate-600 ring-slate-200',
  archived: 'bg-slate-100 text-slate-500 ring-slate-200',
  info: 'bg-slate-100 text-slate-700 ring-slate-200',
}

export function Badge({ tone = 'info', children }: { tone?: string; children: ReactNode }) {
  return <span className={clsx('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset', levelStyles[tone] ?? levelStyles.info)}>{children}</span>
}

export function LevelBadge({ level }: { level: IssueLevel | string }) {
  const { t } = useTranslation()
  return <Badge tone={level}>{t(`levels.${level}`, { defaultValue: level })}</Badge>
}

export function Spinner({ label }: { label?: string }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-slate-500" role="status">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {label ?? t('common.loading')}
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation()
  if (!error) return null
  const message = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error)
  const details = error instanceof ApiError && Array.isArray(error.details) ? (error.details as { loc: string[]; msg: string }[]) : null
  return (
    <div className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800" role="alert">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="flex-1">
        <p>{message}</p>
        {details && (
          <ul className="mt-1 list-disc pl-4 text-xs">
            {details.slice(0, 6).map((d, i) => (
              <li key={i}>
                <code>{d.loc.filter((l) => l !== 'body').join('.')}</code>: {d.msg}
              </li>
            ))}
          </ul>
        )}
      </div>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          {t('common.retry')}
        </Button>
      )}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
      <p className="font-medium text-slate-700">{title}</p>
      {children && <div className="mt-2 text-sm text-slate-500">{children}</div>}
    </div>
  )
}

export function Stat({ label, value, tone, hint }: { label: string; value: ReactNode; tone?: 'ok' | 'warn' | 'bad'; hint?: ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={clsx('mt-1 text-2xl font-semibold', tone === 'ok' && 'text-emerald-600', tone === 'warn' && 'text-amber-600', tone === 'bad' && 'text-rose-600', !tone && 'text-slate-900')}>
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  )
}

export const PAGE_SIZES = [10, 25, 50, 100] as const

export function Pagination({ page, pageSize, total, onPage, onPageSize }: { page: number; pageSize: number; total: number; onPage: (p: number) => void; onPageSize?: (s: number) => void }) {
  const { t } = useTranslation()
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-3 py-2 text-sm text-slate-600">
      <span>{t('common.results', { count: total })}</span>
      <div className="flex items-center gap-3">
        {onPageSize && <label className="flex items-center gap-2">
          {t('common.rowsPerPage')}
          <Select value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))} aria-label={t('common.rowsPerPage')}>
            {PAGE_SIZES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </label>}
        <span>{t('common.page', { page, pages })}</span>
        <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label={t('common.previous')}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label={t('common.next')}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

export function Dialog({ open, onOpenChange, title, description, children, wide }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: string; children: ReactNode; wide?: boolean }) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-slate-900/40" />
        <DialogPrimitive.Content
          className={clsx('fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[95vw] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg bg-white p-5 shadow-xl', wide ? 'max-w-5xl' : 'max-w-lg')}
        >
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <DialogPrimitive.Title className="text-base font-semibold text-slate-900">{title}</DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="mt-1 text-sm text-slate-500">{description}</DialogPrimitive.Description>
              ) : (
                <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
              )}
            </div>
            <DialogPrimitive.Close className="rounded p-1 text-slate-500 hover:bg-slate-100" aria-label="Cerrar">
              <X className="h-4 w-4" />
            </DialogPrimitive.Close>
          </div>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export function Drawer({ open, onOpenChange, title, children }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; children: ReactNode }) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-slate-900/30" />
        <DialogPrimitive.Content className="fixed right-0 top-0 z-50 h-full w-full max-w-2xl overflow-y-auto bg-white p-5 shadow-xl">
          <div className="mb-4 flex items-center justify-between">
            <DialogPrimitive.Title className="text-base font-semibold text-slate-900">{title}</DialogPrimitive.Title>
            <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
            <DialogPrimitive.Close className="rounded p-1 text-slate-500 hover:bg-slate-100" aria-label="Cerrar">
              <X className="h-4 w-4" />
            </DialogPrimitive.Close>
          </div>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export function ProgressBar({ value }: { value: number | null }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value === null ? undefined : Math.round(value * 100)}>
      <div className={clsx('h-full rounded-full bg-brand-500 transition-all', value === null && 'w-1/3 animate-pulse')} style={value === null ? undefined : { width: `${Math.max(3, value * 100)}%` }} />
    </div>
  )
}
