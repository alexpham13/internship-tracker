import { BriefcaseBusiness, HardDrive, Plus, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { readApplications, storageKey, type Application, type ApplicationFields, type StatusFilter } from './applications'
import { ApplicationEditor, DeleteDialog } from './components/ApplicationDialogs'
import { ApplicationTable } from './components/ApplicationTable'
import { Sidebar, type Section } from './components/Sidebar'
import { Statistics } from './components/Statistics'

type DialogState =
  | { kind: 'add' }
  | { kind: 'edit' | 'delete'; application: Application }

function App() {
  const [section, setSection] = useState<Section>('Dashboard')
  const [applications, setApplications] = useState(readApplications)
  const [dialog, setDialog] = useState<DialogState | null>(null)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('All statuses')
  const [storageError, setStorageError] = useState(false)
  const isTrackingView = section === 'Dashboard' || section === 'Applications'

  function updateApplications(next: Application[]) {
    setApplications(next)
    try {
      localStorage.setItem(storageKey, JSON.stringify(next))
      setStorageError(false)
    } catch {
      setStorageError(true)
    }
  }

  function saveApplication(fields: ApplicationFields) {
    if (dialog?.kind === 'edit') {
      const id = dialog.application.id
      updateApplications(applications.map((item) => item.id === id ? { ...fields, id } : item))
    } else {
      const application = { ...fields, id: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}` }
      updateApplications([application, ...applications])
      setSearch('')
      setStatus('All statuses')
    }
    setDialog(null)
  }

  function deleteApplication() {
    if (dialog?.kind !== 'delete') return
    const id = dialog.application.id
    updateApplications(applications.filter((item) => item.id !== id))
    setDialog(null)
  }

  const openAdd = () => setDialog({ kind: 'add' })
  const closeDialog = () => setDialog(null)

  return (
    <div className="app-shell">
      <Sidebar section={section} onNavigate={setSection} />
      <div className="main-shell">
        <header className="topbar">
          <div><BriefcaseBusiness size={17} /> <span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{section}</strong></div>
          <span className="topbar-storage" data-error={storageError}><span /> {storageError ? 'Storage unavailable' : 'Local storage'}</span>
        </header>
        <main className="workspace">
          <header className="page-heading">
            <div>
              <h1>{section}</h1>
              {isTrackingView && <p>{section === 'Dashboard'
                ? 'An overview of your internship search and application progress.'
                : 'Manage every internship you’ve applied to.'}</p>}
            </div>
            {isTrackingView && <button type="button" className="button button-primary" onClick={openAdd}>
              <Plus size={19} /> Add Application
            </button>}
          </header>
          {storageError && <p role="alert" className="storage-alert">Changes could not be saved. Check your browser’s storage settings before refreshing.</p>}
          {section === 'Dashboard' && <Statistics applications={applications} />}
          {isTrackingView && <ApplicationTable applications={applications} onAdd={openAdd}
            onEdit={(application) => setDialog({ kind: 'edit', application })}
            onDelete={(application) => setDialog({ kind: 'delete', application })}
            search={search} onSearch={setSearch} status={status} onStatus={setStatus} />}
          {section === 'AI Assistant' && (
            <section className="info-panel"><Sparkles size={22} /><div>
              <h2>AI Assistant is coming later</h2><p>You can manage your internship search from Applications.</p>
            </div></section>
          )}
          {section === 'Settings' && (
            <section className="info-panel"><HardDrive size={22} /><div>
              <h2>Application storage</h2><p>Your applications are saved in this browser. Clearing site data removes your records.</p>
            </div></section>
          )}
        </main>
      </div>
      {dialog?.kind === 'delete' && <DeleteDialog application={dialog.application} onClose={closeDialog} onConfirm={deleteApplication} />}
      {(dialog?.kind === 'add' || dialog?.kind === 'edit') && <ApplicationEditor
        application={dialog.kind === 'edit' ? dialog.application : undefined}
        onClose={closeDialog} onSave={saveApplication} />}
    </div>
  )
}

export default App
