// Mirrors the API's Pydantic models (apps/api/app/schemas.py and services/runs.py)

export type RunStatus = 'running' | 'awaiting_review' | 'done' | 'failed'
export type Coverage = 'strong' | 'partial' | 'missing'

export interface RunSummary {
  id: string
  status: RunStatus
  title: string
  company: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface Step {
  node: string
  detail: string
}

export interface Usage {
  llm_calls: number
  input_tokens: number
  output_tokens: number
  seconds: number // time spent running, not waiting for review
}

export interface RunView extends RunSummary {
  usage: Usage
  trace_url: string | null // the run's session in Langfuse, when tracing is on
  steps: Step[] // the steps that have produced their output so far
  next_step: string | null // running now, waiting for review, or the one that failed
  review: ReviewRequest | null
  result: TailoredResume | null
}

export interface BulletSpec {
  text: string
  requirement_ids: string[]
  evidence_ids: string[]
}

export interface Bullet extends BulletSpec {
  role: string // the role or project its evidence comes from
  flags: string[] // grounding problems to check
}

export interface Requirement {
  id: string
  text: string
  kind: 'must' | 'nice'
  category: string
}

export interface Match {
  requirement_id: string
  coverage: Coverage
  evidence_ids: string[]
  rationale: string
}

export interface Evidence {
  id: string
  role: string
  content: string
}

/** What the graph shows while paused on a draft */
export interface ReviewRequest {
  revision: number
  summary: string
  bullets: Bullet[]
  warnings: string[]
  coverage: Match[]
  requirements?: Requirement[] // missing on runs paused before the UI existed
  evidence?: Evidence[]
  error?: string // why the last decision was rejected
}

export interface TailoredResume {
  title: string
  company: string | null
  summary: string
  bullets: Bullet[]
  coverage: Record<Coverage, number>
  gaps: string[] // must-have requirements with no evidence
  warnings: string[]
  markdown: string
}

export type ReviewDecision =
  | { action: 'approve' }
  | { action: 'revise'; feedback: string }
  | { action: 'edit'; summary?: string; bullets?: BulletSpec[] }

// SSE payloads
export interface StepStarted {
  node: string
  elapsed: number // seconds since this segment of the run started
}

export interface StepFinished extends StepStarted {
  detail: string
}
