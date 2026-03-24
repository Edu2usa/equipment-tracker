from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Account(db.Model):
    __tablename__ = 'accounts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    account_type = db.Column(db.String(50), nullable=False)  # client, warehouse, spare_pool
    location = db.Column(db.String(120), nullable=False)
    equipment_items = db.relationship('EquipmentItem', backref='account', lazy=True,
                                      foreign_keys='EquipmentItem.account_id')

    def equipment_count(self):
        return sum(e.quantity for e in self.equipment_items)


class EquipmentItem(db.Model):
    __tablename__ = 'equipment_items'
    id = db.Column(db.Integer, primary_key=True)
    equip_id = db.Column(db.String(20), nullable=True, unique=True)  # e.g. EQ-0001
    name = db.Column(db.String(120), nullable=False)
    equipment_type = db.Column(db.String(80), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    item_status = db.Column(db.String(50), default='working')  # working, in_repair, in_storage
    last_service_date = db.Column(db.Date, nullable=True)
    maintenance_records = db.relationship('MaintenanceRecord', backref='equipment', lazy=True)


class MaintenanceRecord(db.Model):
    __tablename__ = 'maintenance_records'
    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment_items.id'), nullable=False)
    maintenance_type = db.Column(db.String(80), nullable=False)
    service_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
