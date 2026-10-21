import os
import re
from datetime import date, timedelta

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.pop('DATABASE_SCHEMA', None)
os.environ.setdefault('SECRET_KEY', 'local-test-only')

try:
    import pytest
except ModuleNotFoundError:
    import types
    import unittest

    def _passthrough(fn):
        return fn

    pytest = types.SimpleNamespace(fixture=_passthrough)

    class LoginApiTests(unittest.TestCase):
        def test_install_pytest(self):
            self.skipTest('Install requirements-dev.txt before running the login and API tests.')

from app import app, db
from models import Account, EquipmentItem, MaintenanceRecord


def _csrf(page):
    match = re.search(br'name="csrf_token" value="([^"]+)"', page.data)
    assert match, page.data[:400]
    return match.group(1).decode()


def _sign_in(client, username='test-user', password='test-only-password'):
    page = client.get('/login')
    return client.post('/login', data={
        'username': username,
        'password': password,
        'csrf_token': _csrf(page),
    })


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('APP_LOGIN_USER', 'test-user')
    monkeypatch.setenv('APP_LOGIN_PASSWORD', 'test-only-password')
    monkeypatch.setenv('TRACKER_API_TOKEN', 'test-only-token')
    app.config['TESTING'] = True
    context = app.app_context()
    context.push()
    db.drop_all()
    db.create_all()
    account = Account(name='Test site', account_type='client', location='Shop')
    db.session.add(account)
    db.session.commit()
    test_client = app.test_client()
    try:
        yield test_client, account
    finally:
        db.session.remove()
        db.drop_all()
        context.pop()


def _headers(token='test-only-token'):
    return {'Authorization': f'Bearer {token}'}


def test_login_required_and_static_assets_load(client):
    test_client, account = client
    home = test_client.get('/')
    assert home.status_code == 302
    assert '/login' in home.headers['Location']
    machine = test_client.get('/equipment/1')
    assert machine.status_code == 302
    assert '/login' in machine.headers['Location']
    blocked = test_client.post('/equipment/add', data={'name': 'Scrubber', 'account_id': account.id})
    assert blocked.status_code in (302, 400)
    assert EquipmentItem.query.count() == 0

    login_page = test_client.get('/login')
    assert login_page.status_code == 200
    assert b'name="username"' in login_page.data
    assert b'name="password"' in login_page.data
    assert b'/static/css/style.css' in login_page.data
    assert test_client.get('/static/css/style.css').status_code == 200
    assert account.name.encode() not in login_page.data

    assert _sign_in(test_client).status_code == 302
    home = test_client.get('/')
    assert home.status_code == 200
    logged_out = test_client.post('/logout', data={'csrf_token': _csrf(home)})
    assert logged_out.status_code == 302
    assert test_client.get('/').status_code == 302


def test_production_without_login_fails_closed(client, monkeypatch):
    test_client, account = client
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.delenv('APP_LOGIN_PASSWORD', raising=False)
    page = test_client.get('/')
    assert page.status_code == 503
    assert b'Sign-in is not configured' in page.data
    assert account.name.encode() not in page.data
    assert test_client.get('/static/css/style.css').status_code == 200

    monkeypatch.setenv('APP_LOGIN_USER', 'test-user')
    monkeypatch.setenv('APP_LOGIN_PASSWORD', 'test-only-password')
    monkeypatch.delenv('SECRET_KEY', raising=False)
    missing_key = test_client.get('/equipment')
    assert missing_key.status_code == 503
    assert account.name.encode() not in missing_key.data


def test_api_rejects_missing_or_bad_token(client, monkeypatch):
    test_client, _account = client
    monkeypatch.delenv('TRACKER_API_TOKEN', raising=False)
    unconfigured = test_client.get('/api/equipment', headers=_headers('anything'))
    assert unconfigured.status_code == 503
    assert unconfigured.is_json
    assert b'equipment' not in unconfigured.data.lower() or b'not configured' in unconfigured.data.lower()

    monkeypatch.setenv('TRACKER_API_TOKEN', 'test-only-token')
    missing = test_client.get('/api/equipment')
    wrong = test_client.get('/api/equipment', headers=_headers('nope'))
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.is_json and wrong.is_json
    ok = test_client.get('/api/accounts', headers=_headers())
    assert ok.status_code == 200
    assert ok.json['accounts'][0]['name'] == 'Test site'


