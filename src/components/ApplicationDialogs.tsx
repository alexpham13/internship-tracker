import { X } from 'lucide-react'
import { useEffect, useId, useRef, type FormEvent, type ReactNode } from 'react'
import { statuses, today, type Application, type ApplicationFields, type ApplicationStatus } from '../applications'

interface DialogProps {
  title: string
  description: string
  onClose: () => void
  children: ReactNode
}

function Dialog({ title, description, onClose, children }: DialogProps) {
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
        <button type="button" className="icon-button" aria-label="Close dialog" onClick={onClose}><X size={20} /></button>
      </header>
      {children}
    </dialog>
  )
}

interface ApplicationEditorProps {
  application?: Application
  onClose: () => void
  onSave: (fields: ApplicationFields) => void
}

export function ApplicationEditor({ application, onClose, onSave }: ApplicationEditorProps) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
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
      description="Enter the details for this internship." onClose={onClose}>
      <form onSubmit={submit}>
        <div className="form-fields">
          <label>Company<input name="company" placeholder="e.g. Acme" defaultValue={application?.company} required pattern=".*\S.*" autoFocus /></label>
          <label>Position<input name="position" placeholder="e.g. Software Engineering Intern" defaultValue={application?.position} required pattern=".*\S.*" /></label>
          <label>Location<input name="location" placeholder="e.g. Chicago, IL or Remote" defaultValue={application?.location} required pattern=".*\S.*" /></label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label>Date applied<input type="date" name="dateApplied" defaultValue={application?.dateApplied ?? today()} min="0001-01-01" max="9999-12-31" required /></label>
            <label>Status<select name="status" defaultValue={application?.status ?? 'Applied'}>
              {statuses.map((value) => <option key={value}>{value}</option>)}
            </select></label>
          </div>
        </div>
        <footer className="dialog-actions">
          <button type="button" className="button button-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="button button-primary">{application ? 'Save changes' : 'Add Application'}</button>
        </footer>
      </form>
    </Dialog>
  )
}

interface DeleteDialogProps {
  application: Application
  onClose: () => void
  onConfirm: () => void
}

export function DeleteDialog({ application, onClose, onConfirm }: DeleteDialogProps) {
  return (
    <Dialog title="Delete application?" description={`Remove your application for ${application.position} at ${application.company}.`}
      onClose={onClose}>
      <footer className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose} autoFocus>Cancel</button>
        <button type="button" className="button button-danger" onClick={onConfirm}>Delete application</button>
      </footer>
    </Dialog>
  )
}
