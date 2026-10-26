import type { Coverage, Evidence, Requirement } from '../api/types'

/** What requirement and evidence ids refer to, for tooltips. Only known while reviewing. */
export interface Lookup {
  requirements: Map<string, Requirement>
  evidence: Map<string, Evidence>
}

export function lookupFrom(requirements: Requirement[] = [], evidence: Evidence[] = []): Lookup {
  return {
    requirements: new Map(requirements.map((r) => [r.id, r])),
    evidence: new Map(evidence.map((e) => [e.id, e])),
  }
}

export const COVERAGE_COLOR: Record<Coverage, 'success' | 'warning' | 'error'> = {
  strong: 'success',
  partial: 'warning',
  missing: 'error',
}
