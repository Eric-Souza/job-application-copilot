import Chip from '@mui/material/Chip'
import type { RunStatus } from '../api/types'

const LOOK: Record<RunStatus, { label: string; color: 'info' | 'warning' | 'success' | 'error' }> = {
  running: { label: 'Running', color: 'info' },
  awaiting_review: { label: 'Needs review', color: 'warning' },
  done: { label: 'Done', color: 'success' },
  failed: { label: 'Failed', color: 'error' },
}

export function StatusChip({ status }: { status: RunStatus }) {
  const { label, color } = LOOK[status]
  return <Chip size="small" variant="outlined" label={label} color={color} />
}
