import type { Application, ApplicationFields } from './applications'

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:8000')
  .replace(/\/+$/, '')

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
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      method: options?.method,
      signal: options?.signal,
      headers: options?.body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: options?.body === undefined ? undefined : JSON.stringify(options.body),
    })
  } catch (error) {
    if (options?.signal?.aborted) throw error
    throw new Error('Could not reach the API. Check that the backend is running and try again.', { cause: error })
  }

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    throw new Error(readError(payload) ?? `The API returned status ${response.status}. Try again.`)
  }
  if (response.status === 204) return undefined as T
  return response.json()
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
