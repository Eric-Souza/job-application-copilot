import Chip from '@mui/material/Chip'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import type { Match } from '../api/types'
import { COVERAGE_COLOR, type Lookup } from './shared'

/** Each requirement, how well your evidence covers it, and why. */
export function CoverageTable({ matches, lookup }: { matches: Match[]; lookup: Lookup }) {
  return (
    <Table size="small" aria-label="Requirement coverage">
      <TableHead>
        <TableRow>
          <TableCell>Requirement</TableCell>
          <TableCell>Coverage</TableCell>
          <TableCell>Evidence</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {matches.map((m) => {
          const requirement = lookup.requirements.get(m.requirement_id)
          return (
            <TableRow key={m.requirement_id}>
              <TableCell>
                <Typography variant="body2">
                  {requirement?.text ?? m.requirement_id}
                  {requirement?.kind === 'nice' && (
                    <Typography component="span" variant="caption" color="text.secondary">
                      {' '}
                      (nice to have)
                    </Typography>
                  )}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {m.rationale}
                </Typography>
              </TableCell>
              <TableCell>
                <Chip size="small" label={m.coverage} color={COVERAGE_COLOR[m.coverage]} variant="outlined" />
              </TableCell>
              <TableCell>
                <Typography variant="body2">{m.evidence_ids.join(', ') || '—'}</Typography>
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
