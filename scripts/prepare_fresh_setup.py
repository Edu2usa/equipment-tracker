"""Generate private setup artifacts; never print or commit credentials."""
import argparse
import json
import re
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-ref', required=True)
    parser.add_argument('--pooler-host', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z]{20}', args.project_ref):
        parser.error('Use the project reference shown in Supabase.')
    if not re.fullmatch(r'aws-\d+-[a-z0-9-]+\.pooler\.supabase\.com', args.pooler_host):
        parser.error('Use the shared pooler hostname shown in Supabase.')
    root = Path(__file__).resolve().parents[1]
    output = root / 'instance'
    output.mkdir(exist_ok=True)
    sql_path = output / 'fresh-setup.private.sql'
    config_path = output / 'fresh-setup.private.json'
    if sql_path.exists() or config_path.exists():
        parser.error('Private setup files already exist; reuse them instead of replacing credentials.')
    password = secrets.token_hex(32)
    template = (root / 'supabase' / 'equipment_tracker_setup.sql').read_text(encoding='utf-8')
    sql_path.write_text(template.replace('__TRACKER_PASSWORD__', password), encoding='utf-8')
    config = {
        'DATABASE_URL': f'postgresql://pm_equipment_app.{args.project_ref}:{password}@{args.pooler_host}:6543/postgres?sslmode=require',
        'DATABASE_SCHEMA': 'equipment_tracker',
    }
    config_path.write_text(json.dumps(config), encoding='utf-8')
    print('Private setup files created in the gitignored instance folder. No credentials displayed.')


if __name__ == '__main__':
    main()
