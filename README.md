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
        └── pages/            # list, detail, create form
```

## Requirements

- [Node.js](https://nodejs.org/) 20+
- [Python](https://www.python.org/) 3.11+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for the database)
  - No Docker? Install PostgreSQL locally, create a database `recipes` with user/password
    `recipes`, or change `DATABASE_URL` in `backend/.env`.

## Running it (3 terminals in VS Code)

### 1. Database

```bash
docker compose up -d
```

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Interactive API docs (try endpoints in the browser): http://localhost:8000/docs

Tables are created automatically on startup.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

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
- Search and filtering (by title, ingredient, prep time)
- Categories / tags (many-to-many table)
- Recipe images (upload or URL)
- User accounts and login
- Switch from `create_all` to Alembic migrations when the schema starts changing
- Tests (pytest for backend, Vitest for frontend)
