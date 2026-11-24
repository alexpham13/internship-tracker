# InternTrack AI

A local internship tracker with a React and TypeScript frontend and a FastAPI backend.

## Run locally

From the repository root, start the backend in one terminal. The commands use the existing virtual environment. On a fresh checkout, first run `python3 -m venv backend/.venv` with Python 3.11 or later.

```sh
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal at the repository root, start the frontend.

```sh
npm ci
npm run dev -- --host localhost --port 5173
```

Open [InternTrack AI](http://localhost:5173), select **Create an account**, and enter your name, email, and a password of at least 15 characters. Use **Sign out** in the sidebar to end your session.

Vite proxies `/api` to FastAPI on `127.0.0.1:8000` by default. For a direct API URL, set `VITE_API_BASE_URL` in the root `.env` and use the same hostname for the frontend and API. Remove an old direct URL override to use the proxy. SQLite defaults to `backend/interntrack.sqlite3`. To change it, set `DATABASE_PATH` in `backend/.env` and restart Uvicorn. Relative database paths resolve from `backend/`.

### Sessions and deployment

- The API hashes passwords with Argon2id. Registration rejects duplicate normalized email addresses. Login errors use the same message for unknown accounts and incorrect passwords.
- Sessions expire after 12 hours and are revoked server-side on sign-out. The browser receives a host-only, HttpOnly, SameSite=Lax cookie with Secure enabled by default. SQLite stores a hash of the session token. If your browser refuses the Secure cookie on loopback HTTP, set `AUTH_COOKIE_SECURE=false` only for that local setup and restart the backend.
- Browser writes require both a trusted `Origin` and `X-InternTrack-Request: 1`. The default allowlist covers Vite on ports 5173, 5174, and 4173 for `localhost` and `127.0.0.1`. For deployment, serve through HTTPS, scope `AUTH_ALLOWED_ORIGINS` to the exact public frontend origin, and keep `AUTH_COOKIE_SECURE=true`. Serve the frontend and API on the same origin when possible, route `/api/*` to FastAPI with the prefix stripped, and route `/login` and `/register` to the frontend entry page.
- Login and registration are rate limited in SQLite in 15-minute windows. Login allows 30 attempts per IP and 20 per normalized account address, and registration allows 8 attempts per IP. If deploying behind a proxy, configure trusted proxy addresses in Uvicorn and have the proxy replace untrusted forwarded IP headers.

### Recover existing applications

The backend migrates the existing SQLite tables on startup. Existing applications and import history remain unassigned and are invisible to every account until the database operator assigns them. New accounts otherwise start empty. Back up the SQLite database before upgrading.

Register the intended owner's account, then run this from the repository root against the same database used by Uvicorn:

```sh
backend/.venv/bin/python -m backend.claim_legacy owner@example.com
```

Reload the workspace after running the command. It assigns the existing SQLite rows and import history and enables the older browser-record import for that account. Run the command only for the account you intend to own the legacy records.

## Resume analysis with Gemini

1. Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey).
2. If `backend/.env` does not exist, create it from `backend/.env.example`. Set `GEMINI_API_KEY` there. Keep the key out of the frontend environment and source control.
3. The default model is `gemini-3.5-flash-lite`. To use another Gemini model that supports structured JSON output, set `GEMINI_MODEL` in `backend/.env`.
4. Install the backend requirements and restart Uvicorn. Open **AI Assistant**, upload a PDF or paste resume text, paste a job description, then select **Analyze Resume**. Each text field supports up to 30,000 characters. Use sample text when testing with a real key.

PDF extraction runs locally. Selecting **Analyze Resume** sends the edited resume text and job description to Google Gemini through the backend. InternTrack does not save these inputs or analysis results. The match score is an AI-generated estimate and no ATS is used. Review suggested rewrites against the source excerpts before copying them.

If analysis fails, check the Uvicorn console for a `Gemini analysis failed` warning. It reports a failure category and, when available, the provider status or validation error codes. It omits credentials, resume and job description text, and raw provider responses.

## Generate a cover letter

In **AI Assistant**, upload a PDF or paste resume text, then paste the internship posting. Choose **Professional**, **Enthusiastic**, or **Concise** and select **Generate Cover Letter**. The feature uses the same backend Gemini key and model as resume analysis.

InternTrack enforces a 250–350-word limit on generated drafts and asks Gemini to check each draft against the resume and posting before showing it. Review the draft against your sources, edit it in place, then select **Copy** or **Download (.txt)** to export the edited text. Use sample inputs when testing with a real key. InternTrack sends the inputs to Gemini for generation and review and keeps the draft in page memory.

If Gemini returns HTTP 503, the backend retries the affected step up to twice, after 1 and 2 seconds. Each Gemini request uses a 30-second timeout. Backend warnings identify generation or grounding verification and omit input text, credentials, and provider response bodies.

## Import browser records

After the database operator assigns legacy access, sign in to that account using the same browser profile, hostname, and port you used before. Go to **Settings → Import browser applications**. The import preserves the original IDs and reports how many records were imported or skipped. Retrying skips IDs the database has already seen, including imported records that you later deleted. The original browser records are retained as a backup.

## API and request lifecycle

React calls the API through `src/api.ts`. Pydantic validates incoming JSON before SQLAlchemy writes to SQLite in a request-scoped session. The server commits changes before returning. React then updates the table and recalculates its cards from the loaded records. The statistics endpoint exposes the same rules for API callers.

| Method | Path | Result |
| --- | --- | --- |
| GET | `/health` | Public SQLite connectivity check |
| POST | `/auth/register` | Register with name, email, and password |
| POST | `/auth/login` | Sign in with email and password |
| GET | `/auth/me` | Read the signed-in account |
| POST | `/auth/logout` | Revoke the session and clear its cookie |
| GET | `/applications` | Applications ordered by date |
| POST | `/applications` | Create an application and assign its ID |
| PUT | `/applications/{id}` | Replace the fields of an existing application |
| DELETE | `/applications/{id}` | Delete an application |
| GET | `/statistics` | Totals for applications, responses, interviews, and offers |
| POST | `/applications/import` | Import a batch of legacy browser records |
| POST | `/resume/extract` | Extract text from a PDF up to 5 MB |
| POST | `/resume/analyze` | Analyze JSON fields `resume_text` and `job_description` with Gemini |
| POST | `/cover-letter/generate` | Generate a draft from `resume_text`, `job_description`, and `tone` (`professional`, `enthusiastic`, or `concise`) |

Responses include every status beyond Applied. Interviews and Offers count applications currently at those stages.

## Checks

From the repository root:

```sh
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
backend/.venv/bin/python -m unittest discover -s backend/tests -v
npm run build
npm run lint
```

Each API test uses its own temporary SQLite database. Resume analysis and cover letter tests mock Gemini and require neither credentials nor network access.

For a browser smoke test, register two accounts with different emails and create an application under the first. Reload and verify that your session persists. Sign out, sign in to the second account, and confirm that its dashboard and applications list are empty. Then sign back in to the first account and edit or delete its application. Open **AI Assistant** to confirm the signed-in workspace is accessible. The automated suite also covers password hashing, session replay and expiration, CSRF checks, rate limits, and legacy migration.
