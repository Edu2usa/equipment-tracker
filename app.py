from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, Account, EquipmentItem, MaintenanceRecord, EquipmentName, EquipmentType, EquipmentServiceType
from datetime import datetime, date
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'preferred-maintenance-secret-key'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Use a hosted Postgres URL in production. Local development may use SQLite,
# but Vercel serverless instances do not share /tmp, so SQLite there splits data.
_raw_db_url = (
    os.environ.get('DATABASE_URL')
    or os.environ.get('POSTGRES_URL')
    or os.environ.get('POSTGRES_PRISMA_URL')
    or os.environ.get('POSTGRES_URL_NON_POOLING')
)
_running_on_serverless = any(
    os.environ.get(key)
    for key in (
        'VERCEL',
        'VERCEL_ENV',
        'VERCEL_URL',
        'VERCEL_REGION',
        'NOW_REGION',
        'AWS_REGION',
        'AWS_EXECUTION_ENV',
        'AWS_LAMBDA_FUNCTION_NAME',
        'LAMBDA_TASK_ROOT',
    )
)
_allow_sqlite_in_serverless = os.environ.get('ALLOW_SQLITE_IN_SERVERLESS') == '1'
PERSISTENT_DATABASE_CONFIGURED = bool(_raw_db_url) or not _running_on_serverless or _allow_sqlite_in_serverless
_db_url = _raw_db_url or ('sqlite:////tmp/equip_tracker.db' if _running_on_serverless else 'sqlite:///equip_tracker.db')
# Normalize hosted Postgres URLs for SQLAlchemy and pg8000.
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
if _db_url.startswith('postgresql://'):
    _db_url = _db_url.replace('postgresql://', 'postgresql+pg8000://', 1)
if _db_url.startswith('postgresql+pg8000://'):
    _url_parts = urlsplit(_db_url)
    _query_pairs = parse_qsl(_url_parts.query, keep_blank_values=True)
    _remaining_query = []
    _ssl_required = False
    _pg8000_query_keys = {'timeout', 'tcp_keepalive', 'application_name'}
    for key, value in _query_pairs:
        if key == 'sslmode':
            _ssl_required = value in ('require', 'verify-ca', 'verify-full')
            continue
        if key in _pg8000_query_keys:
            _remaining_query.append((key, value))
    if _ssl_required:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'connect_args': {
                'ssl_context': True,
            },
        }
    _db_url = urlunsplit(_url_parts._replace(query=urlencode(_remaining_query)))
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url

db.init_app(app)


@app.before_request
def require_persistent_database_in_production():
    if PERSISTENT_DATABASE_CONFIGURED or request.endpoint == 'static':
        return None
    return render_template('database_required.html'), 503

# ── Default seed data ─────────────────────────────────────────────────────────

DEFAULT_EQUIP_NAMES = [
    "Canister Vacuum", "Backpack Vacuum - Cord", "Backpack Vacuum - Battery",
    "Barrel Vacuum - Solo", "Barrel Vacuum - Double", "Barrel Vacuum - Cart",
    "Narrow Buffer", "Wide Buffer", "Extractor", "Scrubber",
    "Walk-Behind Scrubber", "Ride-On Scrubber", "Mop Bucket", "Maid Cart",
    "Ladder", "Fan", "Other",
]

DEFAULT_EQUIP_MODELS = [
    "Tennant", "Nobles", "ProTeam", "Hoover", "Sanitaire", "Nilfisk",
    "Clarke", "Advance", "Karcher", "Other",
]

DEFAULT_SERVICE_TYPES = [
    "General Service", "Batteries", "Hose", "Filter", "Brush", "Pad Driver",
    "Squeegee", "Belt", "Motor", "Charger", "Other",
]

