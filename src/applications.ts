export const statuses = ['Applied', 'Responded', 'Interview', 'Offer', 'Rejected'] as const

export type ApplicationStatus = (typeof statuses)[number]
export type StatusFilter = ApplicationStatus | 'All statuses'

export interface ApplicationFields {
  company: string
  position: string
  location: string
  dateApplied: string
  status: ApplicationStatus
}

export interface Application extends ApplicationFields {
  id: string
}

const storageKey = 'interntrack-applications'

function isApplication(value: unknown): value is Application {
  if (typeof value !== 'object' || value === null) return false
  const item = value as Record<string, unknown>
  return typeof item.id === 'string' && typeof item.company === 'string' &&
    typeof item.position === 'string' && typeof item.location === 'string' &&
    typeof item.dateApplied === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(item.dateApplied) &&
    statuses.some((status) => status === item.status)
}

export function getLegacyApplications(importKey: string): Application[] {
  if (hasImportedApplications(importKey)) return []
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(storageKey) ?? '[]')
    return Array.isArray(saved) ? saved.filter(isApplication) : []
  } catch {
    return []
  }
}

function hasImportedApplications(importKey: string) {
  try {
    return localStorage.getItem(importKey) === 'true'
  } catch {
    return false
  }
}

export function markLegacyApplicationsImported(importKey: string) {
  try {
    localStorage.setItem(importKey, 'true')
  } catch {
    // The server records imported IDs, so retrying is still safe.
  }
}

export function today() {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

export function getStatistics(applications: Application[]) {
  return {
    total: applications.length,
    responses: applications.filter(({ status }) => status !== 'Applied').length,
    interviews: applications.filter(({ status }) => status === 'Interview').length,
    offers: applications.filter(({ status }) => status === 'Offer').length,
  }
}
