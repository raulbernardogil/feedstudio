import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { JobStatus } from '../../components/JobStatus'
import { Button, Dialog, ErrorBox, Field, Input } from '../../components/ui'
import { api } from '../../lib/api'
import { useJob } from '../../lib/useJob'
import { useWorkspace } from '../../lib/workspace'

const schema = z.object({
  name: z.string().trim().min(1, 'Indica un nombre').max(200),
  mode: z.enum(['upload', 'url']),
  url: z.string().trim().optional(),
  item_tag: z.string().trim().max(200).optional(),
}).refine((v) => v.mode === 'upload' || /^https:\/\//i.test(v.url ?? ''), { path: ['url'], message: 'Introduce una URL https:// de descarga directa' })

type FormValues = z.infer<typeof schema>

/** Container: create a source by file upload or HTTPS URL and follow its import job. */
export function AddSourceDialog({ open, onOpenChange, existingSourceId }: { open: boolean; onOpenChange: (o: boolean) => void; existingSourceId?: number }) {
  const qc = useQueryClient()
  const ws = useWorkspace()
  const [file, setFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<number | null>(null)
  const job = useJob(jobId, [['sources'], ['dashboard'], ['schema'], ['products'], ['catalog-issues'], ['snapshots']])
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { name: existingSourceId ? 'snapshot' : '', mode: 'upload', url: '', item_tag: '' } })
  const mode = form.watch('mode')

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      if (values.mode === 'upload' || existingSourceId) {
        if (!file) throw new Error('Selecciona un archivo .xml o .xml.gz')
        const fd = new FormData()
        fd.set('file', file)
        fd.set('name', values.name || file.name)
        if (values.item_tag) fd.set('item_tag', values.item_tag)
        if (existingSourceId) fd.set('source_id', String(existingSourceId))
        return api.uploadSource(fd)
      }
      return api.createUrlSource({ name: values.name, url: values.url ?? '', item_tag: values.item_tag || null })
    },
    onSuccess: (res) => {
      setJobId(res.job.id)
      ws.setSourceId(res.source.id)
      void qc.invalidateQueries({ queryKey: ['sources'] })
    },
  })

  const close = (o: boolean) => {
    if (!o) {
      setJobId(null)
      setFile(null)
      form.reset()
      mutation.reset()
    }
    onOpenChange(o)
  }

  const submit = form.handleSubmit((values) => mutation.mutate(values))
  return (
    <Dialog open={open} onOpenChange={close} title={existingSourceId ? 'Subir nueva versión del feed' : 'Añadir fuente XML'}
      description="El archivo original se guarda de forma inmutable; las reglas trabajan sobre una copia lógica.">
      {jobId ? (
        <div className="space-y-4">
          <JobStatus job={job} />
          <div className="flex justify-end">
            <Button variant="primary" onClick={() => close(false)} disabled={job?.status === 'running' || job?.status === 'queued'}>
              Cerrar
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {!existingSourceId && (
            <>
              <Field label="Nombre" error={form.formState.errors.name?.message}>
                <Input {...form.register('name')} placeholder="Tienda Demo" autoFocus />
              </Field>
              <div className="flex gap-4 text-sm" role="radiogroup" aria-label="Origen">
                <label className="flex items-center gap-2">
                  <input type="radio" value="upload" {...form.register('mode')} /> Archivo local
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" value="url" {...form.register('mode')} /> URL HTTPS
                </label>
              </div>
            </>
          )}
          {mode === 'upload' || existingSourceId ? (
            <Field label="Archivo XML" hint="RSS 2.0 (Google), Atom 1.0 o XML personalizado. Se admite GZIP.">
              <Input type="file" accept=".xml,.gz,application/xml,text/xml,application/gzip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </Field>
          ) : (
            <Field label="URL del feed" error={form.formState.errors.url?.message} hint="Solo HTTPS a destinos públicos (las redes privadas se bloquean).">
              <Input {...form.register('url')} placeholder="https://www.mitienda.com/feed.xml" />
            </Field>
          )}
          {!existingSourceId && (
            <Field label="Nodo de producto (opcional)" hint="Solo para XML personalizado, p. ej. 'producto'. Se autodetecta si se deja vacío.">
              <Input {...form.register('item_tag')} placeholder="item" />
            </Field>
          )}
          <ErrorBox error={mutation.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => close(false)}>
              Cancelar
            </Button>
            <Button type="submit" variant="primary" loading={mutation.isPending}>
              Importar
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  )
}
