import type { RunView, StepFinished, StepStarted } from '../api/types'

export const STEPS = [
  { node: 'parse_posting', label: 'Read the posting' },
  { node: 'retrieve_experience', label: 'Find your evidence' },
  { node: 'match_requirements', label: 'Match requirements' },
  { node: 'research_gaps', label: 'Search again for gaps' },
  { node: 'draft_bullets', label: 'Draft bullets' },
  { node: 'human_review', label: 'Your review' },
  { node: 'finalize', label: 'Finalize' },
] as const

export type StepState = 'done' | 'active' | 'waiting' | 'failed' | 'pending' | 'skipped'

interface Finished {
  detail: string
  seconds?: number // only known for steps seen live
}

export interface Progress {
  finished: Record<string, Finished>
  active: string | null // the step running now
  startedAt: Record<string, number> // elapsed time when each live step started
}

export type ProgressAction =
  | { type: 'follow' }
  | { type: 'load'; run: RunView }
  | ({ type: 'start' } & StepStarted)
  | ({ type: 'finish' } & StepFinished)

export const noProgress: Progress = { finished: {}, active: null, startedAt: {} }

/** Combines the run as the server last described it with the step events seen since. */
export function progressReducer(state: Progress, action: ProgressAction): Progress {
  switch (action.type) {
    case 'follow': // a new stream, and each segment of a run times its steps from zero
      return { ...state, startedAt: {} }
    case 'load': {
      const { run } = action
      const finished = Object.fromEntries(
        run.steps.map((s) => [s.node, { ...state.finished[s.node], detail: s.detail }]),
      )
      return { ...state, finished, active: run.status === 'running' ? run.next_step : null }
    }
    case 'start':
      return {
        ...state,
        active: action.node,
        startedAt: { ...state.startedAt, [action.node]: action.elapsed },
      }
    case 'finish': {
      const started = state.startedAt[action.node]
      const seconds = started === undefined ? undefined : action.elapsed - started
      return {
        ...state,
        finished: { ...state.finished, [action.node]: { detail: action.detail, seconds } },
        active: state.active === action.node ? null : state.active,
      }
    }
  }
}

export interface StepRow {
  node: string
  label: string
  state: StepState
  detail: string
  seconds?: number
}

export function stepRows(run: RunView, progress: Progress): StepRow[] {
  const rows = STEPS.map(({ node, label }): StepRow => {
    const finished = progress.finished[node]
    let state: StepState = 'pending'
    if (progress.active === node && run.status === 'running') state = 'active'
    else if (run.status === 'failed' && run.next_step === node) state = 'failed'
    else if (run.status === 'awaiting_review' && node === 'human_review') state = 'waiting'
    else if (finished || (node === 'human_review' && run.status === 'done')) state = 'done'
    return { node, label, state, detail: finished?.detail ?? '', seconds: finished?.seconds }
  })
  // A step the run went past without running it (no gaps to research, nothing to draft)
  const reached = rows.findLastIndex((r) => r.state !== 'pending')
  return rows.map((r, i) => (i < reached && r.state === 'pending' ? { ...r, state: 'skipped' } : r))
}
