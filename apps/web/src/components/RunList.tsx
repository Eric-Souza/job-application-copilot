import Alert from '@mui/material/Alert'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { RunSummary } from '../api/types'
import { ago } from '../format'
import { StatusChip } from './StatusChip'

interface Props {
  runs: RunSummary[] | null
  error: string | null
  selected: string | null
  onSelect: (id: string) => void
}

export function RunList({ runs, error, selected, onSelect }: Props) {
  if (error) return <Alert severity="error">{error}</Alert>
  if (runs === null) return null
  if (runs.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ px: 2, py: 1 }}>
        No runs yet.
      </Typography>
    )
  }
  return (
    <List dense disablePadding aria-label="Runs">
      {runs.map((run) => (
        <ListItemButton key={run.id} selected={run.id === selected} onClick={() => onSelect(run.id)}>
          <ListItemText
            primary={run.title || (run.status === 'running' ? 'Reading the posting…' : 'Untitled')}
            secondary={
              <Stack component="span" direction="row" spacing={1} sx={{ alignItems: 'center', mt: 0.5 }}>
                <StatusChip status={run.status} />
                <span>{[run.company, ago(run.created_at)].filter(Boolean).join(' · ')}</span>
              </Stack>
            }
            slotProps={{ secondary: { component: 'div' } }}
          />
        </ListItemButton>
      ))}
    </List>
  )
}
