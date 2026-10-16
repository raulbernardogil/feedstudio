import { useEffect, useState } from 'react'

export interface ColumnSpec {
  key: string
  label: string
}

export const STATUS_COLUMN = '__status'

export const DEFAULT_COLUMNS: ColumnSpec[] = [
  { key: 'id', label: 'ID/SKU' },
  { key: 'title', label: 'Título' },
  { key: 'description', label: 'Descripción' },
  { key: 'price', label: 'Precio' },
  { key: 'availability', label: 'Disponibilidad' },
  { key: 'brand', label: 'Marca' },
  { key: 'product_type', label: 'Categoría' },
  { key: 'color', label: 'Color' },
  { key: 'size', label: 'Talla' },
  { key: STATUS_COLUMN, label: 'Estado' },
]

/** Attributes that a product is expected to have; blank values are highlighted. */
export const EXPECTED = new Set(['id', 'title', 'description', 'link', 'image_link', 'price', 'availability', 'brand'])

/** Column configuration persisted per source and view. */
export function useColumns(storageKey: string) {
  const [columns, setColumns] = useState<ColumnSpec[]>(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      return raw ? (JSON.parse(raw) as ColumnSpec[]) : DEFAULT_COLUMNS
    } catch {
      return DEFAULT_COLUMNS
    }
  })
  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(columns))
  }, [storageKey, columns])
  return [columns, setColumns] as const
}