DEFAULT_ACCOUNTS = [
    ("100 MILL PLAIN", "client"),
    ("170 / 164", "client"),
    ("20 GERMANTOWN", "client"),
    ("235 Main", "client"),
    ("33 GERMANTOWN", "client"),
    ("79 SAND PIT", "client"),
    ("ANN'S PLACE", "client"),
    ("BELIMO", "client"),
    ("BRANSON", "client"),
    ("BRIDPORT SURGICAL", "client"),
    ("CCATS", "client"),
    ("COMM CTR", "client"),
    ("DAVITTA", "client"),
    ("DERM ASSOC", "client"),
    ("DHMAC", "client"),
    ("DR. CIGNO", "client"),
    ("ENTEGRIS", "client"),
    ("ETHAN ALLEN", "client"),
    ("GL RIDGEFIELD", "client"),
    ("GOLD GARAGE", "client"),
    ("IMMACULATE", "client"),
    ("MANNKIND", "client"),
    ("MAPLEWOOD", "client"),
    ("MITCHELL WDBRY", "client"),
    ("MOTION PT", "client"),
    ("NEWT REHAB", "client"),
    ("NORTHEAST", "client"),
    ("RIDGEFIELD DIAGNOSTIC", "client"),
    ("RESONETICS", "client"),
    ("SHERMAN SCHOOL", "client"),
    ("SOMERS", "client"),
    ("UROLOGY ASSOC", "client"),
    ("VNA", "client"),
    ("WILTON SURG", "client"),
    ("Special", "spare_pool"),
]


def normalized_text(value):
    return " ".join((value or "").strip().casefold().split())


def find_duplicate_account(name, exclude_id=None):
    normalized_name = normalized_text(name)
    query = Account.query
    if exclude_id is not None:
        query = query.filter(Account.id != exclude_id)
    for account in query.all():
        if normalized_text(account.name) == normalized_name:
            return account
    return None


with app.app_context():
    if not PERSISTENT_DATABASE_CONFIGURED:
        # Do not create a misleading per-instance SQLite database in production.
        pass
    else:
        db.create_all()
        # Migration: add equip_id column if it doesn't exist
        with db.engine.connect() as conn:
            for statement in (
                "ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS equip_id VARCHAR(20)",
                "ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS service_type VARCHAR(80)",
            ):
                try:
                    conn.execute(db.text(statement))
                    conn.commit()
                except Exception:
                    conn.rollback()
        # Backfill equip_id for any existing rows that lack it
        items_without_id = EquipmentItem.query.filter(EquipmentItem.equip_id == None).all()
        for item in items_without_id:
            item.equip_id = f"EQ-{item.id:04d}"
        if items_without_id:
            db.session.commit()
        # Seed equipment names, models, and service types.
        for n in DEFAULT_EQUIP_NAMES:
            if not EquipmentName.query.filter_by(name=n).first():
                db.session.add(EquipmentName(name=n))
        for t in DEFAULT_EQUIP_MODELS:
            if not EquipmentType.query.filter_by(name=t).first():
                db.session.add(EquipmentType(name=t))
        for service_type in DEFAULT_SERVICE_TYPES:
            if not EquipmentServiceType.query.filter_by(name=service_type).first():
                db.session.add(EquipmentServiceType(name=service_type))
        for account_name, account_type in DEFAULT_ACCOUNTS:
            existing_account = find_duplicate_account(account_name)
            if existing_account:
                existing_account.name = account_name
                existing_account.account_type = account_type
            else:
                db.session.add(Account(name=account_name, account_type=account_type, location=''))
        db.session.commit()

def get_equip_names():
    return [r.name for r in EquipmentName.query.order_by(EquipmentName.name).all()]

def get_equip_types():
    return [r.name for r in EquipmentType.query.order_by(EquipmentType.name).all()]


def get_service_types():
    return [r.name for r in EquipmentServiceType.query.order_by(EquipmentServiceType.name).all()]


def remember_option(model, value):
    value = (value or "").strip()
    if value and not model.query.filter_by(name=value).first():
        db.session.add(model(name=value))


