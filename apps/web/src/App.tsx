import Add from '@mui/icons-material/Add'
import AppBar from '@mui/material/AppBar'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import type { RunSummary } from './api/types'
import { NewRun } from './components/NewRun'
import { RunList } from './components/RunList'
import { RunPage } from './components/RunPage'
import { useHashRoute } from './useHashRoute'

export default function App() {
  const [path, navigate] = useHashRoute()
  const runId = path.match(/^\/runs\/([\w-]+)$/)?.[1] ?? null
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [listError, setListError] = useState<string | null>(null)

  const refreshRuns = useCallback(() => {
    api.listRuns().then(
      (list) => {
        setRuns(list)
        setListError(null)
      },
      (e: Error) => setListError(e.message),
    )
  }, [])

  useEffect(refreshRuns, [refreshRuns])

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <AppBar position="static" elevation={0}>
        <Toolbar variant="dense">
          <Typography variant="h6" component="h1">
            Job Application Copilot
          </Typography>
        </Toolbar>
      </AppBar>
      <Box sx={{ flex: 1, display: 'grid', gridTemplateColumns: { xs: '1fr', md: '300px 1fr' } }}>
        <Paper square component="nav" sx={{ borderWidth: '0 1px 0 0', p: 1 }}>
          <Button
            fullWidth
            variant="outlined"
            startIcon={<Add />}
            onClick={() => navigate('/')}
            sx={{ mb: 1 }}
          >
            New run
          </Button>
          <RunList
            runs={runs}
            error={listError}
            selected={runId}
            onSelect={(id) => navigate(`/runs/${id}`)}
          />
        </Paper>
        <Box component="main" sx={{ p: 3, maxWidth: 1100, width: '100%' }}>
          {runId ? (
            <RunPage key={runId} runId={runId} onChange={refreshRuns} />
          ) : (
            <NewRun
              onStarted={(id) => {
                refreshRuns()
                navigate(`/runs/${id}`)
              }}
            />
          )}
        </Box>
      </Box>
    </Box>
  )
}
