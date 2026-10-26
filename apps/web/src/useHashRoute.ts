import { useCallback, useEffect, useState } from 'react'

const current = () => window.location.hash.slice(1) || '/'

/** The path after the "#", so links survive a reload without any server routing. */
export function useHashRoute(): [string, (path: string) => void] {
  const [path, setPath] = useState(current)

  useEffect(() => {
    const update = () => setPath(current())
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])

  const navigate = useCallback((to: string) => {
    window.location.hash = to
  }, [])

  return [path, navigate]
}
