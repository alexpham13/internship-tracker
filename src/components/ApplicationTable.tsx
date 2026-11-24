import { BriefcaseBusiness, ChevronDown, FileText, Funnel, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { statuses, type Application, type StatusFilter } from '../applications'

interface ApplicationTableProps {
  applications: Application[]
  onAdd: () => void
  onEdit: (application: Application) => void
  onDelete: (application: Application) => void
  search: string
  onSearch: (search: string) => void
  status: StatusFilter
  onStatus: (status: StatusFilter) => void
}

const dateFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC',
})

export function ApplicationTable({
  applications, onAdd, onEdit, onDelete, search, onSearch, status, onStatus,
}: ApplicationTableProps) {
  const query = search.trim().toLowerCase()
  const filtered = applications.filter((application) =>
    (status === 'All statuses' || application.status === status) &&
    [application.company, application.position, application.location].some((field) =>
      field.toLowerCase().includes(query),
    ),
  ).sort((a, b) => b.dateApplied.localeCompare(a.dateApplied))
  const isEmpty = applications.length === 0

  return (
    <section className="table-panel" aria-labelledby="application-heading">
      <header className="table-intro">
        <div className="flex items-center gap-2.5">
          <h2 id="application-heading">Your applications</h2>
          <span className="count-badge">{applications.length}</span>
        </div>
        <p>Search, filter, and update your internship applications.</p>
      </header>
      <div className="table-tools">
        <label className="control search-control">
          <Search size={17} aria-hidden="true" />
          <input type="search" aria-label="Search applications" placeholder="Search applications…"
            value={search} onChange={(event) => onSearch(event.target.value)} />
        </label>
        <label className="control select-control">
          <Funnel size={16} aria-hidden="true" />
          <select aria-label="Filter by status" value={status}
            onChange={(event) => onStatus(event.target.value as StatusFilter)}>
            <option>All statuses</option>
            {statuses.map((value) => <option key={value}>{value}</option>)}
          </select>
          <ChevronDown size={16} aria-hidden="true" />
        </label>
      </div>
      <div className="table-scroll" role="region" aria-label="Application records" tabIndex={filtered.length ? 0 : undefined}>
        <table>
          <thead><tr>
            {['Company', 'Position', 'Location', 'Date Applied', 'Status', 'Actions'].map((header) =>
              <th key={header} scope="col">{header}</th>,
            )}
          </tr></thead>
          <tbody>
            {filtered.map((application) => (
              <tr key={application.id}>
                <th scope="row"><span className="company-cell">
                  <span className="company-icon"><BriefcaseBusiness size={16} /></span>{application.company}
                </span></th>
                <td>{application.position}</td>
                <td>{application.location}</td>
                <td className="whitespace-nowrap">
                  {dateFormatter.format(new Date(application.dateApplied))}
                </td>
                <td><span className={`status-badge status-${application.status.toLowerCase()}`}>
                  {application.status}
                </span></td>
                <td><div className="row-actions">
                  <button type="button" className="icon-button" aria-label={`Edit ${application.company} application`}
                    title="Edit application" onClick={() => onEdit(application)}><Pencil size={16} /></button>
                  <button type="button" className="icon-button delete-action" aria-label={`Delete ${application.company} application`}
                    title="Delete application" onClick={() => onDelete(application)}><Trash2 size={16} /></button>
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon" aria-hidden="true">
            {isEmpty ? <FileText size={27} strokeWidth={1.65} /> : <Search size={25} />}
          </div>
          <h3>{isEmpty ? 'No applications yet' : 'No matching applications'}</h3>
          <p>{isEmpty ? 'Add your first internship application to start tracking your progress.'
            : 'Try a different search or clear your filters.'}</p>
          {isEmpty ? (
            <button type="button" className="button button-secondary" onClick={onAdd}><Plus size={17} /> Add Application</button>
          ) : (
            <button type="button" className="button button-secondary" onClick={() => { onSearch(''); onStatus('All statuses') }}>
              Clear filters
            </button>
          )}
        </div>
      )}
      <footer className="table-footer" aria-live="polite">
        Showing {filtered.length} of {applications.length} {applications.length === 1 ? 'application' : 'applications'}
      </footer>
    </section>
  )
}
