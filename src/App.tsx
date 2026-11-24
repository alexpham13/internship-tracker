import { BriefcaseBusiness, HardDrive, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ApiError, applicationsApi, authApi, sessionChangedEvent, type Account } from './api'
import { getLegacyApplications, markLegacyApplicationsImported, type Application, type ApplicationFields, type StatusFilter } from './applications'
import { ApplicationEditor, DeleteDialog } from './components/ApplicationDialogs'
import { ApplicationTable } from './components/ApplicationTable'
import { AuthPage } from './components/AuthPage'
import { ResumeAssistant } from './components/ResumeAssistant'
import { Sidebar, type Section } from './components/Sidebar'
import { Statistics } from './components/Statistics'

type DialogState =
  | { kind: 'add' }
  | { kind: 'edit' | 'delete'; application: Application }

const importKey = 'interntrack-imported:http://127.0.0.1:8000'
const sessionSignal = 'interntrack-session-signal'

type AuthState =
  | { kind: 'checking' | 'anonymous' }
  | { kind: 'signed-in'; account: Account }
  | { kind: 'error'; message: string }

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'An unexpected error occurred. Try again.'
}

function App() {
  const [auth, setAuth] = useState<AuthState>({ kind: 'checking' })
  const [check, setCheck] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    authApi.me(controller.signal)
      .then((account) => {
        if (!controller.signal.aborted) {
          if (window.location.pathname === '/login' || window.location.pathname === '/register') {
            window.history.replaceState(null, '', '/')
          }
          setAuth({ kind: 'signed-in', account })
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setAuth(error instanceof ApiError && error.status === 401
          ? { kind: 'anonymous' }
          : { kind: 'error', message: errorMessage(error) })
      })
    return () => controller.abort()
  }, [check])

  useEffect(() => {
    const sessionExpired = () => {
      window.history.replaceState(null, '', '/login')
      setAuth({ kind: 'anonymous' })
    }
    const sessionSwitched = (event: StorageEvent) => {
      if (event.key !== sessionSignal) return
      setAuth({ kind: 'checking' })
      setCheck((value) => value + 1)
    }
    window.addEventListener(sessionChangedEvent, sessionExpired)
    window.addEventListener('storage', sessionSwitched)
    return () => {
      window.removeEventListener(sessionChangedEvent, sessionExpired)
      window.removeEventListener('storage', sessionSwitched)
    }
  }, [])

  function signalOtherTabs() {
    try {
      localStorage.setItem(sessionSignal, crypto.randomUUID())
    } catch {
      // Sessions still work when browser storage is unavailable.
    }
  }

  function signedIn(account: Account) {
    window.history.replaceState(null, '', '/')
    setAuth({ kind: 'signed-in', account })
    signalOtherTabs()
  }

  function signedOut() {
    window.history.replaceState(null, '', '/login')
    setAuth({ kind: 'anonymous' })
    signalOtherTabs()
  }

  if (auth.kind === 'signed-in') {
    return <Workspace key={auth.account.id} account={auth.account} onSignOut={signedOut} />
  }
  if (auth.kind === 'anonymous') {
    return <AuthPage registering={window.location.pathname === '/register'} onSignIn={signedIn} />
  }
  return (
    <main className="auth-shell">
      <div className="info-panel">
        {auth.kind === 'checking' && <p role="status">Checking your session…</p>}
        {auth.kind === 'error' && <div>
          <p role="alert">{auth.message}</p>
          <button type="button" className="button button-secondary" onClick={() => {
            setAuth({ kind: 'checking' })
            setCheck((value) => value + 1)
          }}>Retry</button>
        </div>}
      </div>
    </main>
  )
}

