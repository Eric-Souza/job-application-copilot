import Chip from '@mui/material/Chip'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import type { Match, Search } from '../api/types'
import { COVERAGE_COLOR, type Lookup } from './shared'

interface Props {
  matches: Match[]
  lookup: Lookup
  searches?: Search[]
}

/** Each requirement, how well your evidence covers it, why, and what the agent searched for again. */
export function CoverageTable({ matches, lookup, searches = [] }: Props) {
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
          const queries = searches.filter((s) => s.requirement_id === m.requirement_id).map((s) => s.query)
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
                {queries.length > 0 && (
                  <Typography variant="caption" color="text.secondary" component="div">
                    Also searched for: {queries.map((q) => `“${q}”`).join(', ')}
                  </Typography>
                )}
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
