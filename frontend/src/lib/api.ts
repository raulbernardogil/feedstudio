import type {
  Channel, FeedItemRow, FeedVersion, IssueSummary, Job, Page, PreviewResult, Product, Rule,
  RuleDefinition, SchemaField, Snapshot, Source,
} from './types'

export class ApiError extends Error {
  status: number
  code: string
  details: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

const TOKEN_KEY = 'feedstudio.apiToken'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

type Query = Record<string, string | number | boolean | null | undefined>

function qs(params?: Query): string {
  if (!params) return ''
  const search = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') search.set(k, String(v))
  }
  const s = search.toString()
  return s ? `?${s}` : ''
}

async function request<T>(method: string, path: string, body?: unknown, params?: Query): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`${path}${qs(params)}`, { method, headers, body: payload })
  if (res.status === 204) return undefined as T
  const text = await res.text()
  const data = text ? JSON.parse(text) : undefined
  if (!res.ok) {
    const err = data?.error
    throw new ApiError(res.status, err?.code ?? 'http_error', err?.message ?? `Error HTTP ${res.status}`, err?.details)
  }
  return data as T
}

/** Fetch a protected file and trigger a browser download (keeps auth header). */
export async function download(path: string, filename: string, params?: Query) {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${path}${qs(params)}`, { headers })
  if (!res.ok) throw new ApiError(res.status, 'download_failed', `No se pudo descargar (${res.status})`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export interface ProductQuery extends Query {
  page?: number
  page_size?: number
  q?: string
  filters?: string
  issue_level?: string
  issue_code?: string
  sort?: string
  order?: 'asc' | 'desc'
}

export interface ItemsQuery extends ProductQuery {
  only_changed?: boolean
  only_errors?: boolean
  excluded?: boolean
  rule_id?: number
}

export const api = {
  dashboard: () => request<Dashboard>('GET', '/api/dashboard'),
  settings: () => request<Record<string, unknown>>('GET', '/api/settings'),

  sources: () => request<{ items: Source[] }>('GET', '/api/sources'),
  source: (id: number) => request<Source>('GET', `/api/sources/${id}`),
  createUrlSource: (body: { name: string; url: string; item_tag?: string | null }) =>
    request<{ source: Source; job: Job }>('POST', '/api/sources', body),
  uploadSource: (form: FormData) => request<{ source: Source; job: Job }>('POST', '/api/sources/upload', form),
  updateSource: (id: number, body: Partial<Pick<Source, 'name' | 'url' | 'item_tag'>>) =>
    request<Source>('PATCH', `/api/sources/${id}`, body),
  deleteSource: (id: number) => request<void>('DELETE', `/api/sources/${id}`),
  refreshSource: (id: number) => request<{ job: Job }>('POST', `/api/sources/${id}/refresh`),
  snapshots: (id: number) => request<{ items: Snapshot[] }>('GET', `/api/sources/${id}/snapshots`),
  schema: (id: number) => request<{ snapshot_id: number | null; product_count?: number; fields: SchemaField[] }>('GET', `/api/sources/${id}/schema`),

  products: (sourceId: number, query: ProductQuery) =>
    request<Page<Product> & { snapshot_id: number }>('GET', `/api/catalogs/${sourceId}/products`, undefined, query),
  product: (sourceId: number, productId: number) => request<Product>('GET', `/api/catalogs/${sourceId}/products/${productId}`),
  catalogStats: (sourceId: number) => request<CatalogStats>('GET', `/api/catalogs/${sourceId}/stats`),
  catalogIssues: (sourceId: number) =>
    request<{ snapshot_id: number; product_count: number; issues: IssueSummary[] }>('GET', `/api/catalogs/${sourceId}/issues`),

  rules: (sourceId: number, channelId?: number | null) =>
    request<{ items: Rule[] }>('GET', '/api/rules', undefined, { source_id: sourceId, channel_id: channelId ?? undefined }),
  createRule: (body: { source_id: number; channel_id: number | null; definition: RuleDefinition }) =>
    request<Rule>('POST', '/api/rules', body),
  updateRule: (id: number, body: { channel_id: number | null; definition: RuleDefinition }) =>
    request<Rule>('PUT', `/api/rules/${id}`, body),
  deleteRule: (id: number) => request<void>('DELETE', `/api/rules/${id}`),
  ruleVersions: (id: number) =>
    request<{ items: { version: number; definition: RuleDefinition; created_at: string; created_by: string | null }[] }>('GET', `/api/rules/${id}/versions`),
  previewRule: (body: { source_id: number; channel_id: number | null; rule_id: number | null; definition: RuleDefinition; page: number; page_size: number }) =>
    request<PreviewResult>('POST', '/api/rules/preview', body),

  channels: (sourceId?: number) => request<{ items: Channel[] }>('GET', '/api/channels', undefined, { source_id: sourceId }),
  createChannel: (body: { source_id: number; name: string; kind: 'google'; settings: Channel['settings'] }) =>
    request<Channel>('POST', '/api/channels', body),
  updateChannel: (id: number, body: { name?: string; settings?: Channel['settings'] }) =>
    request<Channel>('PATCH', `/api/channels/${id}`, body),
  deleteChannel: (id: number) => request<void>('DELETE', `/api/channels/${id}`),
  rotateToken: (id: number) => request<Channel>('POST', `/api/channels/${id}/rotate-token`),
  versions: (channelId: number) => request<{ items: FeedVersion[] }>('GET', `/api/channels/${channelId}/versions`),
  publications: (channelId: number) =>
    request<{ items: { id: number; version_id: number; action: string; published_at: string; published_by: string }[] }>('GET', `/api/channels/${channelId}/publications`),
  generate: (channelId: number) => request<{ version: FeedVersion; job: Job }>('POST', '/api/feeds/generate', { channel_id: channelId }),
  version: (id: number) => request<FeedVersion & { published: boolean }>('GET', `/api/feed-versions/${id}`),
  publish: (id: number, force = false) => request<Channel>('POST', `/api/feed-versions/${id}/publish`, { force }),
  versionIssues: (id: number) => request<VersionIssues>('GET', `/api/feed-versions/${id}/issues`),
  versionItems: (id: number, query: ItemsQuery) => request<Page<FeedItemRow>>('GET', `/api/feed-versions/${id}/items`, undefined, query),

  jobs: (query: Query) => request<Page<Job>>('GET', '/api/jobs', undefined, query),
  job: (id: number) => request<Job>('GET', `/api/jobs/${id}`),
  auditLogs: () => request<{ items: AuditEntry[] }>('GET', '/api/audit-logs'),
}

export interface Dashboard {
  sources: number
  products: number
  valid: number
  warnings: number
  errors: number
  active_rules: number
  last_sync: string | null
  next_sync: string | null
  channels: {
    id: number; name: string; kind: string; source_id: number
    published_version: { id: number; number: number; items: number; created_at: string } | null
    latest_version: { id: number; number: number; status: string; errors: number; warnings: number; items: number } | null
  }[]
  recent_jobs: Job[]
}

export interface CatalogStats {
  snapshot_id: number
  product_count: number
  levels: Record<string, number>
  top_brands: { value: string | null; count: number }[]
  top_product_types: { value: string | null; count: number }[]
  availability: { value: string | null; count: number }[]
  stats: Record<string, unknown> | null
}

export interface VersionIssues {
  version_id: number
  previous_version_id: number | null
  analyzed: number
  valid: number
  errors: number
  warnings: number
  excluded: number
  previous: FeedVersion | null
  issues: IssueSummary[]
}

export interface AuditEntry {
  id: number
  actor: string
  action: string
  entity: string
  entity_id: number | null
  detail: Record<string, unknown> | null
  created_at: string
}
