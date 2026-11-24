import { Check, Copy } from 'lucide-react'
import { useState, type CSSProperties } from 'react'
import type { ResumeAnalysis } from '../api'

function SkillGroup({ title, skills, missing = false }: { title: string; skills: string[]; missing?: boolean }) {
  return (
    <div>
      <h3>{title}</h3>
      {skills.length ? (
        <ul className="analysis-tags" aria-label={title}>
          {skills.map((skill) => <li key={skill} className={missing ? 'tone-amber' : 'tone-green'}>{skill}</li>)}
        </ul>
      ) : <p className="analysis-empty">None identified.</p>}
    </div>
  )
}

function Findings({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h3>{title}</h3>
      {items.length ? (
        <ul className="analysis-findings">
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : <p className="analysis-empty">None identified.</p>}
    </div>
  )
}

export function ResumeAnalysisResults({ analysis }: { analysis: ResumeAnalysis }) {
  const [clipboard, setClipboard] = useState<{ index: number; success: boolean } | null>(null)

  async function copyBullet(text: string, index: number) {
    try {
      await navigator.clipboard.writeText(text)
      setClipboard({ index, success: true })
    } catch {
      setClipboard({ index, success: false })
    }
  }

  return (
    <section className="table-panel analysis-results" aria-labelledby="analysis-heading">
      <header className="table-intro">
        <h2 id="analysis-heading">Resume analysis</h2>
      </header>
      <div className="analysis-summary">
        <div className="analysis-score">
          <div className="analysis-score-ring" role="meter" aria-label="Estimated resume match"
            aria-valuenow={analysis.match_score} aria-valuemin={0} aria-valuemax={100}
            style={{ '--match-score': `${analysis.match_score}%` } as CSSProperties}>
            <span>{analysis.match_score}<small>/100</small></span>
          </div>
          <h3>Resume match</h3>
          <p>AI-generated estimate. No ATS was used.</p>
        </div>
        <div>
          <h3>Overall assessment</h3>
          <p>{analysis.overall_assessment}</p>
        </div>
      </div>
      <div className="analysis-result-row">
        <SkillGroup title="Matching skills" skills={analysis.matching_skills} />
        <SkillGroup title="Missing skills" skills={analysis.missing_skills} missing />
      </div>
      <div className="analysis-result-row">
        <Findings title="Candidate strengths" items={analysis.strengths} />
        <Findings title="Areas for improvement" items={analysis.areas_for_improvement} />
      </div>
      <div className="analysis-result-row">
        <div>
          <h3>Suggested resume bullets</h3>
          {analysis.bullet_improvements.length ? (
            <>
              <p className="analysis-empty">Check each rewrite against your experience before using it.</p>
              <ul className="analysis-bullets">
                {analysis.bullet_improvements.map((bullet, index) => (
                  <li key={index}>
                    <p>{bullet.suggested_text}</p>
                    <details>
                      <summary>View resume excerpt</summary>
                      <p>{bullet.source_text}</p>
                    </details>
                    <button type="button" className="button button-secondary"
                      aria-label={`Copy suggested bullet ${index + 1}`}
                      onClick={() => void copyBullet(bullet.suggested_text, index)}>
                      {clipboard?.index === index && clipboard.success
                        ? <><Check size={15} aria-hidden="true" /> Copied</>
                        : <><Copy size={15} aria-hidden="true" /> Copy</>}
                    </button>
                  </li>
                ))}
              </ul>
              <p role="status" className={clipboard?.success ? 'sr-only' : 'analysis-empty'}>
                {clipboard?.success ? 'Bullet copied to clipboard.' : clipboard && 'Clipboard unavailable. Select the bullet text to copy it manually.'}
              </p>
            </>
          ) : <p className="analysis-empty">No rewrites based on resume excerpts were available.</p>}
        </div>
        <Findings title="Recommendations" items={analysis.recommendations} />
      </div>
    </section>
  )
}
