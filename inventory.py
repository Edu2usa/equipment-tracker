"""Shared equipment and maintenance rules for the website and the JSON API."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from models import (
    Account,
    EquipmentItem,
    EquipmentName,
    EquipmentServiceType,
    EquipmentType,
    MaintenanceRecord,
    db,
)

VALID_STATUSES = ('working', 'in_repair', 'in_storage')
EQUIPMENT_FIELDS = {
    'name',
    'equipment_type',
    'service_type',
    'account_id',
    'quantity',
    'item_status',
    'last_service_date',
    'service_interval_days',
    'serial_number',
    'purchase_date',
    'notes',
}
MAINTENANCE_FIELDS = {
    'maintenance_type',
    'service_date',
    'notes',
    'cost',
    'vendor',
    'invoice_ref',
    'mark_working',
    'equipment_id',
}
MAX_INTERVAL_DAYS = 3650
MAX_DUE_WINDOW_DAYS = 365
MAX_COST = Decimal('99999999.99')


class FieldError(ValueError):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def remember_option(model, value):
    value = (value or '').strip()
    if value and not model.query.filter_by(name=value).first():
        db.session.add(model(name=value))


def like_contains(value):
    escaped = (value or '').replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _text(value, label, max_len, required=False):
    if _blank(value):
        if required:
            raise FieldError(f'{label} is required.')
        return None
    text = str(value).strip()
    if len(text) > max_len:
        raise FieldError(f'{label} is too long.')
    return text


def _date(value, label):
    if _blank(value):
        return None
    if isinstance(value, date):
        return value
    raw = str(value).strip()[:10]
    try:
        year, month, day = (int(part) for part in raw.split('-'))
        return date(year, month, day)
    except (TypeError, ValueError):
        raise FieldError(f'{label} must be a date in YYYY-MM-DD form.')


def _quantity(value):
    if isinstance(value, bool) or isinstance(value, float):
        raise FieldError('Quantity must be a positive whole number.')
    try:
        quantity = int(str(value).strip())
    except (TypeError, ValueError):
        raise FieldError('Quantity must be a positive whole number.')
    if quantity < 1:
        raise FieldError('Quantity must be a positive whole number.')
    return quantity


def _status(value):
    if _blank(value) or str(value).strip() not in VALID_STATUSES:
        raise FieldError('Status must be working, in_repair, or in_storage.')
    return str(value).strip()


def _account_id(value):
    if isinstance(value, bool):
        raise FieldError('Choose an account from the list.')
    try:
        account_id = int(str(value).strip())
    except (TypeError, ValueError):
        raise FieldError('Choose an account from the list.')
    if Account.query.get(account_id) is None:
        raise FieldError('Selected account no longer exists. Choose an account from the list.')
    return account_id


def _interval(value):
    if _blank(value):
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise FieldError('Service interval must be a positive whole number of days.')
    try:
        days = int(str(value).strip())
    except (TypeError, ValueError):
        raise FieldError('Service interval must be a positive whole number of days.')
    if days < 1 or days > MAX_INTERVAL_DAYS:
        raise FieldError('Service interval must be a positive whole number of days.')
    return days


def _cost(value):
    if _blank(value):
        return None
    if isinstance(value, bool):
        raise FieldError('Cost must be a number that is zero or greater.')
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise FieldError('Cost must be a number that is zero or greater.')
    if amount < 0 or amount > MAX_COST:
        raise FieldError('Cost must be a number that is zero or greater.')
    return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _mark_working(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'yes', 'true', '1', 'on'}


def _iso(value):
    if value is None:
        return None
    return value.isoformat()


def _money(value):
    if value is None:
        return None
    return format(Decimal(value).quantize(Decimal('0.01')), 'f')


def parse_due_days(value, default=14):
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        raise FieldError('days must be a whole number from 0 through 365.')
    try:
        days = int(str(value).strip())
    except (TypeError, ValueError):
        raise FieldError('days must be a whole number from 0 through 365.')
    if days < 0 or days > MAX_DUE_WINDOW_DAYS:
        raise FieldError('days must be a whole number from 0 through 365.')
    return days


def cleaned_equipment_changes(payload, partial):
    if not isinstance(payload, dict):
        raise FieldError('Send the equipment fields as a JSON object.')
    data = dict(payload)
    if 'status' in data:
        if 'item_status' in data and str(data['status']).strip() != str(data['item_status']).strip():
            raise FieldError('Send status once.')
        data['item_status'] = data.pop('status')
    unknown = sorted(set(data) - EQUIPMENT_FIELDS)
    if unknown:
        raise FieldError('Unknown field: ' + ', '.join(unknown) + '.')
    if not partial:
        data.setdefault('equipment_type', '')
        data.setdefault('service_type', '')
        data.setdefault('quantity', 1)
        data.setdefault('item_status', 'working')
        data.setdefault('last_service_date', None)
        data.setdefault('service_interval_days', None)
        data.setdefault('serial_number', None)
        data.setdefault('purchase_date', None)
        data.setdefault('notes', None)
        if 'name' not in data or 'account_id' not in data:
            raise FieldError('Equipment name and account are required.')
    changes = {}
    if 'name' in data:
        if _blank(data.get('name')):
            raise FieldError('Equipment name and account are required.')
        changes['name'] = _text(data.get('name'), 'Equipment name', 120, required=True)
    if 'equipment_type' in data:
        changes['equipment_type'] = _text(data.get('equipment_type'), 'Model', 80) or 'N/A'
    if 'service_type' in data:
        changes['service_type'] = _text(data.get('service_type'), 'Service type', 80)
    if 'account_id' in data:
        changes['account_id'] = _account_id(data.get('account_id'))
    if 'quantity' in data:
        changes['quantity'] = _quantity(data.get('quantity'))
    if 'item_status' in data:
        changes['item_status'] = _status(data.get('item_status'))
    if 'last_service_date' in data:
        changes['last_service_date'] = _date(data.get('last_service_date'), 'Last service date')
    if 'service_interval_days' in data:
        changes['service_interval_days'] = _interval(data.get('service_interval_days'))
    if 'serial_number' in data:
        changes['serial_number'] = _text(data.get('serial_number'), 'Serial number', 120)
    if 'purchase_date' in data:
        changes['purchase_date'] = _date(data.get('purchase_date'), 'Purchase date')
    if 'notes' in data:
        changes['notes'] = _text(data.get('notes'), 'Notes', 8000)
    return changes


def _remember_equipment(changes):
    if 'name' in changes:
        remember_option(EquipmentName, changes['name'])
    if changes.get('equipment_type'):
        remember_option(EquipmentType, changes['equipment_type'])
    if changes.get('service_type'):
        remember_option(EquipmentServiceType, changes['service_type'])


def create_equipment(payload):
    changes = cleaned_equipment_changes(payload, partial=False)
    item = EquipmentItem(**changes)
    _remember_equipment(changes)
    db.session.add(item)
    db.session.flush()
    item.equip_id = f'EQ-{item.id:04d}'
    return item


def update_equipment(item, payload, partial):
    changes = cleaned_equipment_changes(payload, partial=partial)
    for key, value in changes.items():
        setattr(item, key, value)
    _remember_equipment(changes)
    return item


def add_maintenance_record(equipment, payload):
    if not isinstance(payload, dict):
        raise FieldError('Send the maintenance fields as a JSON object.')
    unknown = sorted(set(payload) - MAINTENANCE_FIELDS)
    if unknown:
        raise FieldError('Unknown field: ' + ', '.join(unknown) + '.')
    supplied_equipment = payload.get('equipment_id')
    if 'equipment_id' in payload and supplied_equipment not in (None, ''):
        if str(supplied_equipment).strip() != str(equipment.id):
            raise FieldError('A maintenance record always belongs to one machine.')
    maintenance_type = _text(payload.get('maintenance_type'), 'Maintenance type', 80, required=True)
    service_date = _date(payload.get('service_date'), 'Service date')
    if not maintenance_type or service_date is None:
        raise FieldError('Enter a service type and a valid service date.')
    record = MaintenanceRecord(
        equipment_id=equipment.id,
        maintenance_type=maintenance_type,
        service_date=service_date,
        notes=_text(payload.get('notes'), 'Notes', 8000) if 'notes' in payload else None,
        cost=_cost(payload.get('cost')) if 'cost' in payload else None,
        vendor=_text(payload.get('vendor'), 'Vendor', 120) if 'vendor' in payload else None,
        invoice_ref=_text(payload.get('invoice_ref'), 'Invoice or reference', 120) if 'invoice_ref' in payload else None,
    )
    db.session.add(record)
    if equipment.last_service_date is None or service_date > equipment.last_service_date:
        equipment.last_service_date = service_date
        if _mark_working(payload.get('mark_working')):
            equipment.item_status = 'working'
    return record


def equipment_json(item):
    account = item.account
    return {
        'id': item.id,
        'equip_id': item.equip_id,
        'name': item.name,
        'equipment_type': item.equipment_type,
        'service_type': item.service_type,
        'serial_number': item.serial_number,
        'purchase_date': _iso(item.purchase_date),
        'notes': item.notes,
        'quantity': item.quantity,
        'status': item.item_status,
        'account_id': item.account_id,
        'account': account.name if account else None,
        'location': account.location if account else None,
        'last_service_date': _iso(item.last_service_date),
        'service_interval_days': item.service_interval_days,
        'next_due': _iso(item.next_due),
        'url': f'/equipment/{item.id}',
    }


def maintenance_json(record):
    created = record.created_at.isoformat(timespec='seconds') if record.created_at else None
    return {
        'id': record.id,
        'equipment_id': record.equipment_id,
        'maintenance_type': record.maintenance_type,
        'service_date': _iso(record.service_date),
        'notes': record.notes,
        'cost': _money(record.cost),
        'vendor': record.vendor,
        'invoice_ref': record.invoice_ref,
        'created_at': created,
    }


def due_reasons(item, days, today=None):
    today = today or date.today()
    reasons = []
    nxt = item.next_due
    if nxt is not None and nxt <= today + timedelta(days=days):
        reasons.append('overdue' if nxt < today else 'due_soon')
    if item.item_status == 'in_repair':
        reasons.append('in_repair')
    return reasons


def due_summary(item, today=None, soon_days=14):
    today = today or date.today()
    nxt = item.next_due
    if nxt is None:
        state = 'unscheduled'
        days_away = None
    elif nxt < today:
        state = 'overdue'
        days_away = (today - nxt).days
    elif nxt <= today + timedelta(days=soon_days):
        state = 'due_soon'
        days_away = (nxt - today).days
    else:
        state = 'ok'
        days_away = (nxt - today).days
    return {
        'state': state,
        'next_due': nxt,
        'days': days_away,
        'soon_days': soon_days,
    }


def equipment_search_filter(term):
    pattern = like_contains(term)
    return db.or_(
        EquipmentItem.name.ilike(pattern, escape='\\'),
        EquipmentItem.equipment_type.ilike(pattern, escape='\\'),
        EquipmentItem.service_type.ilike(pattern, escape='\\'),
        EquipmentItem.equip_id.ilike(pattern, escape='\\'),
        EquipmentItem.serial_number.ilike(pattern, escape='\\'),
    )


def find_account_filter(account_value, strict):
    """Return an account id, or None when the filter is empty.

    The website ignores a non-numeric filter after a flash. The API rejects it.
    """
    raw = (account_value or '').strip()
    if not raw:
        return None
    if raw.isdigit():
        if strict and Account.query.get(int(raw)) is None:
            raise FieldError('No account matches that filter.')
        return int(raw)
    if strict:
        account = Account.query.filter(db.func.lower(Account.name) == raw.lower()).first()
        if account is None:
            raise FieldError('No account matches that filter.')
        return account.id
    return False


def maintenance_history(item):
    return (
        MaintenanceRecord.query
        .filter_by(equipment_id=item.id)
        .order_by(MaintenanceRecord.service_date.desc(), MaintenanceRecord.id.desc())
        .all()
    )
