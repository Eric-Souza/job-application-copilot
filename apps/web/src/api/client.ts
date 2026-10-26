import type {
  ReviewDecision,
  ReviewRequest,
  RunSummary,
  RunView,
  StepFinished,
  StepStarted,
  TailoredResume,
} from './types'

export const API_URL: string = import.meta.env.VITE_API_URL ?? '/api'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) {
      // FastAPI validation errors
      return body.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, '')).join('; ')
    }
  } catch {
    // not JSON
  }
  return `${response.status} ${response.statusText}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError('Could not reach the API. Is it running on port 8000?', 0)
  }
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status)
  return (await response.json()) as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  listRuns: () => request<RunSummary[]>('/runs'),
  getRun: (id: string) => request<RunView>(`/runs/${id}`),
  startRun: (posting: string) => post<RunSummary>('/runs', { posting }),
  review: (id: string, decision: ReviewDecision) => post<RunView>(`/runs/${id}/review`, decision),
  retry: (id: string) => post<RunView>(`/runs/${id}/retry`),
}

export interface RunEventHandlers {
  status?: (run: RunView) => void
  step?: (event: StepStarted) => void
  node?: (event: StepFinished) => void
  review?: (review: ReviewRequest) => void
  done?: (result: TailoredResume) => void
  error?: (error: { message: string }) => void
}

/**
 * Follow a run over SSE. Returns a function that stops following.
 *
 * The server ends the stream when the run pauses or stops, so it's closed here on those events:
 * EventSource would otherwise reconnect. It does reconnect after a network error, and the
 * `status` event that starts every stream brings the view back up to date.
 */
export function followRun(runId: string, handlers: RunEventHandlers): () => void {
  const source = new EventSource(`${API_URL}/runs/${runId}/events`)

  function on<T>(name: keyof RunEventHandlers, last: (data: T) => boolean) {
    source.addEventListener(name, (event) => {
      // EventSource fires its own `error` (with no data) when the connection drops; it reconnects
      if (!('data' in event) || typeof event.data !== 'string') return
      const data = JSON.parse(event.data) as T
      if (last(data)) source.close()
      ;(handlers[name] as ((data: T) => void) | undefined)?.(data)
    })
  }

  on<RunView>('status', (run) => run.status !== 'running')
  on<StepStarted>('step', () => false)
  on<StepFinished>('node', () => false)
  on<ReviewRequest>('review', () => true)
  on<TailoredResume>('done', () => true)
  on<{ message: string }>('error', () => true)

  return () => source.close()
}
