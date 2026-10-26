import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Link from '@mui/material/Link'
import LinearProgress from '@mui/material/LinearProgress'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { api } from '../api/client'
import type { RunView } from '../api/types'
import { usageLine } from '../format'
import { stepRows } from '../runs/progress'
import { useRun } from '../runs/useRun'
import { ResultView } from './ResultView'
import { ReviewPanel } from './ReviewPanel'
import { StatusChip } from './StatusChip'
import { StepProgress } from './StepProgress'

export function RunPage({ runId, onChange }: { runId: string; onChange?: () => void }) {
  const { run, progress, error, busy, act } = useRun(runId, onChange)

  if (!run) {
    return error ? <Alert severity="error">{error}</Alert> : <LinearProgress />
  }

  return (
    <Stack spacing={2}>
      <Header run={run} />
      {error && <Alert severity="error">{error}</Alert>}
      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: { xs: '1fr', md: '240px 1fr' },
          alignItems: 'start',
        }}
      >
        <Paper sx={{ py: 1 }}>
          <StepProgress rows={stepRows(run, progress)} />
        </Paper>
        <Main run={run} busy={busy} act={act} />
      </Box>
    </Stack>
  )
}

function Header({ run }: { run: RunView }) {
  return (
    <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
      <div>
        <Typography variant="h5">{run.title || 'Reading the posting…'}</Typography>
        {run.company && <Typography color="text.secondary">{run.company}</Typography>}
      </div>
      <StatusChip status={run.status} />
      <Box sx={{ flexGrow: 1 }} />
      {run.usage.llm_calls > 0 && (
        <Typography variant="body2" color="text.secondary" title="Across all steps, not counting your review">
          {usageLine(run.usage)}
          {run.trace_url && (
            <>
              {' · '}
              <Link href={run.trace_url} target="_blank" rel="noreferrer">
                Trace
              </Link>
            </>
          )}
        </Typography>
      )}
    </Stack>
  )
}

interface MainProps {
  run: RunView
  busy: boolean
  act: ReturnType<typeof useRun>['act']
}

function Main({ run, busy, act }: MainProps) {
  if (run.status === 'awaiting_review' && run.review) {
    return (
      <ReviewPanel
        key={run.updated_at} // a new draft (or an edited one) starts in view mode
        review={run.review}
        busy={busy}
        onDecision={(decision) => act(() => api.review(run.id, decision))}
      />
    )
  }
  if (run.status === 'done' && run.result) return <ResultView result={run.result} />
  if (run.status === 'failed') {
    return (
      <Alert
        severity="error"
        action={
          <Button color="inherit" disabled={busy} onClick={() => act(() => api.retry(run.id))}>
            Retry
          </Button>
        }
      >
        {run.error ?? 'The run failed.'}
      </Alert>
    )
  }
  return (
    <Paper sx={{ p: 3 }}>
      <Typography color="text.secondary" gutterBottom>
        Working… steps appear on the left as they finish.
      </Typography>
      <LinearProgress />
    </Paper>
  )
}
