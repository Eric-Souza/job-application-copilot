import CheckCircle from '@mui/icons-material/CheckCircle'
import ErrorOutlined from '@mui/icons-material/ErrorOutlined'
import PauseCircleOutlined from '@mui/icons-material/PauseCircleOutlined'
import RadioButtonUnchecked from '@mui/icons-material/RadioButtonUnchecked'
import CircularProgress from '@mui/material/CircularProgress'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import type { StepRow, StepState } from '../runs/progress'

const ICONS: Record<StepState, React.ReactNode> = {
  done: <CheckCircle color="success" fontSize="small" />,
  active: <CircularProgress size={18} />,
  waiting: <PauseCircleOutlined color="warning" fontSize="small" />,
  failed: <ErrorOutlined color="error" fontSize="small" />,
  pending: <RadioButtonUnchecked color="disabled" fontSize="small" />,
}

function secondary(row: StepRow): string {
  if (row.state === 'waiting') return 'Waiting for you'
  if (row.state === 'failed') return 'Failed here'
  const time = row.seconds === undefined ? '' : `${row.seconds.toFixed(1)}s`
  return [row.detail, time].filter(Boolean).join(' · ')
}

export function StepProgress({ rows }: { rows: StepRow[] }) {
  return (
    <List dense aria-label="Progress">
      {rows.map((row) => (
        <ListItem key={row.node} data-state={row.state}>
          <ListItemIcon sx={{ minWidth: 34 }}>{ICONS[row.state]}</ListItemIcon>
          <ListItemText
            primary={row.label}
            secondary={secondary(row)}
            slotProps={{ primary: { color: row.state === 'pending' ? 'text.disabled' : 'text.primary' } }}
          />
        </ListItem>
      ))}
    </List>
  )
}
