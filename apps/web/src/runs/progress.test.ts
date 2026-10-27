import { describe, expect, it } from 'vitest'
import { pausedView, runView } from '../test/fakes'
import { noProgress, progressReducer, stepRows, type ProgressAction } from './progress'

const states = (rows: ReturnType<typeof stepRows>) => rows.map((r) => r.state)

function apply(...actions: ProgressAction[]) {
  return actions.reduce(progressReducer, noProgress)
}

describe('step progress', () => {
  it('shows a paused run as drafted and waiting for review', () => {
    const run = pausedView()
    const rows = stepRows(run, apply({ type: 'load', run }))

    expect(states(rows)).toEqual(['done', 'done', 'done', 'done', 'done', 'waiting', 'pending'])
    expect(rows[0].detail).toBe('3 requirements')
  })

  it('follows steps live and times them', () => {
    const run = runView()
    const progress = apply(
      { type: 'load', run },
      { type: 'start', node: 'parse_posting', elapsed: 0 },
      { type: 'finish', node: 'parse_posting', elapsed: 2.5, detail: '3 requirements' },
      { type: 'start', node: 'retrieve_experience', elapsed: 2.5 },
    )
    const rows = stepRows(run, progress)

    expect(states(rows)).toEqual(['done', 'active', 'pending', 'pending', 'pending', 'pending', 'pending'])
    expect(rows[0]).toMatchObject({ detail: '3 requirements', seconds: 2.5 })
  })

  it('shows a redraft as active even though the step finished before', () => {
    const run = pausedView({ status: 'running', review: null })
    const progress = apply({ type: 'load', run }, { type: 'start', node: 'draft_bullets', elapsed: 0 })

    expect(stepRows(run, progress)[4].state).toBe('active')
  })

  it('marks the step a failed run stopped at', () => {
    const run = runView({
      status: 'failed',
      next_step: 'match_requirements',
      steps: pausedView().steps.slice(0, 2),
    })

    expect(states(stepRows(run, apply({ type: 'load', run })))).toEqual([
      'done',
      'done',
      'failed',
      'pending',
      'pending',
      'pending',
      'pending',
    ])
  })

  it('marks steps the run went past as skipped', () => {
    // Every requirement was strong, so there was nothing to search again for
    const steps = pausedView().steps.filter((s) => s.node !== 'research_gaps')
    const run = pausedView({ steps })
    const rows = stepRows(run, apply({ type: 'load', run }))

    expect(states(rows)).toEqual(['done', 'done', 'done', 'skipped', 'done', 'waiting', 'pending'])
  })

  it('does not time a step against an earlier segment', () => {
    const progress = apply(
      { type: 'start', node: 'draft_bullets', elapsed: 9 },
      { type: 'finish', node: 'draft_bullets', elapsed: 14, detail: 'draft 1: 2 bullets' },
      { type: 'follow' }, // a redraft; its start was missed
      { type: 'finish', node: 'draft_bullets', elapsed: 5, detail: 'draft 2: 2 bullets' },
    )

    expect(progress.finished.draft_bullets).toEqual({ detail: 'draft 2: 2 bullets', seconds: undefined })
  })

  it('keeps live timings when the run is reloaded', () => {
    const progress = apply(
      { type: 'start', node: 'parse_posting', elapsed: 0 },
      { type: 'finish', node: 'parse_posting', elapsed: 1, detail: '3 requirements' },
      { type: 'load', run: pausedView() },
    )

    expect(progress.finished.parse_posting.seconds).toBe(1)
  })
})
