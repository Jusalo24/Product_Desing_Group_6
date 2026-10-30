# Testing

This document describes the current test coverage, how to run it, and the main
testing gaps for the backend API and frontend.

## Current status

Last verified: 2026-10-30

| Area | Automated tests passed | Other validation |
|---|---:|---|
| Backend API | 9 | FastAPI tests run against an isolated in-memory SQLite database |
| Frontend | 0 | TypeScript check and Vite production build pass |

The frontend currently has no test runner or frontend test files. The frontend
build is a useful compilation check, but it is not counted as a test.

## Running backend API tests

From the repository root:

```powershell
python -m pip install -r backend/requirements-dev.txt
python -m pytest -q
```

Or from the backend directory:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The test fixture in `backend/tests/conftest.py` gives each test an in-memory
SQLite database and redirects the app's database dependency to it. Tests do not
need Docker and do not read, write, or delete data in the development PostgreSQL
database.

### API coverage

The tests in `backend/tests/test_recipes.py` cover:

- `GET /api/health` returns the expected health payload.
- `GET /api/recipes` returns an empty list for a new database.
- Creating a recipe returns `201` and its saved recipe and ingredients can be
  read back from both the detail and list endpoints.
- Invalid recipe data returns `422` and is not persisted.
- Looking up or deleting an unknown recipe returns `404`.
- Deleting a recipe returns `204` and the recipe is no longer available.

The reported total is 9 tests, including the four parameterized invalid-payload
cases.

## Running frontend validation

From the frontend directory:

```powershell
npm install
npm run build
```

`npm run build` runs `tsc -b` and creates a Vite production build. It checks
TypeScript compilation and bundling, but does not exercise rendered pages,
browser interactions, API calls, accessibility, or UI behavior.

## To do

- [ ] Add frontend tests for key pages and user interactions, including loading,
  empty, error, and success states.
- [ ] Add tests for client-side API request behavior and error handling.
- [ ] Add a PostgreSQL-backed integration test run using a separate disposable
  test database to catch differences that SQLite cannot cover.
- [ ] Expand backend API cases as behavior grows, such as ordering, optional and
  boundary values, and database failure handling.
- [ ] Run backend tests and frontend validation in CI on each pull request.

Update the current-status table when a test run or validation changes. Keep
frontend build results separate from automated test counts.
