import type { Usage } from './api/types'

const relative = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['day', 86_400],
  ['hour', 3_600],
  ['minute', 60],
]

/** "5 minutes ago", "yesterday", or "just now" */
export function ago(iso: string, now = Date.now()): string {
  const seconds = (new Date(iso).getTime() - now) / 1000
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit)
  }
  return 'just now'
}

const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 })

/** "3 model calls · 12.4K tokens · 34s" */
export function usageLine(usage: Usage): string {
  const calls = `${usage.llm_calls} model call${usage.llm_calls === 1 ? '' : 's'}`
  const tokens = `${compact.format(usage.input_tokens + usage.output_tokens)} tokens`
  const minutes = Math.floor(usage.seconds / 60)
  const time = minutes ? `${minutes}m ${Math.round(usage.seconds % 60)}s` : `${Math.round(usage.seconds)}s`
  return [calls, tokens, time].join(' · ')
}

/** A file name for a tailored resume: "resume-senior-engineer-northwind.md" */
export function fileName(title: string, company: string | null): string {
  const slug = [title, company]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
  return `resume${slug ? `-${slug}` : ''}.md`
}

export function groupBy<T>(items: T[], key: (item: T) => string): [string, T[]][] {
  const groups = new Map<string, T[]>()
  for (const item of items) {
    const k = key(item)
    groups.set(k, [...(groups.get(k) ?? []), item])
  }
  return [...groups]
}
