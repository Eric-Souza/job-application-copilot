import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { api, followRun } from '../api/client'
import type { DraftPreview, RunView } from '../api/types'
import { noProgress, progressReducer } from './progress'

/**
 * A run, kept live: loads it, follows its events, and reloads it when it pauses or stops.
 * `onChange` fires when the run's title or status changes, so a list of runs can refresh.
 */
export function useRun(runId: string, onChange?: () => void) {
  const [run, setRun] = useState<RunView | null>(null)
  const [progress, dispatch] = useReducer(progressReducer, noProgress)
  const [error, setError] = useState<string | null>(null)
  // The draft being written, tagged with the stream it came from so an old segment's draft isn't shown
  const [live, setLive] = useState<{ stream: string; draft: DraftPreview } | null>(null)
  const [busy, setBusy] = useState(false) // sending an action
  const [segment, setSegment] = useState(0) // bumped to follow the run again after an action
  const changed = useRef(onChange)
  useEffect(() => {
    changed.current = onChange
  })

  const show = useCallback((view: RunView) => {
    setRun(view)
    dispatch({ type: 'load', run: view })
  }, [])

  useEffect(() => {
    const reload = () =>
      api.getRun(runId).then(
        (view) => {
          show(view)
          changed.current?.()
        },
        (e: Error) => setError(e.message),
      )
    dispatch({ type: 'follow' })
    const stream = `${runId}:${segment}`
    return followRun(runId, {
      status: show,
      step: (event) => dispatch({ type: 'start', ...event }),
      draft: (draft) => setLive({ stream, draft }),
      node: (event) => {
        dispatch({ type: 'finish', ...event })
        if (event.node === 'parse_posting') reload() // the run has a title now
      },
      review: reload,
      done: reload,
      error: reload,
    })
  }, [runId, segment, show])

  /** Send a review decision or a retry; the run continues in the background, so follow it again. */
  const act = useCallback(
    async (action: () => Promise<RunView>) => {
      setError(null)
      setBusy(true)
      try {
        show(await action())
        setSegment((n) => n + 1)
        changed.current?.()
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setBusy(false)
      }
    },
    [show],
  )

  const draft = live?.stream === `${runId}:${segment}` ? live.draft : null
  return { run, progress, draft, error, busy, act }
}
