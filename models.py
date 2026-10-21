from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
from sqlalchemy import MetaData
from database_config import database_schema

db = SQLAlchemy(metadata=MetaData(schema=database_schema(os.environ.get('DATABASE_SCHEMA'))))


class Account(db.Model):
    __tablename__ = 'accounts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    account_type = db.Column(db.String(50), nullable=False)  # client, warehouse, spare_pool
    location = db.Column(db.String(120), nullable=False, default='')
    equipment_items = db.relationship('EquipmentItem', backref='account', lazy=True,
                                      foreign_keys='EquipmentItem.account_id')

    def equipment_count(self):
        return sum(e.quantity for e in self.equipment_items)


class EquipmentItem(db.Model):
    __tablename__ = 'equipment_items'
    id = db.Column(db.Integer, primary_key=True)
    equip_id = db.Column(db.String(20), nullable=True, unique=True)  # e.g. EQ-0001
    name = db.Column(db.String(120), nullable=False)
    equipment_type = db.Column(db.String(80), nullable=False)  # UI label: Equipment Model
    service_type = db.Column(db.String(80), nullable=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    item_status = db.Column(db.String(50), default='working')  # working, in_repair, in_storage
    last_service_date = db.Column(db.Date, nullable=True)
    service_interval_days = db.Column(db.Integer, nullable=True)
    serial_number = db.Column(db.String(120), nullable=True)
    purchase_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    maintenance_records = db.relationship('MaintenanceRecord', backref='equipment', lazy=True)

    @property
    def next_due(self):
        if self.last_service_date is None or not self.service_interval_days:
            return None
        return self.last_service_date + timedelta(days=int(self.service_interval_days))


class MaintenanceRecord(db.Model):
    __tablename__ = 'maintenance_records'
    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment_items.id'), nullable=False)
    maintenance_type = db.Column(db.String(80), nullable=False)
    service_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    cost = db.Column(db.Numeric(12, 2), nullable=True)
    vendor = db.Column(db.String(120), nullable=True)
    invoice_ref = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class EquipmentName(db.Model):
    __tablename__ = 'equipment_names'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)


class EquipmentType(db.Model):
    __tablename__ = 'equipment_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)


class EquipmentServiceType(db.Model):
    __tablename__ = 'equipment_service_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)


class LoginLockout(db.Model):
    """Failed sign-in counters. One row per network and one global row.

    Stored in the database so Vercel instances share the same lockout.
    """
    __tablename__ = 'login_lockouts'
    id = db.Column(db.Integer, primary_key=True)
    bucket = db.Column(db.String(16), nullable=False)
    bucket_key = db.Column(db.String(64), nullable=False)
    failures = db.Column(db.Integer, nullable=False, default=0)
    window_started = db.Column(db.DateTime, nullable=True)
    locked_until = db.Column(db.DateTime, nullable=True)
    lockout_level = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint('bucket', 'bucket_key', name='login_lockouts_bucket_key'),
    )
