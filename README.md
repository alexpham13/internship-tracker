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

Open [the dashboard](http://localhost:5173). Open [the API docs](http://127.0.0.1:8000/docs) to try endpoints. Ports 5173 and 5174 are allowed for both `localhost` and `127.0.0.1`.

The API URL defaults to `http://127.0.0.1:8000`. To change it, copy the root `.env.example` to `.env`, set `VITE_API_BASE_URL`, and restart Vite. SQLite defaults to `backend/interntrack.sqlite3`. To change the file, copy `backend/.env.example` to `backend/.env`, set `DATABASE_PATH`, and restart Uvicorn. Relative database paths are resolved from `backend/`.

## Import browser records

Open the dashboard from the same browser profile, hostname, and port you used before. Go to **Settings → Import browser applications**. The import preserves the original IDs and reports how many records were imported or skipped. Retrying skips IDs the database has already seen, including imported records that you later deleted. The original browser records are retained as a backup.

## API and request lifecycle

React calls the API through `src/api.ts`. Pydantic validates incoming JSON before SQLAlchemy writes to SQLite in a request-scoped session. The server commits changes before returning. React then updates the table and recalculates its cards from the loaded records. The statistics endpoint exposes the same rules for API callers.

| Method | Path | Result |
| --- | --- | --- |
| GET | `/health` | SQLite connectivity check |
| GET | `/applications` | Applications ordered by date |
| POST | `/applications` | Create an application and assign its ID |
| PUT | `/applications/{id}` | Replace the fields of an existing application |
| DELETE | `/applications/{id}` | Delete an application |
| GET | `/statistics` | Totals for applications, responses, interviews, and offers |
| POST | `/applications/import` | Import a batch of legacy browser records |

Responses include every status beyond Applied. Interviews and Offers count applications currently at those stages.

## Checks

From the repository root:

```sh
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
backend/.venv/bin/python -m unittest discover -s backend/tests -v
npm run build
npm run lint
```

Each API test uses its own temporary SQLite database.
