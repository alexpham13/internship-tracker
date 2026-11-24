import { BriefcaseBusiness, HardDrive, LayoutGrid, LogOut, Settings, Sparkles } from 'lucide-react'

const sections = [
  { label: 'Dashboard', icon: LayoutGrid },
  { label: 'Applications', icon: BriefcaseBusiness },
  { label: 'AI Assistant', icon: Sparkles },
  { label: 'Settings', icon: Settings },
] as const

export type Section = (typeof sections)[number]['label']

interface SidebarProps {
  section: Section
  onNavigate: (section: Section) => void
  accountName: string
  signingOut: boolean
  onSignOut: () => void
}

export function Sidebar({ section, onNavigate, accountName, signingOut, onSignOut }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-icon"><BriefcaseBusiness size={21} /></span>
        <div>
          <div className="brand-name">InternTrack <span>AI</span></div>
          <p>Internship tracker</p>
        </div>
      </div>
      <div className="sidebar-account">
        <span title={accountName}>{accountName}</span>
        <button type="button" className="button button-secondary" disabled={signingOut} onClick={onSignOut}>
          <LogOut size={15} aria-hidden="true" /> {signingOut ? 'Signing out…' : 'Sign out'}
        </button>
      </div>
      <nav aria-label="Workspace" className="navigation">
        <p className="nav-label">Workspace</p>
        {sections.map(({ label, icon: Icon }) => (
          <button key={label} type="button" aria-current={section === label ? 'page' : undefined}
            onClick={() => onNavigate(label)}>
            <Icon size={18} /><span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">
        <span className="storage-icon"><HardDrive size={17} /></span>
        <div><strong>Workspace storage</strong><p>Saved to database</p></div>
      </div>
    </aside>
  )
}
