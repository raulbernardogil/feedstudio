import clsx from 'clsx'
import {
  Activity, BookOpenCheck, Database, Eye, FileCode2, LayoutDashboard, Rss, Settings, ShieldCheck, Wand2,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useWorkspace } from '../lib/workspace'
import { Select } from './ui'

const NAV = [
  { to: '/', key: 'dashboard', icon: LayoutDashboard },
  { to: '/sources', key: 'sources', icon: FileCode2 },
  { to: '/catalog', key: 'catalog', icon: Database },
  { to: '/rules', key: 'rules', icon: Wand2 },
  { to: '/preview', key: 'preview', icon: Eye },
  { to: '/validation', key: 'validation', icon: ShieldCheck },
  { to: '/channels', key: 'channels', icon: Rss },
  { to: '/jobs', key: 'jobs', icon: Activity },
  { to: '/settings', key: 'settings', icon: Settings },
] as const

export function Layout() {
  const { t } = useTranslation()
  const ws = useWorkspace()
  return (
    <div className="flex h-full">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="flex items-center gap-2 border-b border-slate-100 px-5 py-4">
          <BookOpenCheck className="h-6 w-6 text-brand-600" aria-hidden />
          <div>
            <p className="font-semibold text-slate-900">{t('app.name')}</p>
            <p className="text-xs text-slate-500">{t('app.tagline')}</p>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 p-3" aria-label="Principal">
          {NAV.map(({ to, key, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx('flex items-center gap-2.5 rounded-md px-3 py-2 text-sm', isActive ? 'bg-brand-50 font-medium text-brand-700' : 'text-slate-600 hover:bg-slate-100')
              }
            >
              <Icon className="h-4 w-4" aria-hidden />
              {t(`nav.${key}`)}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-6 py-2.5">
          <nav className="flex gap-1 overflow-x-auto md:hidden" aria-label="Principal móvil">
            {NAV.map(({ to, key }) => (
              <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => clsx('whitespace-nowrap rounded px-2 py-1 text-xs', isActive ? 'bg-brand-50 text-brand-700' : 'text-slate-600')}>
                {t(`nav.${key}`)}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <label className="flex items-center gap-2 text-slate-500">
              {t('common.selectSource')}
              <Select value={ws.sourceId ?? ''} onChange={(e) => ws.setSourceId(e.target.value ? Number(e.target.value) : null)} disabled={!ws.sources.length}>
                {!ws.sources.length && <option value="">—</option>}
                {ws.sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex items-center gap-2 text-slate-500">
              {t('common.selectChannel')}
              <Select value={ws.channelId ?? ''} onChange={(e) => ws.setChannelId(e.target.value ? Number(e.target.value) : null)} disabled={!ws.channels.length}>
                {!ws.channels.length && <option value="">—</option>}
                {ws.channels.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </label>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto px-6 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
