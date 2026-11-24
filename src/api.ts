import type { Application, ApplicationFields } from './applications'

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL?.trim() || '/api')
  .replace(/\/+$/, '')

export const sessionChangedEvent = 'interntrack-session-changed'

export interface Account {
  id: string
  name: string
  legacy_access: boolean
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

interface ImportResult {
  imported: number
  skipped: number
}

function readError(payload: unknown): string | undefined {
  if (typeof payload !== 'object' || !payload || !('detail' in payload)) return
  if (typeof payload.detail === 'string') return payload.detail
  if (Array.isArray(payload.detail)) {
    const first = payload.detail[0]
    if (typeof first?.msg === 'string') {
      const field = Array.isArray(first.loc) ? first.loc.at(-1) : undefined
      const message = first.msg.replace(/^Value error, /, '')
      return typeof field === 'string' && field !== 'body' ? `${field}: ${message}` : message
    }
  }
}

async function request<T>(path: string, options?: { method?: string; body?: unknown; signal?: AbortSignal }): Promise<T> {
  const body = options?.body
  const multipart = body instanceof FormData
  const headers = new Headers()
  if (body !== undefined && !multipart) headers.set('Content-Type', 'application/json')
  if (options?.method && options.method !== 'GET') headers.set('X-InternTrack-Request', '1')
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      method: options?.method,
      signal: options?.signal,
      headers,
      credentials: 'include',
      body: multipart ? body : JSON.stringify(body),
    })
  } catch (error) {
    if (options?.signal?.aborted) throw error
    throw new Error('Could not reach the API. Check that the backend is running and try again.', { cause: error })
  }

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    if (response.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event(sessionChangedEvent))
    }
    throw new ApiError(readError(payload) ?? `The API returned status ${response.status}. Try again.`, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export const authApi = {
  me: (signal: AbortSignal) => request<Account>('/auth/me', { signal }),
  login: (email: string, password: string) =>
    request<Account>('/auth/login', { method: 'POST', body: { email, password } }),
  register: (name: string, email: string, password: string) =>
    request<Account>('/auth/register', { method: 'POST', body: { name, email, password } }),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
}

export function extractResume(file: File, signal: AbortSignal) {
  const body = new FormData()
  body.append('file', file)
  return request<{ text: string }>('/resume/extract', { method: 'POST', body, signal })
}

export interface ResumeAnalysis {
  match_score: number
  overall_assessment: string
  matching_skills: string[]
  missing_skills: string[]
  strengths: string[]
  areas_for_improvement: string[]
  bullet_improvements: { source_text: string; suggested_text: string }[]
  recommendations: string[]
}

export function analyzeResume(resumeText: string, jobDescription: string, signal: AbortSignal) {
  return request<ResumeAnalysis>('/resume/analyze', {
    method: 'POST',
    body: { resume_text: resumeText, job_description: jobDescription },
    signal,
  })
}

export type CoverLetterTone = 'professional' | 'enthusiastic' | 'concise'

export function generateCoverLetter(
  resumeText: string, jobDescription: string, tone: CoverLetterTone, signal: AbortSignal,
) {
  return request<{ cover_letter: string }>('/cover-letter/generate', {
    method: 'POST',
    body: { resume_text: resumeText, job_description: jobDescription, tone },
    signal,
  })
}

export const applicationsApi = {
  list: (signal?: AbortSignal) => request<Application[]>('/applications', { signal }),
  create: (fields: ApplicationFields) =>
    request<Application>('/applications', { method: 'POST', body: fields }),
  update: (id: string, fields: ApplicationFields) =>
    request<Application>(`/applications/${encodeURIComponent(id)}`, { method: 'PUT', body: fields }),
  remove: (id: string) =>
    request<void>(`/applications/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  import: (applications: Application[]) =>
    request<ImportResult>('/applications/import', { method: 'POST', body: { applications } }),
}
