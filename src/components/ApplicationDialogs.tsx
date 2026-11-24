import { X } from 'lucide-react'
import { useEffect, useId, useRef, type FormEvent, type ReactNode } from 'react'
import { statuses, today, type Application, type ApplicationFields, type ApplicationStatus } from '../applications'

interface DialogProps {
  title: string
  description: string
  onClose: () => void
  busy: boolean
  error: string
  children: ReactNode
}

function Dialog({ title, description, onClose, busy, error, children }: DialogProps) {
  const dialog = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    const element = dialog.current
    const trigger = document.activeElement
    element?.showModal()
    return () => {
      element?.close()
      if (trigger instanceof HTMLElement) trigger.focus()
    }
  }, [])

  return (
    <dialog ref={dialog} className="dialog" aria-labelledby={titleId} aria-describedby={descriptionId}
      onCancel={(event) => { event.preventDefault(); onClose() }}>
      <header className="dialog-header">
        <div><h2 id={titleId}>{title}</h2><p id={descriptionId}>{description}</p></div>
        <button type="button" className="icon-button" aria-label="Close dialog" onClick={onClose} disabled={busy}><X size={20} /></button>
      </header>
      {error && <p role="alert" className="storage-alert">{error}</p>}
      {children}
    </dialog>
  )
}

interface ApplicationEditorProps {
  application?: Application
  onClose: () => void
  onSave: (fields: ApplicationFields) => Promise<void>
  busy: boolean
  error: string
}

export function ApplicationEditor({ application, onClose, onSave, busy, error }: ApplicationEditorProps) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const fields = new FormData(event.currentTarget)
    onSave({
      company: String(fields.get('company')).trim(),
      position: String(fields.get('position')).trim(),
      location: String(fields.get('location')).trim(),
      dateApplied: String(fields.get('dateApplied')),
      status: fields.get('status') as ApplicationStatus,
    })
  }

  return (
    <Dialog title={application ? 'Edit application' : 'Add application'}
      description="Enter the details for this internship." onClose={onClose} busy={busy} error={error}>
      <form onSubmit={submit}>
        <fieldset className="form-fields" disabled={busy}>
          <label>Company<input name="company" placeholder="e.g. Acme" defaultValue={application?.company} required pattern=".*\S.*" autoFocus /></label>
          <label>Position<input name="position" placeholder="e.g. Software Engineering Intern" defaultValue={application?.position} required pattern=".*\S.*" /></label>
          <label>Location<input name="location" placeholder="e.g. Chicago, IL or Remote" defaultValue={application?.location} required pattern=".*\S.*" /></label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label>Date applied<input type="date" name="dateApplied" defaultValue={application?.dateApplied ?? today()} min="0001-01-01" max="9999-12-31" required /></label>
            <label>Status<select name="status" defaultValue={application?.status ?? 'Applied'}>
              {statuses.map((value) => <option key={value}>{value}</option>)}
            </select></label>
          </div>
        </fieldset>
        <footer className="dialog-actions">
          <button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="button button-primary" disabled={busy}>
            {busy ? 'Saving…' : application ? 'Save changes' : 'Add Application'}
          </button>
        </footer>
      </form>
    </Dialog>
  )
}

interface DeleteDialogProps {
  application: Application
  onClose: () => void
  onConfirm: () => Promise<void>
  busy: boolean
  error: string
}

export function DeleteDialog({ application, onClose, onConfirm, busy, error }: DeleteDialogProps) {
  return (
    <Dialog title="Delete application?" description={`Remove your application for ${application.position} at ${application.company}.`}
      onClose={onClose} busy={busy} error={error}>
      <footer className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose} disabled={busy} autoFocus>Cancel</button>
        <button type="button" className="button button-danger" onClick={onConfirm} disabled={busy}>
          {busy ? 'Deleting…' : 'Delete application'}
        </button>
      </footer>
    </Dialog>
  )
}
