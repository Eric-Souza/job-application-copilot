import { createTheme } from '@mui/material/styles'

export const theme = createTheme({
  palette: {
    primary: { main: '#3949ab' },
    background: { default: '#f5f6fa' },
  },
  shape: { borderRadius: 8 },
  typography: {
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { textTransform: 'none' } },
    },
    MuiTab: { styleOverrides: { root: { textTransform: 'none' } } },
    MuiPaper: { defaultProps: { variant: 'outlined' } },
  },
})