def test_patch_leaves_untouched_fields_alone(client):
    test_client, account = client
    created = test_client.post('/api/equipment', headers=_headers(), json={
        'name': 'Scrubber',
        'equipment_type': 'Tennant',
        'service_type': 'General Service',
        'account_id': account.id,
        'quantity': 2,
        'status': 'working',
        'serial_number': 'SN-100',
        'service_interval_days': 30,
        'last_service_date': '2026-01-15',
        'notes': 'Keep me',
    })
    assert created.status_code == 201
    item_id = created.json['equipment']['id']
    patched = test_client.patch(f'/api/equipment/{item_id}', headers=_headers(), json={'notes': 'only this'})
    assert patched.status_code == 200
    body = patched.json['equipment']
    assert body['notes'] == 'only this'
    assert body['name'] == 'Scrubber'
    assert body['equipment_type'] == 'Tennant'
    assert body['service_type'] == 'General Service'
    assert body['serial_number'] == 'SN-100'
    assert body['quantity'] == 2
    assert body['status'] == 'working'
    assert body['account_id'] == account.id
    assert body['service_interval_days'] == 30
    assert body['last_service_date'] == '2026-01-15'
    assert body['next_due'] == '2026-02-14'
    rejected = test_client.patch(f'/api/equipment/{item_id}', headers=_headers(), json={'nope': 1})
    assert rejected.status_code == 400
    assert EquipmentItem.query.get(item_id).notes == 'only this'


def test_maintenance_add_updates_last_service_date(client):
    test_client, account = client
    created = test_client.post('/api/equipment', headers=_headers(), json={
        'name': 'Buffer',
        'account_id': account.id,
        'status': 'in_repair',
        'last_service_date': '2020-01-01',
    })
    item_id = created.json['equipment']['id']
    older = test_client.post(f'/api/equipment/{item_id}/maintenance', headers=_headers(), json={
        'maintenance_type': 'Inspection',
        'service_date': '2019-05-01',
        'mark_working': True,
        'vendor': 'Earlier shop',
    })
    assert older.status_code == 201
    assert older.json['equipment']['last_service_date'] == '2020-01-01'
    assert older.json['equipment']['status'] == 'in_repair'
    newer = test_client.post(f'/api/equipment/{item_id}/maintenance', headers=_headers(), json={
        'maintenance_type': 'Filter',
        'service_date': '2026-03-01',
        'mark_working': True,
        'cost': '48.5',
        'vendor': 'Preferred Maintenance',
        'invoice_ref': 'REF-9',
        'notes': 'New hose',
    })
    assert newer.status_code == 201
    assert newer.json['equipment']['last_service_date'] == '2026-03-01'
    assert newer.json['equipment']['status'] == 'working'
    record = newer.json['maintenance']
    assert record['equipment_id'] == item_id
    assert record['cost'] == '48.50'
    assert record['vendor'] == 'Preferred Maintenance'
    assert MaintenanceRecord.query.count() == 2
    detail = test_client.get(f'/api/equipment/{item_id}', headers=_headers())
    assert [row['service_date'] for row in detail.json['maintenance']] == ['2026-03-01', '2019-05-01']