function Workspace({ account, onSignOut }: { account: Account; onSignOut: () => void }) {
  const [signingOut, setSigningOut] = useState(false)
  const [signOutError, setSignOutError] = useState('')
  const [section, setSection] = useState<Section>('Dashboard')
  const [applications, setApplications] = useState<Application[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [dialog, setDialog] = useState<DialogState | null>(null)
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('All statuses')
  const [legacyApplications, setLegacyApplications] = useState(() => account.legacy_access ? getLegacyApplications(importKey) : [])
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState('')
  const [importMessage, setImportMessage] = useState('')
  const isTrackingView = section === 'Dashboard' || section === 'Applications'
  const canManage = !loading && !loadError && !importing

  useEffect(() => {
    const controller = new AbortController()
    applicationsApi.list(controller.signal)
      .then((records) => {
        if (!controller.signal.aborted) setApplications(records)
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setLoadError(errorMessage(error))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [loadAttempt])

  async function signOut() {
    if (signingOut) return
    setSigningOut(true)
    setSignOutError('')
    try {
      await authApi.logout()
      onSignOut()
    } catch (error) {
      setSignOutError(errorMessage(error))
    } finally {
      setSigningOut(false)
    }
  }

  function reloadApplications() {
    setLoading(true)
    setLoadError('')
    setLoadAttempt((value) => value + 1)
  }

  function showDialog(next: DialogState) {
    setActionError('')
    setDialog(next)
  }

  async function saveApplication(fields: ApplicationFields) {
    if (!dialog || saving) return
    setSaving(true)
    setActionError('')
    try {
      if (dialog.kind === 'edit') {
        const updated = await applicationsApi.update(dialog.application.id, fields)
        setApplications((current) => current.map((item) => item.id === updated.id ? updated : item))
      } else {
        const created = await applicationsApi.create(fields)
        setApplications((current) => [created, ...current])
        setSearch('')
        setStatus('All statuses')
      }
      setDialog(null)
    } catch (error) {
      setActionError(errorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  async function deleteApplication() {
    if (dialog?.kind !== 'delete' || saving) return
    setSaving(true)
    setActionError('')
    const id = dialog.application.id
    try {
      await applicationsApi.remove(id)
      setApplications((current) => current.filter((item) => item.id !== id))
      setDialog(null)
    } catch (error) {
      setActionError(errorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  async function importApplications() {
    if (importing || !legacyApplications.length) return
    setImporting(true)
    setImportError('')
    try {
      const { imported, skipped } = await applicationsApi.import(legacyApplications)
      markLegacyApplicationsImported(importKey)
      setLegacyApplications([])
      setImportMessage(`Imported ${imported} of ${imported + skipped} browser records. ${skipped} skipped because their IDs were already recorded.`)
      reloadApplications()
    } catch (error) {
      setImportError(errorMessage(error))
    } finally {
      setImporting(false)
    }
  }

  const openAdd = () => showDialog({ kind: 'add' })
  const closeDialog = () => { if (!saving) setDialog(null) }

  return (
    <div className="app-shell">
      <Sidebar section={section} onNavigate={setSection} accountName={account.name}
        signingOut={signingOut} onSignOut={() => void signOut()} />
      <div className="main-shell">
        <header className="topbar">
          <div><BriefcaseBusiness size={17} /> <span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{section}</strong></div>
          <span className="topbar-storage" data-error={!!loadError}><span />
            {loading ? 'Connecting…' : loadError ? 'API unavailable' : 'Database connected'}
          </span>
        </header>
        <main className="workspace">
          {signOutError && <p className="storage-alert" role="alert">{signOutError}</p>}
          <header className="page-heading">
            <div>
              <h1>{section}</h1>
              {isTrackingView && <p>{section === 'Dashboard'
                ? 'An overview of your internship search and application progress.'
                : 'Manage every internship you’ve applied to.'}</p>}
              {section === 'AI Assistant' && <p>Prepare your resume and the job description in one place.</p>}
            </div>
            {isTrackingView && <button type="button" className="button button-primary" onClick={openAdd} disabled={!canManage}>
              <Plus size={19} /> Add Application
            </button>}
          </header>
          {isTrackingView && legacyApplications.length > 0 && (
            <div className="info-panel import-panel">
              <HardDrive size={22} /><div>
                <h2>Browser records available</h2>
                <p>Import your previously saved applications into the local database from Settings.</p>
                <button type="button" className="button button-secondary" onClick={() => setSection('Settings')}>Open Settings</button>
              </div>
            </div>
          )}
          {isTrackingView && (loading || importing) && (
            <p role="status" className="info-panel">{importing ? 'Importing applications…' : 'Loading applications…'}</p>
          )}
          {isTrackingView && loadError && !importing && (
            <div className="info-panel import-panel">
              <div>
                <p role="alert">{loadError}</p>
                <button type="button" className="button button-secondary" onClick={reloadApplications}>Retry</button>
              </div>
            </div>
          )}
          {section === 'Dashboard' && canManage && <Statistics applications={applications} />}
          {isTrackingView && canManage && <ApplicationTable applications={applications} onAdd={openAdd}
            onEdit={(application) => showDialog({ kind: 'edit', application })}
            onDelete={(application) => showDialog({ kind: 'delete', application })}
            search={search} onSearch={setSearch} status={status} onStatus={setStatus} />}
          {section === 'AI Assistant' && <ResumeAssistant />}
          {section === 'Settings' && (
            <section className="info-panel import-panel"><HardDrive size={22} /><div>
              <h2>Application storage</h2><p>Your applications are saved in the workspace database.</p>
              {legacyApplications.length > 0 && <>
                <p>{legacyApplications.length} {legacyApplications.length === 1 ? 'application is' : 'applications are'} available to import from this browser.</p>
                <button type="button" className="button button-secondary" onClick={importApplications} disabled={importing || loading}>
                  {importing ? 'Importing…' : 'Import browser applications'}
                </button>
              </>}
              {importError && <p role="alert" className="storage-alert">{importError}</p>}
              {importMessage && <p role="status">{importMessage}</p>}
            </div></section>
          )}
        </main>
      </div>
      {dialog?.kind === 'delete' && <DeleteDialog application={dialog.application} onClose={closeDialog} onConfirm={deleteApplication}
        busy={saving} error={actionError} />}
      {(dialog?.kind === 'add' || dialog?.kind === 'edit') && <ApplicationEditor
        application={dialog.kind === 'edit' ? dialog.application : undefined}
        onClose={closeDialog} onSave={saveApplication} busy={saving} error={actionError} />}
    </div>
  )
}

export default App
