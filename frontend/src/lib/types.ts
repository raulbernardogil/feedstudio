export type Value = string | { [key: string]: Value[] }
export type Attributes = Record<string, Value[]>

export type IssueLevel = 'valid' | 'recommendation' | 'warning' | 'error' | 'excluded'
export type Severity = 'error' | 'warning' | 'recommendation'

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface Snapshot {
  id: number
  source_id: number
  status: 'pending' | 'processing' | 'ready' | 'failed' | 'archived'
  format: string | null
  item_tag: string | null
  namespaces: Record<string, string> | null
  product_count: number
  size_bytes: number | null
  sha256: string | null
  original_filename: string | null
  stats: Record<string, unknown> | null
  error: { code: string; message: string; line: number | null } | null
  created_at: string
}

export interface Source {
  id: number
  name: string
  kind: 'upload' | 'url'
  url: string | null
  item_tag: string | null
  schedule: string
  active_snapshot_id: number | null
  active_snapshot: Snapshot | null
  last_refresh_at: string | null
  created_at: string
}

export interface Job {
  id: number
  kind: 'import' | 'generate'
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  source_id: number | null
  channel_id: number | null
  progress: number
  message: string | null
  params: Record<string, unknown> | null
  result: Record<string, unknown> | null
  error: { code: string; message: string; line?: number | null } | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  events?: { at: string; message: string; progress: number }[]
}

export interface SchemaField {
  key: string
  qname: string
  kind: 'scalar' | 'list' | 'nested'
  inferred_type: string
  present_count: number
  empty_count: number
  max_repeat: number
  coverage: number
  samples: string[]
}

export interface Issue {
  code: string
  severity: Severity
  attribute: string | null
  message: string
}

export interface Product {
  id: number
  position: number
  external_id: string | null
  data: Attributes
  issue_level: IssueLevel
  issue_count: number
  issues?: Issue[]
}

export interface IssueSummary {
  code: string
  severity: Severity
  count: number
  title: string
  recommendation: string | null
  source: string | null
  suggested_rule: Partial<RuleDefinition> | null
  previous_count?: number | null
}

// --- Rules ------------------------------------------------------------------

export type ConditionOperator =
  | 'contains' | 'not_contains' | 'equals' | 'not_equals' | 'starts_with' | 'ends_with'
  | 'is_empty' | 'not_empty' | 'exists' | 'not_exists' | 'greater_than' | 'less_than'
  | 'between' | 'matches_regex' | 'in_list' | 'not_in_list'

export interface Condition {
  field: string
  operator: ConditionOperator
  value?: string | null
  value_to?: string | null
  values?: string[] | null
  value_field?: string | null
  case_sensitive?: boolean
}

export interface ConditionGroup {
  operator: 'and' | 'or'
  conditions: (Condition | ConditionGroup)[]
}

export type Action =
  | { type: 'set_value' | 'set_if_empty' | 'prepend' | 'append'; template: string }
  | { type: 'replace'; find: string; replace_with: string; use_regex?: boolean; case_sensitive?: boolean }
  | { type: 'remove_text'; find: string; use_regex?: boolean; case_sensitive?: boolean }
  | { type: 'uppercase' | 'lowercase' | 'collapse_whitespace' | 'strip_html' | 'exclude' }
  | { type: 'capitalize'; mode: 'sentence' | 'words' }
  | { type: 'truncate'; max_length: number; strategy: 'word' | 'char'; ellipsis?: string }
  | { type: 'copy_from'; field: string }
  | { type: 'map_values'; mappings: { from: string; to: string }[]; case_sensitive?: boolean }
  | { type: 'normalize_price'; decimals: number; default_currency?: string | null }
  | { type: 'regex_extract'; pattern: string; group: number; case_sensitive?: boolean; keep_if_no_match?: boolean }
  | { type: 'add_to_segment'; segment: string }

export type ActionType = Action['type']

export interface RuleDefinition {
  schema_version?: number
  name: string
  description?: string | null
  enabled: boolean
  priority: number
  target: string | null
  condition: ConditionGroup | null
  actions: Action[]
  evaluate_on: 'current' | 'original'
  on_missing_variable: 'empty' | 'fallback' | 'skip_rule' | 'error'
  fallback_value: string
}

export interface Rule {
  id: number
  source_id: number
  channel_id: number | null
  name: string
  enabled: boolean
  priority: number
  version: number
  definition: RuleDefinition
  updated_by: string | null
  created_at: string
  updated_at: string
}

export interface PreviewRow {
  product_id: number
  external_id: string | null
  attribute: string | null
  original: string | null
  before: string | null
  after: string | null
  final: string | null
  excluded: boolean
  new_issues: Issue[]
  rule_issues: { rule_id: number; rule_name: string; message: string }[]
}

export interface PreviewResult {
  scanned: number
  truncated: boolean
  matched: number
  affected: number
  excluded: number
  conflicts: { rule_id: number; name: string; priority: number }[]
  new_issue_counts: Record<string, number>
  page: number
  page_size: number
  items: PreviewRow[]
}

// --- Channels & feeds ----------------------------------------------------------

export interface FeedVersion {
  id: number
  channel_id: number
  snapshot_id: number
  job_id: number | null
  number: number
  status: 'building' | 'ready' | 'failed'
  size_bytes: number | null
  sha256: string | null
  total_count: number
  item_count: number
  excluded_count: number
  changed_count: number
  error_count: number
  warning_count: number
  valid_count: number
  stats: { issues: { code: string; severity: Severity; count: number }[]; levels: Record<string, number>; rule_hits: Record<string, number> } | null
  error: { message: string } | null
  created_at: string
  rules_count: number
  published?: boolean
}

export interface Channel {
  id: number
  source_id: number
  name: string
  kind: 'google'
  settings: { title?: string; link?: string; description?: string }
  published_version_id: number | null
  published_version: FeedVersion | null
  public_url: string
  created_at: string
}

export interface Change {
  rule_id: number
  rule_name: string
  field: string
  before: string | null
  after: string | null
}

export interface FeedItemRow {
  id: number
  product_id: number
  external_id: string | null
  position: number
  excluded: boolean
  changed: boolean
  issue_level: IssueLevel
  original: Attributes
  transformed: Attributes
  changes: Change[]
  rule_issues: { rule_id: number; rule_name: string; message: string }[]
  issues: Issue[]
}