def test_due_endpoint_math(client):
    test_client, account = client
    today = date.today()

    def add(**extra):
        payload = {'name': extra.pop('name'), 'account_id': account.id, 'quantity': 1}
        payload.update(extra)
        response = test_client.post('/api/equipment', headers=_headers(), json=payload)
        assert response.status_code == 201, response.json
        return response.json['equipment']

    overdue = add(
        name='Overdue vacuum',
        last_service_date=(today - timedelta(days=20)).isoformat(),
        service_interval_days=10,
    )
    soon = add(
        name='Soon buffer',
        last_service_date=(today - timedelta(days=1)).isoformat(),
        service_interval_days=10,
    )
    later = add(
        name='Later scrubber',
        last_service_date=today.isoformat(),
        service_interval_days=40,
    )
    repair = add(name='Repair cart', status='in_repair')
    both = add(
        name='Both states',
        status='in_repair',
        last_service_date=(today - timedelta(days=30)).isoformat(),
        service_interval_days=10,
    )
    assert overdue['next_due'] == (today - timedelta(days=10)).isoformat()
    assert soon['next_due'] == (today + timedelta(days=9)).isoformat()

    within_14 = test_client.get('/api/due', headers=_headers())
    assert within_14.status_code == 200
    assert within_14.json['days'] == 14
    by_name = {row['name']: row for row in within_14.json['equipment']}
    assert set(by_name) == {'Overdue vacuum', 'Soon buffer', 'Repair cart', 'Both states'}
    assert by_name['Overdue vacuum']['reasons'] == ['overdue']
    assert by_name['Soon buffer']['reasons'] == ['due_soon']
    assert by_name['Repair cart']['reasons'] == ['in_repair']
    assert by_name['Both states']['reasons'] == ['overdue', 'in_repair']
    assert later['name'] not in by_name

    within_7 = test_client.get('/api/due?days=7', headers=_headers())
    names = {row['name'] for row in within_7.json['equipment']}
    assert 'Soon buffer' not in names
    assert {'Overdue vacuum', 'Repair cart', 'Both states'} <= names
    bad = test_client.get('/api/due?days=nope', headers=_headers())
    assert bad.status_code == 400


def test_machine_page_renders_profile_and_history(client):
    test_client, account = client
    today = date.today()
    item = EquipmentItem(
        name='Wide Buffer',
        equip_id='EQ-0008',
        equipment_type='Tennant',
        service_type='General Service',
        account_id=account.id,
        quantity=1,
        item_status='working',
        last_service_date=today - timedelta(days=40),
        service_interval_days=30,
        serial_number='SN-440',
        purchase_date=date(2022, 5, 2),
        notes='Left closet',
    )
    db.session.add(item)
    db.session.flush()
    db.session.add(MaintenanceRecord(
        equipment_id=item.id,
        maintenance_type='Hose',
        service_date=today - timedelta(days=40),
        notes='Older visit',
        vendor='Shop A',
        cost='10.00',
        invoice_ref='A-1',
    ))
    db.session.add(MaintenanceRecord(
        equipment_id=item.id,
        maintenance_type='Filter',
        service_date=today - timedelta(days=5),
        notes='Newer visit',
        vendor='Shop B',
        cost='22.25',
        invoice_ref='B-2',
    ))
    db.session.commit()
    hidden = test_client.get(f'/equipment/{item.id}')
    assert hidden.status_code == 302

    assert _sign_in(test_client).status_code == 302
    page = test_client.get(f'/equipment/{item.id}')
    assert page.status_code == 200
    body = page.data.decode()
    assert 'Wide Buffer' in body
    assert 'SN-440' in body
    assert 'Left closet' in body
    assert 'Overdue' in body
    assert 'Shop B' in body and 'Shop A' in body
    assert body.index('Newer visit') < body.index('Older visit')
    assert f'equipment_id={item.id}' in body
    assert f'/equipment/edit/{item.id}' in body
    assert 'Copy link' in body
    assert f'/equipment/{item.id}' in body


def test_login_lockout_uses_the_database(client, monkeypatch):
    test_client, _account = client
    monkeypatch.setattr('security.IP_FAILURE_LIMIT', 3)
    monkeypatch.setattr('security.GLOBAL_FAILURE_LIMIT', 100)
    for _ in range(2):
        failed = _sign_in(test_client, password='wrong-password')
        assert failed.status_code == 401
    locked = _sign_in(test_client, password='wrong-password')
    assert locked.status_code == 429
    assert b'Too many sign-in attempts' in locked.data
    still_locked = _sign_in(test_client)
    assert still_locked.status_code == 429
    from models import LoginLockout
    LoginLockout.query.delete()
    db.session.commit()
    assert _sign_in(test_client).status_code == 302
