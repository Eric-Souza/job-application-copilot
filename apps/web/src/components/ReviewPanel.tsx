import DeleteOutlined from '@mui/icons-material/DeleteOutlined'
import Undo from '@mui/icons-material/Undo'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import IconButton from '@mui/material/IconButton'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useMemo, useState } from 'react'
import type { BulletSpec, ReviewDecision, ReviewRequest } from '../api/types'
import { BulletGroups, Warnings } from './Bullets'
import { CoverageTable } from './CoverageTable'
import { lookupFrom } from './shared'

interface Props {
  review: ReviewRequest
  busy: boolean
  onDecision: (decision: ReviewDecision) => void
}

type Mode = 'view' | 'revise' | 'edit'

export function ReviewPanel({ review, busy, onDecision }: Props) {
  const [mode, setMode] = useState<Mode>('view')
  const lookup = useMemo(() => lookupFrom(review.requirements, review.evidence), [review])

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h6">Draft {review.revision}</Typography>
          {review.error && <Alert severity="error">Your last decision was rejected: {review.error}</Alert>}
          <Warnings warnings={review.warnings} />
          {mode === 'edit' ? (
            <EditForm review={review} busy={busy} onDecision={onDecision} onCancel={() => setMode('view')} />
          ) : (
            <>
              <section>
                <Typography variant="overline" color="text.secondary">
                  Summary
                </Typography>
                <Typography>{review.summary}</Typography>
              </section>
              <section>
                <Typography variant="overline" color="text.secondary">
                  Bullets
                </Typography>
                <BulletGroups bullets={review.bullets} lookup={lookup} />
              </section>
              {mode === 'revise' ? (
                <ReviseForm busy={busy} onDecision={onDecision} onCancel={() => setMode('view')} />
              ) : (
                <Stack direction="row" spacing={1}>
                  <Button
                    variant="contained"
                    disabled={busy}
                    onClick={() => onDecision({ action: 'approve' })}
                  >
                    Approve
                  </Button>
                  <Button variant="outlined" disabled={busy} onClick={() => setMode('revise')}>
                    Ask for changes
                  </Button>
                  <Button disabled={busy} onClick={() => setMode('edit')}>
                    Edit it myself
                  </Button>
                </Stack>
              )}
            </>
          )}
        </Stack>
      </Paper>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          Requirement coverage
        </Typography>
        <CoverageTable matches={review.coverage} lookup={lookup} />
      </Paper>
    </Stack>
  )
}

interface FormProps {
  busy: boolean
  onDecision: (decision: ReviewDecision) => void
  onCancel: () => void
}

function ReviseForm({ busy, onDecision, onCancel }: FormProps) {
  const [feedback, setFeedback] = useState('')
  return (
    <Stack spacing={1}>
      <TextField
        label="What should change?"
        placeholder="e.g. Lead with the payments work, and make the summary shorter."
        multiline
        minRows={2}
        autoFocus
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
      />
      <Stack direction="row" spacing={1}>
        <Button
          variant="contained"
          disabled={busy || !feedback.trim()}
          onClick={() => onDecision({ action: 'revise', feedback: feedback.trim() })}
        >
          Redraft
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
      </Stack>
    </Stack>
  )
}

/**
 * Edit the summary and bullet text, or drop bullets. A bullet keeps its requirement and evidence
 * ids, so the server can check the edited text against the same evidence.
 */
function EditForm({ review, busy, onDecision, onCancel }: FormProps & { review: ReviewRequest }) {
  const [summary, setSummary] = useState(review.summary)
  const [texts, setTexts] = useState(() => review.bullets.map((b) => b.text))
  const [removed, setRemoved] = useState<Set<number>>(new Set())

  const kept = review.bullets
    .map((b, i) => ({ bullet: b, text: texts[i].trim(), i }))
    .filter(({ text, i }) => text && !removed.has(i))
  const bulletsChanged =
    kept.length !== review.bullets.length || kept.some(({ bullet, text }) => text !== bullet.text)
  const summaryChanged = summary.trim() !== review.summary

  function save() {
    if (!summaryChanged && !bulletsChanged) return onCancel()
    const bullets: BulletSpec[] = kept.map(({ bullet, text }) => ({
      text,
      requirement_ids: bullet.requirement_ids,
      evidence_ids: bullet.evidence_ids,
    }))
    onDecision({
      action: 'edit',
      ...(summaryChanged && { summary: summary.trim() }),
      ...(bulletsChanged && { bullets }),
    })
  }

  function toggle(i: number) {
    setRemoved((prev) => {
      const next = new Set(prev)
      if (!next.delete(i)) next.add(i)
      return next
    })
  }

  return (
    <Stack spacing={2}>
      <TextField
        label="Summary"
        multiline
        minRows={2}
        value={summary}
        onChange={(e) => setSummary(e.target.value)}
      />
      {review.bullets.map((bullet, i) => (
        <Stack key={i} direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
          <TextField
            label={bullet.role || `Bullet ${i + 1}`}
            multiline
            fullWidth
            disabled={removed.has(i)}
            value={texts[i]}
            onChange={(e) => setTexts((prev) => prev.map((t, j) => (j === i ? e.target.value : t)))}
            sx={removed.has(i) ? { textDecoration: 'line-through' } : undefined}
          />
          <Tooltip title={removed.has(i) ? 'Keep this bullet' : 'Drop this bullet'}>
            <IconButton
              aria-label={removed.has(i) ? `Keep bullet ${i + 1}` : `Drop bullet ${i + 1}`}
              onClick={() => toggle(i)}
            >
              {removed.has(i) ? <Undo /> : <DeleteOutlined />}
            </IconButton>
          </Tooltip>
        </Stack>
      ))}
      {kept.length === 0 && <Alert severity="info">Keep at least one bullet.</Alert>}
      <Typography variant="body2" color="text.secondary">
        Edits are checked against the evidence like the model's drafts, then shown to you again.
      </Typography>
      <Stack direction="row" spacing={1}>
        <Button variant="contained" disabled={busy || kept.length === 0 || !summary.trim()} onClick={save}>
          Save edits
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
      </Stack>
    </Stack>
  )
}
