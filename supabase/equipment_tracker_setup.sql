-- TEMPLATE ONLY: prepare_fresh_setup.py supplies a private random password.
-- Run the generated private file in the healthy project's SQL Editor as postgres.
-- This is an additive fresh installation, not a reset or recovery migration.
BEGIN;

DO $$
BEGIN
  IF '__TRACKER_PASSWORD__' LIKE '\_\_%' THEN
    RAISE EXCEPTION 'Use the generated private setup file, not this template.';
  END IF;
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'pm_equipment_app')
     OR EXISTS (SELECT FROM pg_namespace WHERE nspname = 'equipment_tracker') THEN
    RAISE EXCEPTION 'Equipment Tracker already exists. Nothing was reset. Ask for verification instead.';
  END IF;
END $$;

CREATE ROLE pm_equipment_app LOGIN PASSWORD '__TRACKER_PASSWORD__'
  NOSUPERUSER NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE SCHEMA equipment_tracker;
REVOKE ALL ON SCHEMA equipment_tracker FROM PUBLIC, anon, authenticated, service_role;
GRANT USAGE ON SCHEMA equipment_tracker TO pm_equipment_app;
GRANT CONNECT ON DATABASE postgres TO pm_equipment_app;

CREATE TABLE equipment_tracker.accounts (
  id SERIAL PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  account_type VARCHAR(50) NOT NULL,
  location VARCHAR(120) NOT NULL DEFAULT ''
);
CREATE TABLE equipment_tracker.equipment_items (
  id SERIAL PRIMARY KEY,
  equip_id VARCHAR(20) UNIQUE,
  name VARCHAR(120) NOT NULL,
  equipment_type VARCHAR(80) NOT NULL,
  service_type VARCHAR(80),
  account_id INTEGER NOT NULL REFERENCES equipment_tracker.accounts(id),
  quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
  item_status VARCHAR(50) NOT NULL DEFAULT 'working'
    CHECK (item_status IN ('working','in_repair','in_storage')),
  last_service_date DATE
);
CREATE TABLE equipment_tracker.maintenance_records (
  id SERIAL PRIMARY KEY,
  equipment_id INTEGER NOT NULL REFERENCES equipment_tracker.equipment_items(id),
  maintenance_type VARCHAR(80) NOT NULL,
  service_date DATE NOT NULL DEFAULT CURRENT_DATE,
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE equipment_tracker.equipment_names (id SERIAL PRIMARY KEY, name VARCHAR(120) NOT NULL UNIQUE);
CREATE TABLE equipment_tracker.equipment_types (id SERIAL PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE);
CREATE TABLE equipment_tracker.equipment_service_types (id SERIAL PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE);

CREATE INDEX equipment_tracker_account_idx ON equipment_tracker.equipment_items(account_id);
CREATE INDEX equipment_tracker_status_idx ON equipment_tracker.equipment_items(item_status);
CREATE INDEX equipment_tracker_history_idx ON equipment_tracker.maintenance_records(equipment_id, service_date);

REVOKE ALL ON ALL TABLES IN SCHEMA equipment_tracker FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA equipment_tracker FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA equipment_tracker TO pm_equipment_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA equipment_tracker TO pm_equipment_app;

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['accounts','equipment_items','maintenance_records','equipment_names','equipment_types','equipment_service_types'] LOOP
    EXECUTE format('ALTER TABLE equipment_tracker.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY equipment_backend_access ON equipment_tracker.%I FOR ALL TO pm_equipment_app USING (true) WITH CHECK (true)', t);
  END LOOP;
  -- Fail rather than silently inherit pre-existing PUBLIC grants to other apps.
  IF EXISTS (
    SELECT FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('public','auth','storage') AND c.relkind IN ('r','p','v','m')
      AND has_table_privilege('pm_equipment_app', c.oid, 'SELECT,INSERT,UPDATE,DELETE')
  ) THEN
    RAISE EXCEPTION 'Existing PUBLIC table privileges need review; the isolated setup has been rolled back.';
  END IF;
END $$;

INSERT INTO equipment_tracker.equipment_names(name) VALUES
('Canister Vacuum'),('Backpack Vacuum - Cord'),('Backpack Vacuum - Battery'),
('Barrel Solo'),('Barrel Double'),('Barrel - Cart'),('Narrow Buffer'),('Wide Buffer'),
('Extractor'),('Scrubber'),('Walk-Behind Scrubber'),('Ride-On Scrubber'),
('Mop Bucket'),('Maid Cart'),('Ladder'),('Fan'),('Other');
INSERT INTO equipment_tracker.equipment_types(name) VALUES
('Tennant'),('Nobles'),('ProTeam'),('Hoover'),('Sanitaire'),('Nilfisk'),('Clarke'),('Advance'),('Karcher'),('Other');
INSERT INTO equipment_tracker.equipment_service_types(name) VALUES
('General Service'),('Batteries'),('Hose'),('Filter'),('Brush'),('Pad Driver'),
('Squeegee'),('Belt'),('Motor'),('Charger'),('Other');

COMMIT;
SELECT 'Equipment Tracker is ready. No accounts, equipment, or maintenance records were added.' AS result;
