-- Preferred Maintenance Equipment Tracker
-- Run this once in the Supabase SQL Editor (postgres role), BEFORE deploying
-- the app version that adds sign-in, the API, service intervals, and NFC pages.
-- Safe to run again. It only adds missing columns, the login lockout table,
-- and the grants the restricted app role needs. It does not delete data.
--
-- The website login (pm_equipment_app) cannot change tables. Do not run this
-- with that login, and do not run flask init-db against this database.

BEGIN;

ALTER TABLE equipment_tracker.equipment_items
  ADD COLUMN IF NOT EXISTS service_interval_days INTEGER;
ALTER TABLE equipment_tracker.equipment_items
  ADD COLUMN IF NOT EXISTS serial_number VARCHAR(120);
ALTER TABLE equipment_tracker.equipment_items
  ADD COLUMN IF NOT EXISTS purchase_date DATE;
ALTER TABLE equipment_tracker.equipment_items
  ADD COLUMN IF NOT EXISTS notes TEXT;

ALTER TABLE equipment_tracker.maintenance_records
  ADD COLUMN IF NOT EXISTS cost NUMERIC(12, 2);
ALTER TABLE equipment_tracker.maintenance_records
  ADD COLUMN IF NOT EXISTS vendor VARCHAR(120);
ALTER TABLE equipment_tracker.maintenance_records
  ADD COLUMN IF NOT EXISTS invoice_ref VARCHAR(120);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'equipment_items_service_interval_positive'
      AND connamespace = 'equipment_tracker'::regnamespace
  ) THEN
    ALTER TABLE equipment_tracker.equipment_items
      ADD CONSTRAINT equipment_items_service_interval_positive
      CHECK (service_interval_days IS NULL OR service_interval_days > 0);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'maintenance_records_cost_nonnegative'
      AND connamespace = 'equipment_tracker'::regnamespace
  ) THEN
    ALTER TABLE equipment_tracker.maintenance_records
      ADD CONSTRAINT maintenance_records_cost_nonnegative
      CHECK (cost IS NULL OR cost >= 0);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS equipment_tracker.login_lockouts (
  id SERIAL PRIMARY KEY,
  bucket VARCHAR(16) NOT NULL,
  bucket_key VARCHAR(64) NOT NULL,
  failures INTEGER NOT NULL DEFAULT 0,
  window_started TIMESTAMP,
  locked_until TIMESTAMP,
  lockout_level INTEGER NOT NULL DEFAULT 0,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT login_lockouts_bucket_key UNIQUE (bucket, bucket_key)
);

CREATE INDEX IF NOT EXISTS login_lockouts_updated_idx
  ON equipment_tracker.login_lockouts (updated_at);

REVOKE ALL ON TABLE equipment_tracker.login_lockouts FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE equipment_tracker.login_lockouts TO pm_equipment_app;
GRANT USAGE, SELECT ON SEQUENCE equipment_tracker.login_lockouts_id_seq TO pm_equipment_app;

ALTER TABLE equipment_tracker.login_lockouts ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'equipment_tracker'
      AND tablename = 'login_lockouts'
      AND policyname = 'equipment_backend_access'
  ) THEN
    CREATE POLICY equipment_backend_access
      ON equipment_tracker.login_lockouts
      FOR ALL
      TO pm_equipment_app
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;

COMMIT;

SELECT 'Equipment Tracker columns and login lockouts are ready.' AS result;
