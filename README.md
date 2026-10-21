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

### Fresh start in a shared Supabase project

Use a verified connection string for the healthy project, not the retired project.
Configure `DATABASE_SCHEMA=equipment_tracker` alongside `DATABASE_URL` and
`SECRET_KEY`. The ORM qualifies every table and foreign key with this schema,
so similarly named tables in `public` are not used or altered.

An administrator can run `python -m flask --app app init-db --empty-accounts`
with a setup connection. This creates seven isolated tables and equipment/service
dropdown choices, but no accounts, equipment, or maintenance records. It is
additive and does not erase an existing schema. No paid project is required.

Do not expose this schema in Supabase's Data API or add anonymous grants. Database
schema isolation does not replace application authentication. Never reset a shared
project's password without coordinating the other apps that use it.

After initialization, deploy the configured environment, add the first account,
and then add equipment. Keep Preview deployments disconnected from production
data. Verify CRUD using an isolated test database before real operational use.

### Setup without resetting a shared database password

`scripts/prepare_fresh_setup.py --project-ref REF --pooler-host HOST` generates
`instance/fresh-setup.private.sql` and `instance/fresh-setup.private.json`.
Both are gitignored and contain a new private credential: do not share or commit
them. It refuses to overwrite previous setup credentials. Use the project ref
and IPv4 shared pooler host shown in Supabase's Connect dialog.

The project owner runs the private SQL file once in Supabase SQL Editor. It
creates a non-admin `pm_equipment_app` login, the isolated schema, seven tables,
and dropdown choices. It does not reset any existing password or change other
apps' tables. The runtime role has data access only within the new schema;
RLS policies permit that role and do not permit anonymous API access. Setup
aborts if names already exist or the new role would inherit PUBLIC table access
to other application schemas. The script is transactional.

Only after successful SQL setup, configure Vercel Production with the database
values from the private JSON, then redeploy. The runtime login is not a schema
administrator: do not use it for future migrations or the init-db command.
Later column changes belong in `supabase/migrations/` and are run in the SQL
Editor before the matching deploy. The app role cannot alter tables.
Remove the private setup artifacts after verification and protect any SQL Editor
history containing the generated credential. A restricted database role does not
protect the website by itself; set the sign-in variables described below.

Database outages return a redacted 503 page, not fabricated empty inventory.
Repair watch reflects the saved equipment status, not an inferred maintenance
schedule. Equipment deletion also deletes its maintenance history and requires
confirmation in the browser.

## Sign-in and the bot API

The website uses one shared username and password: `APP_LOGIN_USER` and
`APP_LOGIN_PASSWORD`. Set both, plus a stable `SECRET_KEY`, in Vercel. If any
of those is missing on Vercel, the site stays closed. Leave them blank in
local files. A phone stays signed in for 180 days.

The shared password may be short, so wrong tries are counted in the database
table `login_lockouts` (this still works on Vercel, where each request can be
a different machine):

- 8 wrong passwords from the same network within 15 minutes locks that network.
- 40 wrong passwords from anywhere within 15 minutes locks sign-in for everyone.
- The first lock lasts 15 minutes. Each further lock doubles, up to 24 hours.
- A successful sign-in clears only that network's lock.
- After a day with no wrong try, the doubling penalty resets.
- To unlock immediately, delete the rows in `equipment_tracker.login_lockouts`
  from the Supabase SQL Editor. Do not do that during a real guessing attack.

Bot calls use `Authorization: Bearer <TRACKER_API_TOKEN>` under `/api`. They
do not use the website login. If `TRACKER_API_TOKEN` is unset, `/api` stays closed.
The API cannot delete anything.

Per-machine pages live at `/equipment/<id>` and keep that address when a machine
is renamed or moved. They require the same sign-in as the rest of the site.

## Verification

```powershell
python -m unittest discover -s tests -v
python -m pytest tests/test_login_api.py -q
python -m compileall -q app.py models.py security.py inventory.py api.py
```

Install pytest from `requirements-dev.txt` when running the second command.
Tests use an isolated in-memory database. Check the dashboard and inventory on
desktop and phone; add/edit equipment, transfer it, log maintenance, review
reports, and test filters in a non-production database.