# ─── Dashboard ───────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    total = db.session.query(db.func.sum(EquipmentItem.quantity)).scalar() or 0
    working = db.session.query(db.func.sum(EquipmentItem.quantity)).filter_by(item_status='working').scalar() or 0
    in_repair = db.session.query(db.func.sum(EquipmentItem.quantity)).filter_by(item_status='in_repair').scalar() or 0
    in_storage = db.session.query(db.func.sum(EquipmentItem.quantity)).filter_by(item_status='in_storage').scalar() or 0

    recently_repaired = (
        MaintenanceRecord.query
        .order_by(MaintenanceRecord.service_date.desc())
        .limit(10)
        .all()
    )
    accounts = Account.query.all()
    equipment_list = EquipmentItem.query.all()
    return render_template('dashboard.html',
                           total=total, working=working,
                           in_repair=in_repair, in_storage=in_storage,
                           recently_repaired=recently_repaired,
                           accounts=accounts,
                           equipment_list=equipment_list)


# ─── Accounts ────────────────────────────────────────────────────────────────

@app.route('/accounts')
def accounts():
    all_accounts = Account.query.order_by(Account.name).all()
    return render_template('accounts.html', accounts=all_accounts)


@app.route('/accounts/add', methods=['GET', 'POST'])
def add_account():
    if request.method == 'POST':
        name = request.form['name'].strip()
        account_type = request.form['account_type']
        location = request.form['location'].strip()
        if not name:
            flash('Account name is required.', 'error')
            return render_template('account_form.html', action='Add', account=None)
        duplicate = find_duplicate_account(name)
        if duplicate:
            flash(f'Account "{duplicate.name}" already exists. Use Edit instead of adding a duplicate.', 'warning')
            return redirect(url_for('accounts'))
        acct = Account(name=name, account_type=account_type, location=location)
        db.session.add(acct)
        db.session.commit()
        flash(f'Account "{name}" added successfully.', 'success')
        return redirect(url_for('accounts'))
    return render_template('account_form.html', action='Add', account=None)


@app.route('/accounts/edit/<int:account_id>', methods=['GET', 'POST'])
@app.route('/accounts/<int:account_id>/edit', methods=['GET', 'POST'])
def edit_account(account_id):
    acct = Account.query.get(account_id)
    if not acct:
        if Account.query.count() == 0:
            flash('No accounts exist yet. Add an account first, then you can edit it.', 'warning')
            return redirect(url_for('add_account'))
        flash('That account no longer exists. Choose an account from the list below.', 'warning')
        return redirect(url_for('accounts'))
    if request.method == 'POST':
        acct.name = request.form['name'].strip()
        acct.account_type = request.form['account_type']
        acct.location = request.form['location'].strip()
        if not acct.name:
            flash('Account name is required.', 'error')
            return render_template('account_form.html', action='Edit', account=acct)
        duplicate = find_duplicate_account(acct.name, exclude_id=acct.id)
        if duplicate:
            flash(f'Account "{duplicate.name}" already exists. Merge or edit the existing account instead.', 'warning')
            return redirect(url_for('accounts'))
        db.session.commit()
        flash(f'Account "{acct.name}" updated.', 'success')
        return redirect(url_for('accounts'))
    return render_template('account_form.html', action='Edit', account=acct)


@app.route('/accounts/delete/<int:account_id>', methods=['GET', 'POST'])
@app.route('/accounts/<int:account_id>/delete', methods=['GET', 'POST'])
def delete_account(account_id):
    acct = Account.query.get(account_id)
    if not acct:
        if Account.query.count() == 0:
            flash('No accounts exist yet. Add an account first.', 'warning')
            return redirect(url_for('add_account'))
        flash('That account was not found. It may have already been deleted.', 'warning')
        return redirect(url_for('accounts'))
    if request.method == 'GET':
        flash('Use the Delete button on an account row to confirm deletion.', 'error')
        return redirect(url_for('accounts'))
    if acct.equipment_items:
        flash('Cannot delete account with equipment assigned.', 'error')
        return redirect(url_for('accounts'))
    db.session.delete(acct)
    db.session.commit()
    flash('Account deleted.', 'success')
    return redirect(url_for('accounts'))


# ─── Equipment ───────────────────────────────────────────────────────────────

