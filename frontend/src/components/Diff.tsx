import { diffWords } from '../lib/diff'

/** Presentational: highlights inserted/deleted words between two values. */
export function Diff({ before, after }: { before: string | null; after: string | null }) {
  if (before === null && after === null) return <span className="text-slate-400">—</span>
  if (before === null) return <span className="diff-ins rounded px-0.5">{after}</span>
  if (after === null) return <span className="diff-del rounded px-0.5">{before}</span>
  return (
    <span className="whitespace-pre-wrap break-words">
      {diffWords(before, after).map((p, i) =>
        p.type === 'same' ? <span key={i}>{p.text}</span> : <span key={i} className={p.type === 'ins' ? 'diff-ins rounded' : 'diff-del rounded'}>{p.text}</span>,
      )}
    </span>
  )
}
