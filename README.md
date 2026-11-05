# Recipe App

School project starter: a recipe / food web page.

| Layer    | Tech                                  |
| -------- | ------------------------------------- |
| Frontend | TypeScript, React, Vite               |
| Backend  | Python, FastAPI, SQLAlchemy           |
| Database | PostgreSQL (via Docker for local dev) |

## Project structure

```
recipe-app/
├── docker-compose.yml        # PostgreSQL for local development
├── backend/
│   ├── requirements.txt
│   ├── .env.example          # copy to .env
│   └── app/
│       ├── main.py           # FastAPI app, CORS, router registration
│       ├── config.py         # settings from environment / .env
│       ├── database.py       # engine, session, get_db dependency
│       ├── models.py         # SQLAlchemy tables (Recipe, Ingredient)
│       ├── schemas.py        # Pydantic request/response models
│       └── routers/
│           └── recipes.py    # /api/recipes endpoints
└── frontend/
    ├── package.json
    ├── vite.config.ts        # dev proxy: /api -> localhost:8000
    └── src/
        ├── main.tsx
        ├── App.tsx           # header + routes
        ├── api.ts            # all backend calls live here
        ├── types.ts          # TS types mirroring backend schemas
        └── pages/            # meal search, list, detail, create form
```

## Requirements

- [Node.js](https://nodejs.org/) 20+
- [Python](https://www.python.org/) 3.11+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for the database)
  - No Docker? Install PostgreSQL locally, create a database `recipes` with user/password
    `recipes`, or change `DATABASE_URL` in `backend/.env`.

## Running it (3 terminals in VS Code)

### 1. Database

From the repository root, start the database:

```powershell
docker compose up -d db
```

### 2. Backend

Open a terminal in the repository root, then run each command below in order. Keep
using this same terminal for the backend.

```powershell
Set-Location backend
```

Create the virtual environment once:

```powershell
python -m venv .venv
```

Activate it whenever you open a new backend terminal:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the backend dependencies:

```powershell
python -m pip install -r requirements.txt
```

Create `backend/.env` once. If it already exists, do not overwrite it; make sure its
`DATABASE_URL` is `postgresql+psycopg://recipes:recipes@127.0.0.1:5433/recipes`.

```powershell
Copy-Item .env.example .env
```

Start the backend and leave this terminal open:

```powershell
python -m uvicorn app.main:app --reload
```

Wait for `Application startup complete`. The API health check is
http://localhost:8000/api/health, and interactive API docs are at
http://localhost:8000/docs. Tables are created automatically on startup.

To check the API from another PowerShell terminal:

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

To stop the backend, press `Ctrl+C` in its terminal. To leave the virtual environment
after stopping the backend, run:

```powershell
deactivate
```

If PowerShell blocks virtual-environment activation, skip activation and run the
backend tools through the environment's Python instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

On macOS/Linux, run the following commands from the repository root, in order:

```bash
cd backend
```

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
python -m pip install -r requirements.txt
```

```bash
cp .env.example .env
```

```bash
python -m uvicorn app.main:app --reload
```

To leave the virtual environment on macOS/Linux, run `deactivate` after stopping
the backend with `Ctrl+C`.

### Fineli nutrition data (one-time setup)

Fineli's API blocks our backend (Cloudflare), so nutrition data is imported from the open
data package instead. The data is not stored in git.
The staging and import commands display progress while processing the data.

1. Download the Fineli Rel20 nutrient-data ZIP in your browser and move it to the
   repository root. Keep the filename `Fineli_Rel20__74_ravintotekij__.zip`.
2. From `backend/`, stage the required CSV files into `backend/data/fineli/`:

   ```powershell
   python -m app.scripts.download_fineli
   ```

   Use `--output-dir` to change the staging directory.
3. With the database running, import the data from `backend/`:

   ```powershell
   python -m app.scripts.import_fineli
   ```

The backend uses the imported local dataset for Fineli lookups and does not rely on
Fineli's online API. Re-running the import safely replaces the previous Fineli dataset.
Data: Fineli, Finnish Institute for Health and Welfare (THL), CC BY 4.0.

### Backend API tests

The backend tests use an isolated in-memory SQLite database and do not require
Docker or modify the local PostgreSQL database.

From the repository root, switch to `backend/`:

```powershell
Set-Location backend
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the test dependencies:

```powershell
python -m pip install -r requirements-dev.txt
```

Run the tests:

```powershell
python -m pytest -q
```

### 3. Frontend

Open another terminal in the repository root and switch to `frontend/`:

```powershell
Set-Location frontend
```

Install the frontend dependencies:

```powershell
npm install
```

Start the frontend:

```powershell
npm run dev
```

Open http://localhost:5173. Leave this terminal open while using the app. Stop the
frontend with `Ctrl+C`.

The homepage searches TheMealDB. Saved recipes remain available at
http://localhost:5173/my-recipes, and the search page calls the backend at
`/api/meals/search?q=...`, matching the meal-search route used by the
TheMealDB-implementation branch.

### Frontend tests

Open another terminal in the repository root and switch to `frontend/`:

```powershell
Set-Location frontend
```

Run the frontend tests:

```powershell
npm test
```

## VS Code

Open the `recipe-app` folder (not a subfolder). VS Code will suggest the recommended
extensions. Select the Python interpreter at `backend/.venv`. There is also a
"Backend: FastAPI (debug)" launch config under Run and Debug (F5).

## Working together

- Make a Git repo and push it to GitHub; each person works on their own branch and opens
  pull requests into `main`.
- `.env` files are git-ignored. Never commit passwords; share changes to settings by
  updating `.env.example`.
- When you change a backend schema in `backend/app/schemas.py`, update
  `frontend/src/types.ts` to match.

## Ideas for next steps

- Edit recipe (PUT endpoint + form)
- Categories / tags (many-to-many table)
- Recipe images (upload or URL)
- User accounts and login
- Switch from `create_all` to Alembic migrations when the schema starts changing
