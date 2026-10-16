export interface DiffPart {
  type: 'same' | 'del' | 'ins'
  text: string
}

const MAX_TOKENS = 1500

/** Word-level LCS diff used to highlight before/after values (display only). */
export function diffWords(before: string, after: string): DiffPart[] {
  const a = before.split(/(\s+)/)
  const b = after.split(/(\s+)/)
  if (a.length > MAX_TOKENS || b.length > MAX_TOKENS) {
    return before === after ? [{ type: 'same', text: before }] : [{ type: 'del', text: before }, { type: 'ins', text: after }]
  }
  const dp: number[][] = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  const parts: DiffPart[] = []
  const push = (type: DiffPart['type'], text: string) => {
    const last = parts[parts.length - 1]
    if (last && last.type === type) last.text += text
    else parts.push({ type, text })
  }
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push('same', a[i])
      i++
      j++
    } else if (dp[i + 1][j] >= dp[i][j + 1]) push('del', a[i++])
    else push('ins', b[j++])
  }
  while (i < a.length) push('del', a[i++])
  while (j < b.length) push('ins', b[j++])
  return parts
}
