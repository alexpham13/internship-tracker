import { BriefcaseBusiness, CalendarDays, Mail, Trophy } from 'lucide-react'
import { getStatistics, type Application } from '../applications'

export function Statistics({ applications }: { applications: Application[] }) {
  const { total, responses, interviews, offers } = getStatistics(applications)
  const cards = [
    { label: 'Total Applications', value: total, description: 'Applications tracked', icon: BriefcaseBusiness, tone: 'blue' },
    { label: 'Responses', value: responses, description: 'Employers heard from', icon: Mail, tone: 'violet' },
    { label: 'Interviews', value: interviews, description: 'In the interview stage', icon: CalendarDays, tone: 'amber' },
    { label: 'Offers', value: offers, description: 'Offers received', icon: Trophy, tone: 'green' },
  ]

  return (
    <section aria-label="Application statistics" className="stats-grid">
      {cards.map(({ label, value, description, icon: Icon, tone }) => (
        <article className="stat-card" key={label}>
          <div className="flex items-center gap-3">
            <span className={`stat-icon tone-${tone}`}><Icon size={19} /></span>
            <h2>{label}</h2>
          </div>
          <p className="stat-value">{value}</p>
          <p className="stat-description">{description}</p>
        </article>
      ))}
    </section>
  )
}
