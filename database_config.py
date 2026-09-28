"""Database namespace validation, independent of Flask and credentials."""
import re


def database_schema(value):
    schema = (value or '').strip()
    if not schema:
        return None
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
        raise ValueError('DATABASE_SCHEMA must be a lowercase SQL identifier.')
    if schema in {'public', 'auth', 'storage', 'information_schema'} or schema.startswith('pg_'):
        raise ValueError('DATABASE_SCHEMA must be a dedicated application schema.')
    return schema
