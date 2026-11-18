# Testing

This document describes the current automated test coverage and how to run the
backend and frontend suites.

## Current status

Last verified: 2026-11-18

| Area | Automated tests passed | Other validation |
|---|---:|---|
| Backend API | 103 | FastAPI tests run against an isolated in-memory SQLite database |
| Backend statement coverage | 86% | 224 of 1634 statements are currently uncovered |
| Frontend | 16 | TypeScript check and Vite production build pass |

The 16 frontend tests are Vitest and React Testing Library tests covering app
routes and recipe search/detail interactions. The production build remains a
separate compilation check and is not counted as an automated test.

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

### Backend coverage

The backend test suite covers:

- Recipe CRUD, validation, ingredient editing, and not-found responses.
- Ingredient matching, alias and mapping lookup, and mapping import behavior.
- Fineli measure parsing, household units, fractions, negligible measures, and
  kilogram/gram conversion.
- Nutrition recalculation, partial nutrient data, calculation history, and
  stale-cache invalidation.
- Local Fineli data import and searches.
- TheMealDB response mapping and selected cache behavior.
- PostgreSQL trigram setup, SQLite behavior, and PostgreSQL setup fallback.

Recent regression coverage verifies that ingredient edits do not retain stale
quantity values:

- An explicit quantity must agree with the amount text or be reconciled through
  the selected Fineli food.
- Removing a match clears the Fineli source and quantity.
- Quantified amounts such as tablespoons are recalculated.
- `to taste` and other negligible amounts clear quantity metadata.
- A deleted or unavailable Fineli mapping is handled as unknown quantity.

For a line-by-line coverage report, install the coverage plugin and run:

```powershell
python -m pip install pytest-cov
python -m pytest --cov=app --cov-report=term-missing -q
```

## Running frontend validation

From the frontend directory:

```powershell
npm install
npm test
npm run build
```

`npm test` runs the Vitest suite. It currently includes app routing, meal
search, recipe detail matching, nutrition display, and basic error handling.

`npm run build` runs `tsc -b` and creates a Vite production build. It checks
TypeScript compilation and bundling separately from browser behavior.

## To do

- [ ] Add frontend tests for auto-match loading/failure and retry interactions.
- [ ] Test quantity editing, unmatched ingredients, and stale nutrition invalidation
  in the browser UI.
- [ ] Add frontend tests for empty suggestion lists and missing Fineli metadata.
- [ ] Cover more client-side API errors and concurrent submission states.
- [ ] Add PostgreSQL fuzzy-search and trigram integration tests.
- [ ] Add external-provider timeout, HTTP 429/5xx, malformed payload, and cache
  expiry tests.
- [ ] Cover migration scripts and download/import scripts more extensively.
- [ ] Add frontend coverage reporting.
- [ ] Add a PostgreSQL-backed integration test run using a separate disposable
  test database to catch differences that SQLite cannot cover.
- [ ] Run backend tests and frontend validation in CI on each pull request.

Update the current-status table when a test run or validation changes. Keep
frontend build results separate from automated test counts.
