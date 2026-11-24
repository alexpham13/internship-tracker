import { BriefcaseBusiness } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { authApi, type Account } from '../api'

export function AuthPage({ registering, onSignIn }: {
  registering: boolean
  onSignIn: (account: Account) => void
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    const data = new FormData(event.currentTarget)
    const email = String(data.get('email') ?? '')
    const password = String(data.get('password') ?? '')
    setPending(true)
    setError('')
    try {
      const account = registering
        ? await authApi.register(String(data.get('name') ?? ''), email, password)
        : await authApi.login(email, password)
      onSignIn(account)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not sign in. Try again.')
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="auth-shell">
      <section className="table-panel auth-panel" aria-labelledby="auth-heading">
        <div className="brand auth-brand">
          <span className="brand-icon"><BriefcaseBusiness size={21} aria-hidden="true" /></span>
          <div className="brand-name">InternTrack <span>AI</span></div>
        </div>
        <header className="table-intro">
          <h1 id="auth-heading">{registering ? 'Create your account' : 'Sign in'}</h1>
        </header>
        <form className="form-fields" onSubmit={(event) => void submit(event)} aria-busy={pending}>
          {registering && (
            <label>Name
              <input name="name" autoComplete="name" maxLength={100} disabled={pending} required />
            </label>
          )}
          <label>Email
            <input name="email" type="email" autoComplete="username" maxLength={254}
              disabled={pending} required />
          </label>
          <label>Password
            <input name="password" type="password" autoComplete={registering ? 'new-password' : 'current-password'}
              minLength={registering ? 15 : 1} maxLength={128} disabled={pending} required
              aria-describedby={registering ? 'password-hint' : undefined} />
            {registering && <span id="password-hint" className="auth-hint">Use at least 15 characters.</span>}
          </label>
          {error && <p className="storage-alert" role="alert">{error}</p>}
          <button className="button button-primary" type="submit" disabled={pending}>
            {registering ? pending ? 'Creating account…' : 'Create account' : pending ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <footer className="table-footer auth-footer">
          {registering ? 'Already have an account?' : 'New to InternTrack AI?'}{' '}
          <a href={registering ? '/login' : '/register'}>{registering ? 'Sign in' : 'Create an account'}</a>
        </footer>
      </section>
    </main>
  )
}
