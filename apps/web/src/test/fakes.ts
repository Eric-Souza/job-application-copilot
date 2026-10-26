import { vi } from 'vitest'
import type { ReviewRequest, RunView, TailoredResume } from '../api/types'

/** Stands in for EventSource: tests push server events with emit(). */
export class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  private listeners = new Map<string, ((event: Event) => void)[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  static latest(): FakeEventSource {
    return FakeEventSource.instances[FakeEventSource.instances.length - 1]
  }

  static install() {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  }

  addEventListener(name: string, listener: (event: Event) => void) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener])
  }

  close() {
    this.closed = true
  }

  emit(name: string, data: unknown) {
    const event = new MessageEvent(name, { data: JSON.stringify(data) })
    this.listeners.get(name)?.forEach((listener) => listener(event))
  }

  /** What the browser fires when the connection drops */
  drop() {
    this.listeners.get('error')?.forEach((listener) => listener(new Event('error')))
  }
}

type Route = (body: unknown) => unknown

/** Stub fetch with handlers keyed by "METHOD /path"; returns the calls made. */
export function stubFetch(routes: Record<string, Route | { status: number; body: unknown }>) {
  const calls: { method: string; path: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const path = url.replace(/^\/api/, '')
      const body = init?.body ? JSON.parse(init.body as string) : undefined
      calls.push({ method, path, body })
      const route = routes[`${method} ${path}`]
      if (!route) return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 })
      if (typeof route === 'function') return Response.json(route(body))
      return new Response(JSON.stringify(route.body), { status: route.status })
    }),
  )
  return calls
}

export const REVIEW: ReviewRequest = {
  revision: 1,
  summary: 'Backend engineer who ships payment systems.',
  bullets: [
    {
      text: 'Built a payments API in Go handling 2M requests a day.',
      requirement_ids: ['R1'],
      evidence_ids: ['E1'],
      role: 'Engineer · Acme',
      flags: [],
    },
    {
      text: 'Cut deploy time by 80% with a new CI pipeline.',
      requirement_ids: ['R2'],
      evidence_ids: ['E2'],
      role: 'Engineer · Acme',
      flags: ['"80%" is not in the evidence'],
    },
  ],
  warnings: [],
  coverage: [
    { requirement_id: 'R1', coverage: 'strong', evidence_ids: ['E1'], rationale: 'Built one.' },
    { requirement_id: 'R2', coverage: 'partial', evidence_ids: ['E2'], rationale: 'Some CI work.' },
    { requirement_id: 'R3', coverage: 'missing', evidence_ids: [], rationale: 'Nothing on Kubernetes.' },
  ],
  requirements: [
    { id: 'R1', text: 'Go', kind: 'must', category: 'skill' },
    { id: 'R2', text: 'CI/CD', kind: 'must', category: 'skill' },
    { id: 'R3', text: 'Kubernetes', kind: 'nice', category: 'skill' },
  ],
  evidence: [
    { id: 'E1', role: 'Engineer · Acme', content: 'Payments API in Go, 2M requests a day' },
    { id: 'E2', role: 'Engineer · Acme', content: 'Rebuilt the CI pipeline' },
  ],
}

export const RESULT: TailoredResume = {
  title: 'Senior Backend Engineer',
  company: 'Northwind',
  summary: REVIEW.summary,
  bullets: REVIEW.bullets,
  coverage: { strong: 1, partial: 1, missing: 1 },
  gaps: ['Go'],
  warnings: [],
  markdown: '# Senior Backend Engineer\n\n- Built a payments API',
}

const STEPS_SO_FAR = [
  { node: 'parse_posting', detail: '3 requirements' },
  { node: 'retrieve_experience', detail: '2 pieces of evidence' },
  { node: 'match_requirements', detail: '1 strong, 1 partial, 1 missing' },
  { node: 'draft_bullets', detail: 'draft 1: 2 bullets' },
]

export function runView(overrides: Partial<RunView> = {}): RunView {
  return {
    id: 'r1',
    status: 'running',
    title: '',
    company: null,
    error: null,
    created_at: '2026-10-26T12:00:00Z',
    updated_at: '2026-10-26T12:00:00Z',
    steps: [],
    next_step: 'parse_posting',
    review: null,
    result: null,
    ...overrides,
  }
}

export function pausedView(overrides: Partial<RunView> = {}): RunView {
  return runView({
    status: 'awaiting_review',
    title: 'Senior Backend Engineer',
    company: 'Northwind',
    steps: STEPS_SO_FAR,
    next_step: 'human_review',
    review: REVIEW,
    updated_at: '2026-10-26T12:01:00Z',
    ...overrides,
  })
}
