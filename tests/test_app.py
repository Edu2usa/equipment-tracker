import os
import unittest
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'local-test-only'
from app import app, db, initialize_database
from models import Account, EquipmentItem, MaintenanceRecord
from datetime import date
from sqlalchemy.exc import OperationalError


class EquipmentTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.context = app.app_context()
        self.context.push()
        db.create_all()
        self.client = app.test_client()
        self.account = Account(name='Test site', account_type='client', location='Brookfield')
        db.session.add(self.account)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def add_item(self, **overrides):
        data = dict(name='Scrubber', account_id=str(self.account.id), quantity='2', item_status='working')
        data.update(overrides)
        return self.client.post('/equipment/add', data=data, follow_redirects=True)

    def test_all_main_pages_render(self):
        for path in ('/', '/accounts', '/equipment', '/maintenance', '/reports', '/settings', '/equipment/add', '/accounts/add', '/maintenance/add'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_add_blank_model_and_filter(self):
        self.assertEqual(self.add_item().status_code, 200)
        item = EquipmentItem.query.one()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.equipment_type, 'N/A')
        self.assertTrue(item.equip_id.startswith('EQ-'))
        self.assertIn(b'Scrubber', self.client.get('/equipment?search=Scrub').data)
        self.assertNotIn(b'Scrubber', self.client.get('/equipment?status=in_repair').data)

    def test_invalid_quantities_and_status_do_not_save(self):
        for quantity in ('-1', '0', '1.5', 'no'):
            self.add_item(quantity=quantity)
        self.add_item(item_status='invalid')
        self.add_item(last_service_date='not-a-date')
        self.assertEqual(EquipmentItem.query.count(), 0)

    def test_invalid_filter_does_not_crash(self):
        self.assertEqual(self.client.get('/equipment?account=bad').status_code, 200)

    def test_transfer_preserves_quantity(self):
        self.add_item()
        item = EquipmentItem.query.one()
        destination = Account(name='Warehouse', account_type='warehouse', location='')
        db.session.add(destination)
        db.session.commit()
        response = self.client.post(f'/equipment/transfer/{item.id}', data={'account_id': destination.id})
        self.assertEqual(response.status_code, 302)
        db.session.refresh(item)
        self.assertEqual(item.account_id, destination.id)
        self.assertEqual(item.quantity, 2)

    def test_delete_equipment_removes_related_history(self):
        self.add_item()
        item = EquipmentItem.query.one()
        db.session.add(MaintenanceRecord(equipment_id=item.id, maintenance_type='Filter', service_date=date.today()))
        db.session.commit()
        self.assertEqual(self.client.post(f'/equipment/delete/{item.id}').status_code, 302)
        self.assertEqual(EquipmentItem.query.count(), 0)
        self.assertEqual(MaintenanceRecord.query.count(), 0)

    def test_initialization_preserves_user_data(self):
        self.add_item(name='QA real equipment')
        self.account.name = 'BELIMO'
        self.account.account_type = 'warehouse'
        db.session.commit()
        initialize_database()
        initialize_database()
        self.assertEqual(EquipmentItem.query.count(), 1)
        self.assertEqual(Account.query.filter_by(name='BELIMO').one().account_type, 'warehouse')

    def test_database_failure_is_clear_and_redacted(self):
        with patch.object(db.session, 'query', side_effect=OperationalError('secret statement', {}, Exception('secret password'))):
            result = self.client.get('/')
        self.assertEqual(result.status_code, 503)
        self.assertIn(b'cannot reach your equipment records', result.data)
        self.assertNotIn(b'secret password', result.data)

    def test_repair_watch_and_status_navigation(self):
        self.add_item(item_status='in_repair')
        page = self.client.get('/').data
        self.assertIn(b'Repair watch', page)
        self.assertIn(b'Scrubber', page)
        self.assertIn(b'status=in_repair', page)

    def test_missing_maintenance_inputs_do_not_crash(self):
        self.add_item()
        item = EquipmentItem.query.one()
        self.assertEqual(self.client.post('/maintenance/add', data={'equipment_id': item.id}).status_code, 200)
        self.assertEqual(MaintenanceRecord.query.count(), 0)

    def test_missing_production_database_is_not_fake_inventory(self):
        with patch('app.PERSISTENT_DATABASE_CONFIGURED', False):
            result = self.client.get('/')
            self.assertEqual(result.status_code, 503)
            self.assertIn(b'Connect a shared database', result.data)
            self.assertEqual(self.client.get('/static/css/style.css').status_code, 200)

    def test_edit_equipment_saves_and_rejects_negative_quantity(self):
        self.add_item()
        item = EquipmentItem.query.one()
        data = dict(name='Scrubber', account_id=self.account.id, quantity='3', item_status='in_storage')
        self.assertEqual(self.client.post(f'/equipment/edit/{item.id}', data=data).status_code, 302)
        db.session.refresh(item)
        self.assertEqual(item.quantity, 3)
        self.assertEqual(item.item_status, 'in_storage')
        data['quantity'] = '-5'
        self.client.post(f'/equipment/edit/{item.id}', data=data)
        db.session.refresh(item)
        self.assertEqual(item.quantity, 3)


if __name__ == '__main__':
    unittest.main()