@app.route('/equipment')
def equipment():
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')
    account_filter = request.args.get('account', '')

    query = EquipmentItem.query
    if search:
        query = query.filter(
            db.or_(
                EquipmentItem.name.ilike(f'%{search}%'),
                EquipmentItem.equipment_type.ilike(f'%{search}%'),
                EquipmentItem.service_type.ilike(f'%{search}%'),
            )
        )
    if status_filter:
        query = query.filter_by(item_status=status_filter)
    if account_filter:
        query = query.filter_by(account_id=int(account_filter))

    items = query.order_by(EquipmentItem.name).all()
    accounts = Account.query.order_by(Account.name).all()
    return render_template('equipment.html', items=items, accounts=accounts,
                           search=search, status_filter=status_filter,
                           account_filter=account_filter)


@app.route('/equipment/add', methods=['GET', 'POST'])
def add_equipment():
    accounts = Account.query.order_by(Account.name).all()
    equip_names = get_equip_names()
    equip_types = get_equip_types()
    service_types = get_service_types()
    if request.method == 'POST':
        name = (request.form.get('custom_name') or request.form.get('name') or '').strip()
        equipment_type = (request.form.get('custom_equipment_type') or request.form.get('equipment_type') or '').strip()
        service_type = (request.form.get('custom_service_type') or request.form.get('service_type') or '').strip()
        account_id_raw = request.form.get('account_id', '').strip()
        quantity_raw = request.form.get('quantity', '1').strip()
        item_status = request.form.get('item_status', 'working')
        last_service_raw = request.form.get('last_service_date', '').strip()

        if not name or not equipment_type or not account_id_raw:
            flash('Equipment name, model, and account are required.', 'error')
            return render_template('equipment_form.html', action='Add', item=None,
                                   accounts=accounts, equip_names=equip_names,
                                   equip_types=equip_types, service_types=service_types)

        try:
            account_id = int(account_id_raw)
            quantity = int(quantity_raw) if quantity_raw else 1
        except ValueError:
            flash('Invalid account or quantity value.', 'error')
            return render_template('equipment_form.html', action='Add', item=None,
                                   accounts=accounts, equip_names=equip_names,
                                   equip_types=equip_types, service_types=service_types)

        if not Account.query.get(account_id):
            flash('Selected account no longer exists. Choose an account from the list.', 'error')
            accounts = Account.query.order_by(Account.name).all()
            return render_template('equipment_form.html', action='Add', item=None,
                                   accounts=accounts, equip_names=equip_names,
                                   equip_types=equip_types, service_types=service_types)

        last_service = None
        if last_service_raw:
            try:
                last_service = datetime.strptime(last_service_raw, '%Y-%m-%d').date()
            except ValueError:
                pass

        item = EquipmentItem(
            name=name, equipment_type=equipment_type, service_type=service_type,
            account_id=account_id, quantity=quantity,
            item_status=item_status, last_service_date=last_service
        )
        remember_option(EquipmentName, name)
        remember_option(EquipmentType, equipment_type)
        remember_option(EquipmentServiceType, service_type)
        db.session.add(item)
        db.session.flush()
        item.equip_id = f"EQ-{item.id:04d}"
        db.session.commit()
        flash(f'Equipment "{name}" added (ID: {item.equip_id}).', 'success')
        return redirect(url_for('equipment'))

    return render_template('equipment_form.html', action='Add', item=None,
                           accounts=accounts, equip_names=equip_names,
                           equip_types=equip_types, service_types=service_types)


