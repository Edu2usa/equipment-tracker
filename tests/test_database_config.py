import os
import subprocess
import sys
import unittest
from database_config import database_schema


class SchemaTests(unittest.TestCase):
    def test_legacy_schema_is_unchanged_when_unset(self):
        self.assertIsNone(database_schema(None))
        self.assertIsNone(database_schema(''))

    def test_dedicated_schema(self):
        self.assertEqual(database_schema('equipment_tracker'), 'equipment_tracker')

    def test_rejects_shared_and_unsafe_schema_names(self):
        for name in ('public', 'auth', 'storage', 'pg_catalog', 'information_schema', 'x;drop schema public', 'a.b', 'a"b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                database_schema(name)

    def test_all_models_and_foreign_keys_use_dedicated_schema(self):
        env = dict(os.environ, DATABASE_SCHEMA='equipment_tracker')
        script = """
from models import db, EquipmentItem
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
assert len(db.metadata.tables) == 6
for table in db.metadata.tables.values():
    assert table.schema == 'equipment_tracker'
    for foreign_key in table.foreign_keys:
        assert foreign_key.column.table.schema == 'equipment_tracker'
sql = str(CreateTable(EquipmentItem.__table__).compile(dialect=postgresql.dialect()))
assert 'equipment_tracker.equipment_items' in sql
assert 'REFERENCES equipment_tracker.accounts' in sql
"""
        result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
