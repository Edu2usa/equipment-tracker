from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, Account, EquipmentItem, MaintenanceRecord
from datetime import datetime, date
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'preferred-maintenance-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///equip_tracker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()


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
        if not name or not location:
            flash('Name and location are required.', 'error')
            return render_template('account_form.html', action='Add', account=None)
        acct = Account(name=name, account_type=account_type, location=location)
        db.session.add(acct)
        db.session.commit()
        flash(f'Account "{name}" added successfully.', 'success')
        return redirect(url_for('accounts'))
    return render_template('account_form.html', action='Add', account=None)


@app.route('/accounts/edit/<int:account_id>', methods=['GET', 'POST'])
def edit_account(account_id):
    acct = Account.query.get_or_404(account_id)
    if request.method == 'POST':
        acct.name = request.form['name'].strip()
        acct.account_type = request.form['account_type']
        acct.location = request.form['location'].strip()
        db.session.commit()
        flash(f'Account "{acct.name}" updated.', 'success')
        return redirect(url_for('accounts'))
    return render_template('account_form.html', action='Edit', account=acct)


@app.route('/accounts/delete/<int:account_id>', methods=['POST'])
def delete_account(account_id):
    acct = Account.query.get_or_404(account_id)
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
        query = query.filter(EquipmentItem.name.ilike(f'%{search}%'))
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
    if request.method == 'POST':
        name = request.form['name'].strip()
        equipment_type = request.form['equipment_type'].strip()
        account_id = int(request.form['account_id'])
        quantity = int(request.form.get('quantity', 1))
        item_status = request.form['item_status']
        last_service_raw = request.form.get('last_service_date', '').strip()
        last_service = datetime.strptime(last_service_raw, '%Y-%m-%d').date() if last_service_raw else None

        item = EquipmentItem(
            name=name, equipment_type=equipment_type,
            account_id=account_id, quantity=quantity,
            item_status=item_status, last_service_date=last_service
        )
        db.session.add(item)
        db.session.commit()
        flash(f'Equipment "{name}" added.', 'success')
        return redirect(url_for('equipment'))
    return render_template('equipment_form.html', action='Add', item=None, accounts=accounts)


@app.route('/equipment/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_equipment(item_id):
    item = EquipmentItem.query.get_or_404(item_id)
    accounts = Account.query.order_by(Account.name).all()
    if request.method == 'POST':
        item.name = request.form['name'].strip()
        item.equipment_type = request.form['equipment_type'].strip()
        item.account_id = int(request.form['account_id'])
        item.quantity = int(request.form.get('quantity', 1))
        item.item_status = request.form['item_status']
        last_service_raw = request.form.get('last_service_date', '').strip()
        item.last_service_date = datetime.strptime(last_service_raw, '%Y-%m-%d').date() if last_service_raw else None
        db.session.commit()
        flash(f'Equipment "{item.name}" updated.', 'success')
        return redirect(url_for('equipment'))
    return render_template('equipment_form.html', action='Edit', item=item, accounts=accounts)


@app.route('/equipment/delete/<int:item_id>', methods=['POST'])
def delete_equipment(item_id):
    item = EquipmentItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('Equipment deleted.', 'success')
    return redirect(url_for('equipment'))


@app.route('/equipment/transfer/<int:item_id>', methods=['GET', 'POST'])
def transfer_equipment(item_id):
    item = EquipmentItem.query.get_or_404(item_id)
    accounts = Account.query.order_by(Account.name).all()
    if request.method == 'POST':
        new_account_id = int(request.form['account_id'])
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
        query = query.filter(EquipmentItem.name.ilike(f'%{search}%'))
    records = query.order_by(MaintenanceRecord.service_date.desc()).all()
    return render_template('maintenance.html', records=records, search=search)


@app.route('/maintenance/add', methods=['GET', 'POST'])
def add_maintenance():
    equipment_list = EquipmentItem.query.order_by(EquipmentItem.name).all()
    if request.method == 'POST':
        equipment_id = int(request.form['equipment_id'])
        maintenance_type = request.form['maintenance_type'].strip()
        service_date_raw = request.form['service_date'].strip()
        notes = request.form.get('notes', '').strip()

        service_date = datetime.strptime(service_date_raw, '%Y-%m-%d').date()
        record = MaintenanceRecord(
            equipment_id=equipment_id,
            maintenance_type=maintenance_type,
            service_date=service_date,
            notes=notes
        )
        db.session.add(record)

        # Update last_service_date on the equipment
        equip = EquipmentItem.query.get(equipment_id)
        if equip and (equip.last_service_date is None or service_date > equip.last_service_date):
            equip.last_service_date = service_date
            # If it was in_repair and maintenance is logged, optionally set to working
            if request.form.get('mark_working') == 'yes':
                equip.item_status = 'working'

        db.session.commit()
        flash('Maintenance record logged.', 'success')
        return redirect(url_for('maintenance'))
    return render_template('maintenance_form.html', equipment_list=equipment_list,
                           today=date.today().isoformat())


@app.route('/maintenance/delete/<int:record_id>', methods=['POST'])
def delete_maintenance(record_id):
    record = MaintenanceRecord.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()
    flash('Maintenance record deleted.', 'success')
    return redirect(url_for('maintenance'))


if __name__ == '__main__':
    app.run(debug=True)
