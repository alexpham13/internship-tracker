import { Copy, Download, FileText, FileUp, LoaderCircle, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import {
  analyzeResume, extractResume, generateCoverLetter, type CoverLetterTone, type ResumeAnalysis,
} from '../api'
import { ResumeAnalysisResults } from './ResumeAnalysisResults'

const maxResumeSize = 5 * 1024 * 1024
const maxAnalysisLength = 30_000

export function ResumeAssistant() {
  const input = useRef<HTMLInputElement>(null)
  const upload = useRef<AbortController | null>(null)
  const pendingAnalysis = useRef<AbortController | null>(null)
  const pendingLetter = useRef<AbortController | null>(null)
  const [tone, setTone] = useState<CoverLetterTone>('professional')
  const [letter, setLetter] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [letterError, setLetterError] = useState('')
  const [exportFeedback, setExportFeedback] = useState('')
  const [exportError, setExportError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [filename, setFilename] = useState('')
  const [resume, setResume] = useState('')
  const [jobDescription, setJobDescription] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const [analysis, setAnalysis] = useState<ResumeAnalysis | null>(null)
  const resumeText = resume.trim()
  const jobText = jobDescription.trim()
  const exceedsLimit = [resumeText, jobText].some((value) => Array.from(value).length > maxAnalysisLength)
  const busy = analyzing || generating
  const canSubmit = !loading && !busy && !!resumeText && !!jobText && !exceedsLimit

  useEffect(() => () => {
    upload.current?.abort()
    pendingAnalysis.current?.abort()
    pendingLetter.current?.abort()
  }, [])

  function clearAnalysis() {
    setAnalysis(null)
    setAnalysisError('')
  }

  async function runAnalysis() {
    if (!canSubmit || pendingAnalysis.current || pendingLetter.current || upload.current) return
    clearAnalysis()
    const controller = new AbortController()
    pendingAnalysis.current = controller
    setAnalyzing(true)
    try {
      const result = await analyzeResume(resumeText, jobText, controller.signal)
      if (!controller.signal.aborted) setAnalysis(result)
    } catch (error) {
      if (!controller.signal.aborted) {
        setAnalysisError(error instanceof Error ? error.message : 'Could not analyze the resume. Try again.')
      }
    } finally {
      pendingAnalysis.current = null
      if (!controller.signal.aborted) setAnalyzing(false)
    }
  }

  async function runLetterGeneration() {
    if (!canSubmit || pendingAnalysis.current || pendingLetter.current || upload.current) return
    const controller = new AbortController()
    pendingLetter.current = controller
    setGenerating(true)
    setLetterError('')
    setExportFeedback('')
    setExportError('')
    try {
      const result = await generateCoverLetter(resumeText, jobText, tone, controller.signal)
      if (!controller.signal.aborted) setLetter(result.cover_letter)
    } catch (error) {
      if (!controller.signal.aborted) {
        setLetterError(error instanceof Error ? error.message : 'Could not generate a cover letter. Try again.')
      }
    } finally {
      pendingLetter.current = null
      if (!controller.signal.aborted) setGenerating(false)
    }
  }

  async function copyLetter() {
    if (!letter?.trim()) return
    setExportFeedback('')
    setExportError('')
    try {
      await navigator.clipboard.writeText(letter)
      setExportFeedback('Cover letter copied.')
    } catch {
      setExportError('Could not copy the cover letter. Select the text and copy it manually.')
    }
  }

  function downloadLetter() {
    if (!letter?.trim()) return
    const url = URL.createObjectURL(new Blob([letter], { type: 'text/plain;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'cover-letter.txt'
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  async function uploadFiles(files: FileList | null) {
    if (!files?.length || upload.current || pendingAnalysis.current || pendingLetter.current) return
    const file = files[0]
    setError('')
    if (files.length !== 1) {
      setError('Upload one resume at a time.')
      return
    }
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Choose a PDF resume.')
      return
    }
    if (file.size > maxResumeSize) {
      setError('The resume must be 5 MB or smaller.')
      return
    }

    const controller = new AbortController()
    upload.current = controller
    setLoading(true)
    try {
      const { text } = await extractResume(file, controller.signal)
      if (controller.signal.aborted) return
      setResume(text)
      setFilename(file.name)
      clearAnalysis()
    } catch (error) {
      if (!controller.signal.aborted) {
        setError(error instanceof Error ? error.message : 'Could not extract the resume. Try again.')
      }
    } finally {
      upload.current = null
      if (!controller.signal.aborted) setLoading(false)
    }
  }

  return (
    <>
      <div className="assistant-grid">
        <section className="table-panel assistant-panel" aria-labelledby="resume-heading">
          <header className="table-intro">
            <h2 id="resume-heading">Resume</h2>
            <p>Upload a PDF, then review and edit the extracted text.</p>
          </header>
          <div className="assistant-fields">
            <div className="resume-drop-zone" data-dragging={dragging}
              onDragOver={(event) => {
                event.preventDefault()
                event.dataTransfer.dropEffect = loading || busy ? 'none' : 'copy'
                if (!loading && !busy && event.dataTransfer.types.includes('Files')) setDragging(true)
              }}
              onDragLeave={(event) => {
                const next = event.relatedTarget
                if (!(next instanceof Node) || !event.currentTarget.contains(next)) setDragging(false)
              }}
              onDrop={(event) => {
                event.preventDefault()
                setDragging(false)
                void uploadFiles(event.dataTransfer.files)
              }}>
              <span className="stat-icon tone-blue"><FileUp size={19} aria-hidden="true" /></span>
              <div className="resume-drop-copy">
                <p>Drag and drop your resume here</p>
                <p id="resume-limit">PDF up to 5 MB</p>
              </div>
              <input ref={input} type="file" accept=".pdf,application/pdf" hidden disabled={loading || busy}
                onChange={(event) => {
                  void uploadFiles(event.currentTarget.files)
                  event.currentTarget.value = ''
                }} />
              <button type="button" className="button button-secondary" disabled={loading || busy}
                aria-describedby="resume-limit" onClick={() => input.current?.click()}>
                {loading && <LoaderCircle size={16} className="resume-spinner" aria-hidden="true" />}
                {loading ? 'Extracting…' : filename ? 'Replace PDF' : 'Choose PDF'}
              </button>
            </div>
            <div className="resume-feedback" role="status">
              {loading ? 'Extracting resume text…' : filename && `Loaded ${filename}`}
            </div>
            {error && <p className="storage-alert" role="alert">{error}</p>}
            <label htmlFor="resume-text">Resume text</label>
            <textarea id="resume-text" value={resume} readOnly={loading || busy}
              placeholder="Extracted text will appear here. You can also paste your resume."
              onChange={(event) => {
                setResume(event.target.value)
                clearAnalysis()
              }} />
          </div>
        </section>
        <section className="table-panel assistant-panel" aria-labelledby="job-heading">
          <header className="table-intro">
            <h2 id="job-heading"><label htmlFor="job-description">Job description</label></h2>
            <p>Paste the posting for the internship you’re targeting.</p>
          </header>
          <div className="assistant-fields assistant-job">
            <textarea id="job-description" value={jobDescription} readOnly={busy}
              placeholder="Paste the job description here."
              onChange={(event) => {
                setJobDescription(event.target.value)
                clearAnalysis()
              }} />
            <div className="analysis-actions">
              <p id="gemini-notice">Both AI actions send your resume text and job description to Google Gemini. Remove personal details you don’t want to share.</p>
              {exceedsLimit && <p role="alert" className="storage-alert">Keep each text field to 30,000 characters or fewer.</p>}
              {analysisError && <p role="alert" className="storage-alert">{analysisError}</p>}
              <div className="cover-letter-tone">
                <label htmlFor="cover-letter-tone">Cover letter tone</label>
                <select id="cover-letter-tone" value={tone} disabled={generating}
                  onChange={(event) => setTone(event.target.value as CoverLetterTone)}>
                  <option value="professional">Professional</option>
                  <option value="enthusiastic">Enthusiastic</option>
                  <option value="concise">Concise</option>
                </select>
              </div>
              {letterError && <p role="alert" className="storage-alert">{letterError}</p>}
              <div className="assistant-buttons">
                <button type="button" className="button button-primary" disabled={!canSubmit}
                  aria-describedby="gemini-notice" onClick={() => void runAnalysis()}>
                  {analyzing ? <LoaderCircle size={17} className="resume-spinner" aria-hidden="true" /> : <Sparkles size={17} aria-hidden="true" />}
                  {analyzing ? 'Analyzing…' : 'Analyze Resume'}
                </button>
                <button type="button" className="button button-secondary" disabled={!canSubmit}
                  aria-describedby="gemini-notice" onClick={() => void runLetterGeneration()}>
                  {generating
                    ? <LoaderCircle size={17} className="resume-spinner" aria-hidden="true" />
                    : <FileText size={17} aria-hidden="true" />}
                  {generating ? 'Generating…' : 'Generate Cover Letter'}
                </button>
              </div>
              <p role="status" className="sr-only">
                {analyzing ? 'Analyzing your resume with Gemini.' : analysis ? 'Resume analysis is ready below.' : ''}
              </p>
              <p role="status" className="sr-only">
                {generating ? 'Generating and checking your cover letter with Gemini.'
                  : letter !== null && !letterError ? 'Cover letter draft is ready below.' : ''}
              </p>
            </div>
          </div>
        </section>
      </div>
      {letter !== null && (
        <section className="table-panel analysis-results" aria-labelledby="cover-letter-heading">
          <header className="table-intro">
            <h2 id="cover-letter-heading"><label htmlFor="cover-letter-draft">Cover letter draft</label></h2>
            <p>Review the details against your resume and edit the draft before sending it.</p>
          </header>
          <div className="assistant-fields cover-letter-fields">
            <textarea id="cover-letter-draft" value={letter} readOnly={generating}
              onChange={(event) => {
                setLetter(event.target.value)
                setExportFeedback('')
                setExportError('')
              }} />
            <div className="assistant-buttons">
              <button type="button" className="button button-secondary" disabled={!letter.trim() || generating}
                onClick={() => void copyLetter()}>
                <Copy size={16} aria-hidden="true" /> Copy
              </button>
              <button type="button" className="button button-secondary" disabled={!letter.trim() || generating}
                onClick={downloadLetter}>
                <Download size={16} aria-hidden="true" /> Download (.txt)
              </button>
            </div>
            <div role="status" className="cover-letter-feedback">{exportFeedback}</div>
            {exportError && <p role="alert" className="storage-alert">{exportError}</p>}
          </div>
        </section>
      )}
      {analysis && <ResumeAnalysisResults analysis={analysis} />}
    </>
  )
}
