# Preferred Maintenance Equipment Tracker

Flask equipment inventory, account assignment, maintenance, and reports.

## Local development

Create a virtual environment and install `requirements.txt`, then run:

```powershell
python -m flask --app app run --port 5055
```

Without a database environment variable, local development uses SQLite in the
ignored instance directory. Never use temporary SQLite on Vercel.

## Shared database setup

Configure `DATABASE_URL` (or existing `POSTGRES_URL`) and a random, stable
`SECRET_KEY` in the hosting environment. Do not put credentials in source code.
With the same database environment configured in a trusted terminal, initialize
a new database explicitly:

```powershell
python -m flask --app app init-db
```

This additive command creates tables, fills missing equipment IDs, and adds
missing default catalog/account records. It does not delete QA-prefixed records,
rename accounts, or overwrite account types. Back up an existing database first.
Production startup does not run schema changes or catalog cleanup.

Database outages return a redacted 503 page, not fabricated empty inventory.
Repair watch reflects the saved equipment status, not an inferred maintenance
schedule. Equipment deletion also deletes its maintenance history and requires
confirmation in the browser.

## Verification

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py models.py
```

Tests use an isolated in-memory database. Check the dashboard and inventory on
desktop and phone; add/edit equipment, transfer it, log maintenance, review
reports, and test filters in a non-production database.

## Remaining production security requirement

This app does not currently implement user authentication or role-based write
authorization. Do not treat a public URL as a private staff system. Configure
appropriate access protection before storing sensitive operational data. Auth,
CSRF protection, and permission policy require a separate agreed security pass.