@app.route('/equipment/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_equipment(item_id):
    item = EquipmentItem.query.get(item_id)
    if not item:
        flash('That equipment item no longer exists. Choose an item from the list below.', 'warning')
        return redirect(url_for('equipment'))
    accounts = Account.query.order_by(Account.name).all()
    equip_names = get_equip_names()
    equip_types = get_equip_types()
    service_types = get_service_types()
    if request.method == 'POST':
        name = (request.form.get('custom_name') or request.form.get('name') or '').strip()
        equipment_type = (request.form.get('custom_equipment_type') or request.form.get('equipment_type') or '').strip()
        service_type = (request.form.get('custom_service_type') or request.form.get('service_type') or '').strip()
        account_id_raw = request.form.get('account_id', '').strip()
        quantity_raw = request.form.get('quantity', '1').strip()
        item_status = request.form.get('item_status', 'working')
        last_service_raw = request.form.get('last_service_date', '').strip()

        if not name or not equipment_type or not account_id_raw:
            flash('Equipment name, model, and account are required.', 'error')
            return render_template('equipment_form.html', action='Edit', item=item,
                                   accounts=accounts, equip_names=equip_names,
                                   equip_types=equip_types, service_types=service_types)

        try:
            account_id = int(account_id_raw)
            quantity = int(quantity_raw) if quantity_raw else 1
        except ValueError:
            flash('Invalid account or quantity value.', 'error')
            return render_template('equipment_form.html', action='Edit', item=item,
                                   accounts=accounts, equip_names=equip_names,
                                   equip_types=equip_types, service_types=service_types)

        if not Account.query.get(account_id):
            flash('Selected account no longer exists. Choose an account from the list.', 'error')
            accounts = Account.query.order_by(Account.name).all()
            return render_template('equipment_form.html', action='Edit', item=item,
                                   accounts=accounts, equip_names=equip_names,
                                   equip_types=equip_types, service_types=service_types)

        item.name = name
        item.equipment_type = equipment_type
        item.service_type = service_type
        item.account_id = account_id
        item.quantity = quantity
        item.item_status = item_status
        item.last_service_date = None
        if last_service_raw:
            try:
                item.last_service_date = datetime.strptime(last_service_raw, '%Y-%m-%d').date()
            except ValueError:
                pass
        remember_option(EquipmentName, name)
        remember_option(EquipmentType, equipment_type)
        remember_option(EquipmentServiceType, service_type)
        db.session.commit()
        flash(f'Equipment "{item.name}" updated.', 'success')
        return redirect(url_for('equipment'))

    return render_template('equipment_form.html', action='Edit', item=item,
                           accounts=accounts, equip_names=equip_names,
                           equip_types=equip_types, service_types=service_types)


@app.route('/equipment/delete/<int:item_id>', methods=['POST'])
def delete_equipment(item_id):
    item = EquipmentItem.query.get(item_id)
    if not item:
        flash('That equipment item was not found. It may have already been deleted.', 'warning')
        return redirect(url_for('equipment'))
    db.session.delete(item)
    db.session.commit()
    flash('Equipment deleted.', 'success')
    return redirect(url_for('equipment'))


@app.route('/equipment/transfer/<int:item_id>', methods=['GET', 'POST'])
def transfer_equipment(item_id):
    item = EquipmentItem.query.get(item_id)
    if not item:
        flash('That equipment item no longer exists. Choose an item from the list below.', 'warning')
        return redirect(url_for('equipment'))
    accounts = Account.query.order_by(Account.name).all()
    if request.method == 'POST':
        try:
            new_account_id = int(request.form.get('account_id', ''))
        except ValueError:
            flash('Choose a destination account.', 'error')
            return render_template('transfer_form.html', item=item, accounts=accounts)
        destination = Account.query.get(new_account_id)
        if not destination:
            flash('Destination account no longer exists. Choose another account.', 'error')
            accounts = Account.query.order_by(Account.name).all()
            return render_template('transfer_form.html', item=item, accounts=accounts)
        old_account = item.account.name
        item.account_id = new_account_id
        db.session.commit()
        flash(f'"{item.name}" transferred from {old_account} to {item.account.name}.', 'success')
        return redirect(url_for('equipment'))
    return render_template('transfer_form.html', item=item, accounts=accounts)


# ─── Maintenance ─────────────────────────────────────────────────────────────

@app.route('/maintenance')
def maintenance():
    search = request.args.get('search', '').strip()
    query = (
        MaintenanceRecord.query
        .join(EquipmentItem)
    )
    if search:
        query = query.filter(
            db.or_(
                EquipmentItem.name.ilike(f'%{search}%'),
                EquipmentItem.equipment_type.ilike(f'%{search}%'),
                EquipmentItem.service_type.ilike(f'%{search}%'),
            )
        )
    records = query.order_by(MaintenanceRecord.service_date.desc()).all()
    return render_template('maintenance.html', records=records, search=search)


@app.route('/maintenance/add', methods=['GET', 'POST'])
def add_maintenance():
    equipment_list = EquipmentItem.query.order_by(EquipmentItem.name).all()
    if request.method == 'POST':
        try:
            equipment_id = int(request.form.get('equipment_id', ''))
        except ValueError:
            flash('Choose equipment before saving a maintenance record.', 'error')
            return render_template('maintenance_form.html', equipment_list=equipment_list,
                                   today=date.today().isoformat())

        equipment = EquipmentItem.query.get(equipment_id)
        if not equipment:
            flash('Selected equipment no longer exists. Choose an item from the list.', 'error')
            equipment_list = EquipmentItem.query.order_by(EquipmentItem.name).all()
            return render_template('maintenance_form.html', equipment_list=equipment_list,
                                   today=date.today().isoformat())

        maintenance_type = request.form.get('maintenance_type', '').strip()
        service_date_raw = request.form['service_date'].strip()
        notes = request.form.get('notes', '').strip()

        try:
            service_date = datetime.strptime(service_date_raw, '%Y-%m-%d').date()
        except ValueError:
            flash('Enter a valid service date.', 'error')
            return render_template('maintenance_form.html', equipment_list=equipment_list,
                                   today=date.today().isoformat())

        record = MaintenanceRecord(
            equipment_id=equipment_id,
            maintenance_type=maintenance_type,
            service_date=service_date,
            notes=notes
        )
        db.session.add(record)

        if equipment.last_service_date is None or service_date > equipment.last_service_date:
            equipment.last_service_date = service_date
            if request.form.get('mark_working') == 'yes':
                equipment.item_status = 'working'

        db.session.commit()
        flash('Maintenance record logged.', 'success')
        return redirect(url_for('maintenance'))
    return render_template('maintenance_form.html', equipment_list=equipment_list,
                           today=date.today().isoformat())


@app.route('/maintenance/delete/<int:record_id>', methods=['POST'])
def delete_maintenance(record_id):
    record = MaintenanceRecord.query.get(record_id)
    if not record:
        flash('That maintenance record was not found. It may have already been deleted.', 'warning')
        return redirect(url_for('maintenance'))
    db.session.delete(record)
    db.session.commit()
    flash('Maintenance record deleted.', 'success')
    return redirect(url_for('maintenance'))


# ─── Reports ─────────────────────────────────────────────────────────────────

@app.route('/reports')
def reports():
    from sqlalchemy import func, case
    report_view = request.args.get('view', 'equipment')
    selected_name = request.args.get('name', '')
    selected_account_id = request.args.get('account', '')

    # All distinct equipment names that exist in the DB (for the dropdown)
    available_names = [
        r[0] for r in db.session.query(EquipmentItem.name).distinct().order_by(EquipmentItem.name).all()
    ]
    available_accounts = Account.query.order_by(Account.name).all()

    # Full summary grouped by name (always shown)
    name_summary = (
        db.session.query(
            EquipmentItem.name,
            EquipmentItem.equipment_type,
            EquipmentItem.service_type,
            func.sum(EquipmentItem.quantity).label('total_qty'),
            func.sum(
                case((EquipmentItem.item_status == 'working', EquipmentItem.quantity), else_=0)
            ).label('working_qty'),
            func.sum(
                case((EquipmentItem.item_status == 'in_repair', EquipmentItem.quantity), else_=0)
            ).label('repair_qty'),
            func.sum(
                case((EquipmentItem.item_status == 'in_storage', EquipmentItem.quantity), else_=0)
            ).label('storage_qty'),
        )
        .group_by(EquipmentItem.name, EquipmentItem.equipment_type, EquipmentItem.service_type)
        .order_by(EquipmentItem.name, EquipmentItem.equipment_type, EquipmentItem.service_type)
        .all()
    )

    # Per-account breakdown for the selected equipment name
    detail_by_account = []
    detail_total = 0
    if selected_name:
        detail_by_account = (
            db.session.query(
                Account.name.label('account_name'),
                Account.location,
                Account.account_type,
                EquipmentItem.equipment_type,
                EquipmentItem.service_type,
                func.sum(EquipmentItem.quantity).label('qty'),
                func.sum(
                    case((EquipmentItem.item_status == 'working', EquipmentItem.quantity), else_=0)
                ).label('working_qty'),
                func.sum(
                    case((EquipmentItem.item_status == 'in_repair', EquipmentItem.quantity), else_=0)
                ).label('repair_qty'),
                func.sum(
                    case((EquipmentItem.item_status == 'in_storage', EquipmentItem.quantity), else_=0)
                ).label('storage_qty'),
            )
            .join(EquipmentItem, EquipmentItem.account_id == Account.id)
            .filter(EquipmentItem.name == selected_name)
            .group_by(Account.id, EquipmentItem.equipment_type, EquipmentItem.service_type)
            .order_by(Account.name, EquipmentItem.equipment_type, EquipmentItem.service_type)
            .all()
        )
        detail_total = sum(r.qty for r in detail_by_account)

    account_inventory_query = (
        db.session.query(
            Account.id.label('account_id'),
            Account.name.label('account_name'),
            Account.location,
            Account.account_type,
            EquipmentItem.name.label('equipment_name'),
            EquipmentItem.equipment_type,
            EquipmentItem.service_type,
            func.sum(EquipmentItem.quantity).label('qty'),
            func.sum(
                case((EquipmentItem.item_status == 'working', EquipmentItem.quantity), else_=0)
            ).label('working_qty'),
            func.sum(
                case((EquipmentItem.item_status == 'in_repair', EquipmentItem.quantity), else_=0)
            ).label('repair_qty'),
            func.sum(
                case((EquipmentItem.item_status == 'in_storage', EquipmentItem.quantity), else_=0)
            ).label('storage_qty'),
        )
        .join(EquipmentItem, EquipmentItem.account_id == Account.id)
    )
    selected_account = None
    if selected_account_id:
        try:
            selected_account_int = int(selected_account_id)
        except ValueError:
            selected_account_int = None
        if selected_account_int:
            selected_account = Account.query.get(selected_account_int)
            account_inventory_query = account_inventory_query.filter(Account.id == selected_account_int)

    account_inventory = (
        account_inventory_query
        .group_by(
            Account.id,
            EquipmentItem.name,
            EquipmentItem.equipment_type,
            EquipmentItem.service_type,
        )
        .order_by(
            Account.name,
            EquipmentItem.name,
            EquipmentItem.equipment_type,
            EquipmentItem.service_type,
        )
        .all()
    )
    account_totals = {
        'qty': sum(row.qty or 0 for row in account_inventory),
        'working': sum(row.working_qty or 0 for row in account_inventory),
        'repair': sum(row.repair_qty or 0 for row in account_inventory),
        'storage': sum(row.storage_qty or 0 for row in account_inventory),
    }

    return render_template('reports.html',
                           report_view=report_view,
                           available_names=available_names,
                           available_accounts=available_accounts,
                           selected_name=selected_name,
                           selected_account_id=selected_account_id,
                           selected_account=selected_account,
                           name_summary=name_summary,
                           detail_by_account=detail_by_account,
                           detail_total=detail_total,
                           account_inventory=account_inventory,
                           account_totals=account_totals)


# ─── Settings: Equipment Names & Types ───────────────────────────────────────

@app.route('/settings')
def settings():
    names = EquipmentName.query.order_by(EquipmentName.name).all()
    types = EquipmentType.query.order_by(EquipmentType.name).all()
    service_types = EquipmentServiceType.query.order_by(EquipmentServiceType.name).all()
    return render_template('settings.html', names=names, types=types, service_types=service_types)


@app.route('/settings/names/add', methods=['POST'])
def add_equip_name():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name cannot be empty.', 'error')
        return redirect(url_for('settings'))
    if EquipmentName.query.filter_by(name=name).first():
        flash(f'"{name}" already exists.', 'error')
        return redirect(url_for('settings'))
    db.session.add(EquipmentName(name=name))
    db.session.commit()
    flash(f'Equipment name "{name}" added.', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/names/edit/<int:name_id>', methods=['POST'])
def edit_equip_name(name_id):
    rec = EquipmentName.query.get(name_id)
    if not rec:
        flash('That equipment name was not found. It may have already been deleted.', 'warning')
        return redirect(url_for('settings'))
    new_name = request.form.get('name', '').strip()
    if not new_name:
        flash('Name cannot be empty.', 'error')
        return redirect(url_for('settings'))
    rec.name = new_name
    db.session.commit()
    flash(f'Updated to "{new_name}".', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/names/delete/<int:name_id>', methods=['POST'])
def delete_equip_name(name_id):
    rec = EquipmentName.query.get(name_id)
    if not rec:
        flash('That equipment name was not found. It may have already been deleted.', 'warning')
        return redirect(url_for('settings'))
    db.session.delete(rec)
    db.session.commit()
    flash(f'Equipment name "{rec.name}" deleted.', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/types/add', methods=['POST'])
def add_equip_type():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Model cannot be empty.', 'error')
        return redirect(url_for('settings'))
    if EquipmentType.query.filter_by(name=name).first():
        flash(f'"{name}" already exists.', 'error')
        return redirect(url_for('settings'))
    db.session.add(EquipmentType(name=name))
    db.session.commit()
    flash(f'Equipment model "{name}" added.', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/types/edit/<int:type_id>', methods=['POST'])
def edit_equip_type(type_id):
    rec = EquipmentType.query.get(type_id)
    if not rec:
        flash('That equipment model was not found. It may have already been deleted.', 'warning')
        return redirect(url_for('settings'))
    new_name = request.form.get('name', '').strip()
    if not new_name:
        flash('Model cannot be empty.', 'error')
        return redirect(url_for('settings'))
    rec.name = new_name
    db.session.commit()
    flash(f'Updated to "{new_name}".', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/types/delete/<int:type_id>', methods=['POST'])
def delete_equip_type(type_id):
    rec = EquipmentType.query.get(type_id)
    if not rec:
        flash('That equipment model was not found. It may have already been deleted.', 'warning')
        return redirect(url_for('settings'))
    db.session.delete(rec)
    db.session.commit()
    flash(f'Equipment model "{rec.name}" deleted.', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/service-types/add', methods=['POST'])
def add_service_type():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Service type cannot be empty.', 'error')
        return redirect(url_for('settings'))
    if EquipmentServiceType.query.filter_by(name=name).first():
        flash(f'"{name}" already exists.', 'error')
        return redirect(url_for('settings'))
    db.session.add(EquipmentServiceType(name=name))
    db.session.commit()
    flash(f'Service type "{name}" added.', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/service-types/edit/<int:service_type_id>', methods=['POST'])
def edit_service_type(service_type_id):
    rec = EquipmentServiceType.query.get(service_type_id)
    if not rec:
        flash('That service type was not found. It may have already been deleted.', 'warning')
        return redirect(url_for('settings'))
    new_name = request.form.get('name', '').strip()
    if not new_name:
        flash('Service type cannot be empty.', 'error')
        return redirect(url_for('settings'))
    rec.name = new_name
    db.session.commit()
    flash(f'Updated to "{new_name}".', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/service-types/delete/<int:service_type_id>', methods=['POST'])
def delete_service_type(service_type_id):
    rec = EquipmentServiceType.query.get(service_type_id)
    if not rec:
        flash('That service type was not found. It may have already been deleted.', 'warning')
        return redirect(url_for('settings'))
    db.session.delete(rec)
    db.session.commit()
    flash(f'Service type "{rec.name}" deleted.', 'success')
    return redirect(url_for('settings'))


if __name__ == '__main__':
    app.run(debug=True)

