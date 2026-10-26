import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useState } from 'react'
import { api } from '../api/client'

const MIN_LENGTH = 50 // the API's limits
const MAX_LENGTH = 30_000

export function NewRun({ onStarted }: { onStarted: (runId: string) => void }) {
  const [posting, setPosting] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const length = posting.trim().length

  async function start(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onStarted((await api.startRun(posting.trim())).id)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <Paper component="form" onSubmit={start} sx={{ p: 3 }}>
      <Stack spacing={2}>
        <div>
          <Typography variant="h5">Tailor your resume</Typography>
          <Typography color="text.secondary">
            Paste a job posting. The agent reads it, finds matching evidence in your indexed experience, and
            drafts a summary and bullets for you to review.
          </Typography>
        </div>
        <TextField
          label="Job posting"
          multiline
          minRows={14}
          maxRows={30}
          value={posting}
          onChange={(e) => setPosting(e.target.value)}
          helperText={
            length < MIN_LENGTH
              ? `At least ${MIN_LENGTH} characters (${length} so far)`
              : `${length.toLocaleString()} characters`
          }
          error={length > MAX_LENGTH}
        />
        {error && <Alert severity="error">{error}</Alert>}
        <div>
          <Button
            type="submit"
            variant="contained"
            disabled={busy || length < MIN_LENGTH || length > MAX_LENGTH}
          >
            {busy ? 'Starting…' : 'Start'}
          </Button>
        </div>
      </Stack>
    </Paper>
  )
}
