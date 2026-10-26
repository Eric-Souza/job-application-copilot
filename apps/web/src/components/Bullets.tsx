import Alert from '@mui/material/Alert'
import Chip from '@mui/material/Chip'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import type { Bullet } from '../api/types'
import { groupBy } from '../format'
import type { Lookup } from './shared'

function IdChip({ id, title }: { id: string; title?: string }) {
  const chip = <Chip size="small" variant="outlined" label={id} sx={{ height: 20, fontSize: 12 }} />
  return title ? <Tooltip title={title}>{chip}</Tooltip> : chip
}

function BulletItem({ bullet, lookup }: { bullet: Bullet; lookup?: Lookup }) {
  return (
    <li>
      <Typography>{bullet.text}</Typography>
      {lookup && (
        <Stack direction="row" spacing={0.5} sx={{ mt: 0.5, flexWrap: 'wrap', rowGap: 0.5 }}>
          {bullet.requirement_ids.map((id) => (
            <IdChip key={id} id={id} title={lookup.requirements.get(id)?.text} />
          ))}
          {bullet.evidence_ids.map((id) => (
            <IdChip key={id} id={id} title={lookup.evidence.get(id)?.content} />
          ))}
        </Stack>
      )}
      {bullet.flags.map((flag) => (
        <Alert key={flag} severity="warning" sx={{ mt: 0.5, py: 0 }}>
          Check: {flag}
        </Alert>
      ))}
    </li>
  )
}

/** Bullets under the role or project they came from, like they'd sit on a resume. */
export function BulletGroups({ bullets, lookup }: { bullets: Bullet[]; lookup?: Lookup }) {
  return (
    <Stack spacing={2}>
      {groupBy(bullets, (b) => b.role || 'Other').map(([role, items]) => (
        <div key={role}>
          <Typography variant="subtitle2" color="text.secondary">
            {role}
          </Typography>
          <Stack component="ul" spacing={1} sx={{ m: 0, pl: 2.5 }}>
            {items.map((bullet, i) => (
              <BulletItem key={i} bullet={bullet} lookup={lookup} />
            ))}
          </Stack>
        </div>
      ))}
    </Stack>
  )
}

export function Warnings({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null
  return (
    <Alert severity="warning">
      {warnings.length === 1 ? (
        warnings[0]
      ) : (
        <Stack component="ul" sx={{ m: 0, pl: 2 }}>
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </Stack>
      )}
    </Alert>
  )
}
