import { keepPreviousData, useQuery } from '@tanstack/react-query'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import clsx from 'clsx'
import { ArrowDown, ArrowUp, Columns3, Download, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Badge, Button, Card, Drawer, EmptyState, ErrorBox, Input, LevelBadge, PageHeader, Pagination, Select, Spinner } from '../../components/ui'
import { api, download } from '../../lib/api'
import { text, truncate } from '../../lib/format'
import type { Product } from '../../lib/types'
import { useWorkspace } from '../../lib/workspace'
import { AttributeList } from './AttributeList'
import { ColumnPicker } from './ColumnPicker'
import { EXPECTED, STATUS_COLUMN, useColumns } from './columns'
import type { AttributeFilter } from './FilterBar'
import { FilterBar } from './FilterBar'

export function CatalogPage() {
  const ws = useWorkspace()
  if (!ws.loading && !ws.source) return <EmptyState title="Sin catálogo">Primero añade una fuente XML.</EmptyState>
  if (!ws.source) return <Spinner />
  return <CatalogTable sourceId={ws.source.id} key={ws.source.id} />
}

function CatalogTable({ sourceId }: { sourceId: number }) {
  const [params, setParams] = useSearchParams()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [filters, setFilters] = useState<AttributeFilter[]>([])
  const [level, setLevel] = useState<string>(params.get('issue_level') ?? '')
  const issueCode = params.get('issue_code') ?? ''
  const [sorting, setSorting] = useState<SortingState>([])
  const [columns, setColumns] = useColumns(`feedstudio.columns.catalog.${sourceId}`)
  const [picking, setPicking] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)

  useEffect(() => setPage(1), [q, filters, level, issueCode, pageSize, sorting])

  const schema = useQuery({ queryKey: ['schema', sourceId], queryFn: () => api.schema(sourceId) })
  const query = {
    page,
    page_size: pageSize,
    q,
    filters: filters.length ? JSON.stringify(filters) : undefined,
    issue_level: level || undefined,
    issue_code: issueCode || undefined,
    sort: sorting[0]?.id === STATUS_COLUMN ? 'issue_level' : sorting[0]?.id,
    order: sorting[0]?.desc ? ('desc' as const) : ('asc' as const),
  }
  const products = useQuery({
    queryKey: ['products', sourceId, query],
    queryFn: () => api.products(sourceId, query),
    placeholderData: keepPreviousData,
  })

  const columnDefs = useMemo<ColumnDef<Product>[]>(
    () =>
      columns.map((c) => ({
        id: c.key,
        header: c.label,
        enableSorting: true,
        cell: ({ row }) => {
          if (c.key === STATUS_COLUMN) return <LevelBadge level={row.original.issue_level} />
          const value = text(row.original.data, c.key)
          if (!value.trim()) {
            return EXPECTED.has(c.key) ? <Badge tone="error">falta</Badge> : <span className="text-slate-300">—</span>
          }
          return <span title={value}>{truncate(value, c.key === 'description' ? 60 : 70)}</span>
        },
      })),
    [columns],
  )

  const table = useReactTable({
    data: products.data?.items ?? [],
    columns: columnDefs,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    state: { sorting },
    onSortingChange: setSorting,
  })

  return (
    <>
      <PageHeader
        title="Catálogo"
        description="Datos originales normalizados del último snapshot (sin reglas). La búsqueda, filtros, orden y paginación se ejecutan en el servidor."
        actions={
          <>
            <Button onClick={() => setPicking(true)}><Columns3 className="h-4 w-4" /> Columnas</Button>
            <Button onClick={() => void download(`/api/catalogs/${sourceId}/products/export`, `catalogo-${sourceId}.csv`, { q, filters: query.filters, issue_level: query.issue_level, issue_code: query.issue_code })}>
              <Download className="h-4 w-4" /> Exportar filtrados (CSV)
            </Button>
          </>
        }
      />
      <Card>
        <div className="mb-3 flex flex-wrap items-start gap-3">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setQ(search) }}>
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="SKU exacto o texto (título, marca, MPN, GTIN)" className="w-80" aria-label="Buscar productos" />
            <Button type="submit"><Search className="h-4 w-4" /></Button>
          </form>
          <Select value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Estado de validación">
            <option value="">Todos los estados</option>
            <option value="error">Con errores</option>
            <option value="warning">Con advertencias</option>
            <option value="recommendation">Con recomendaciones</option>
            <option value="valid">Válidos</option>
          </Select>
          {issueCode && (
            <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2.5 py-1 text-xs text-rose-700">
              Incidencia: <code>{issueCode}</code>
              <button onClick={() => { params.delete('issue_code'); setParams(params) }} aria-label="Quitar filtro de incidencia">×</button>
            </span>
          )}
        </div>
        <FilterBar fields={schema.data?.fields ?? []} filters={filters} onChange={setFilters} />
      </Card>

      <div className="mt-4 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <ErrorBox error={products.error} onRetry={() => void products.refetch()} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((h) => (
                    <th key={h.id} className="whitespace-nowrap px-3 py-2">
                      <button className="inline-flex items-center gap-1 uppercase" onClick={h.column.getToggleSortingHandler()}>
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {h.column.getIsSorted() === 'asc' && <ArrowUp className="h-3 w-3" />}
                        {h.column.getIsSorted() === 'desc' && <ArrowDown className="h-3 w-3" />}
                      </button>
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className={clsx('divide-y divide-slate-100', products.isFetching && 'opacity-60')}>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="cursor-pointer hover:bg-brand-50/40" onClick={() => setSelected(row.original.id)}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="max-w-xs px-3 py-2 align-top">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {products.isLoading && <Spinner />}
          {products.data && products.data.items.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No hay productos con estos criterios.</p>}
        </div>
        <Pagination page={page} pageSize={pageSize} total={products.data?.total ?? 0} onPage={setPage} onPageSize={setPageSize} />
      </div>

      <ColumnPicker open={picking} onOpenChange={setPicking} columns={columns} onChange={setColumns} fields={schema.data?.fields ?? []} />
      <ProductDrawer sourceId={sourceId} productId={selected} onClose={() => setSelected(null)} />
    </>
  )
}

function ProductDrawer({ sourceId, productId, onClose }: { sourceId: number; productId: number | null; onClose: () => void }) {
  const product = useQuery({ queryKey: ['product', sourceId, productId], queryFn: () => api.product(sourceId, productId as number), enabled: productId !== null })
  return (
    <Drawer open={productId !== null} onOpenChange={(o) => !o && onClose()} title={product.data ? `Producto ${product.data.external_id ?? product.data.id}` : 'Producto'}>
      {product.isLoading && <Spinner />}
      <ErrorBox error={product.error} />
      {product.data && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <LevelBadge level={product.data.issue_level} />
            <span className="text-xs text-slate-500">Posición {product.data.position} en el XML</span>
          </div>
          {product.data.issues && product.data.issues.length > 0 && (
            <ul className="space-y-1 rounded-md border border-slate-200 p-3 text-sm">
              {product.data.issues.map((i, n) => (
                <li key={n} className="flex items-start gap-2">
                  <LevelBadge level={i.severity} />
                  <span>{i.message} {i.attribute && <code className="text-xs text-slate-500">{i.attribute}</code>}</span>
                </li>
              ))}
            </ul>
          )}
          <AttributeList data={product.data.data} />
        </div>
      )}
    </Drawer>
  )
}
