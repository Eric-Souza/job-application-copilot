import ContentCopy from '@mui/icons-material/ContentCopy'
import Download from '@mui/icons-material/Download'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Typography from '@mui/material/Typography'
import { useState } from 'react'
import type { Coverage, TailoredResume } from '../api/types'
import { fileName } from '../format'
import { BulletGroups, Warnings } from './Bullets'
import { COVERAGE_COLOR } from './shared'

export function ResultView({ result }: { result: TailoredResume }) {
  const [tab, setTab] = useState<'formatted' | 'markdown'>('formatted')
  const [copied, setCopied] = useState(false)

  async function copy() {
    await navigator.clipboard.writeText(result.markdown)
    setCopied(true)
  }

  function download() {
    const url = URL.createObjectURL(new Blob([result.markdown], { type: 'text/markdown' }))
    const link = Object.assign(document.createElement('a'), {
      href: url,
      download: fileName(result.title, result.company),
    })
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Paper sx={{ p: 3 }}>
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', rowGap: 1 }}>
          <Typography variant="h6" sx={{ mr: 1 }}>
            Tailored resume
          </Typography>
          {(Object.entries(result.coverage) as [Coverage, number][]).map(([coverage, n]) => (
            <Chip
              key={coverage}
              size="small"
              variant="outlined"
              color={COVERAGE_COLOR[coverage]}
              label={`${n} ${coverage}`}
            />
          ))}
          <Box sx={{ flexGrow: 1 }} />
          <Button startIcon={<ContentCopy />} onClick={copy}>
            {copied ? 'Copied' : 'Copy Markdown'}
          </Button>
          <Button startIcon={<Download />} onClick={download}>
            Download
          </Button>
        </Stack>
        {result.gaps.length > 0 && (
          <Alert severity="info">
            No evidence for these must-haves: {result.gaps.join('; ')}. Worth addressing in a cover letter, or
            add the experience to your resume folder if you have it.
          </Alert>
        )}
        <Warnings warnings={result.warnings} />
        <Tabs value={tab} onChange={(_, value) => setTab(value)}>
          <Tab value="formatted" label="Formatted" />
          <Tab value="markdown" label="Markdown" />
        </Tabs>
        {tab === 'formatted' ? (
          <Stack spacing={2}>
            <Typography>{result.summary}</Typography>
            <BulletGroups bullets={result.bullets} />
          </Stack>
        ) : (
          <Box
            component="pre"
            sx={{
              m: 0,
              p: 2,
              bgcolor: 'grey.100',
              borderRadius: 1,
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              fontSize: 13,
            }}
          >
            {result.markdown}
          </Box>
        )}
      </Stack>
    </Paper>
  )
}
