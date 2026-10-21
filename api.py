"""Token-protected JSON API. No browser session and no CSRF.

Every request needs Authorization: Bearer <TRACKER_API_TOKEN>.
When that variable is missing, the API refuses all calls.
There are no delete routes.
"""
import os
from datetime import date

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from inventory import (
    VALID_STATUSES,
    FieldError,
    add_maintenance_record,
    create_equipment,
    due_reasons,
    equipment_json,
    equipment_search_filter,
    find_account_filter,
    maintenance_history,
    maintenance_json,
    parse_due_days,
    update_equipment,
)
from models import Account, EquipmentItem, db
from security import bearer_token, migration_needed, token_match

api_bp = Blueprint('api', __name__, url_prefix='/api')


def json_error(message, status):
    response = jsonify(error=message)
    response.status_code = status
    return response


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise FieldError('Send a JSON object.')
    return data


@api_bp.before_request
def require_token():
    expected = configured_token()
    if expected is None:
        return json_error('The API token is not configured.', 503)
    if not token_match(bearer_token(), expected):
        return json_error('Missing or invalid API token.', 401)
    return None


def configured_token():
    value = os.environ.get('TRACKER_API_TOKEN')
    if value is None or value.strip() == '':
        return None
    return value


@api_bp.errorhandler(SQLAlchemyError)
def api_database_error(error):
    db.session.rollback()
    if migration_needed(error):
        return json_error('The database is missing a required update. Run the SQL migration, then try again.', 503)
    return json_error('The database is unavailable.', 503)


@api_bp.errorhandler(404)
def api_not_found(_err):
    return json_error('Not found.', 404)


@api_bp.errorhandler(405)
def api_method_not_allowed(_err):
    return json_error('That action is not available.', 405)


def _equipment_or_404(item_id):
    item = EquipmentItem.query.get(item_id)
    if item is None:
        return None
    return item


def _filtered_equipment():
    search = (request.args.get('search') or '').strip()
    status = (request.args.get('status') or '').strip()
    account = request.args.get('account') or ''
    if status and status not in VALID_STATUSES:
        raise FieldError('Status must be working, in_repair, or in_storage.')
    query = EquipmentItem.query
    if search:
        query = query.filter(equipment_search_filter(search))
    if status:
        query = query.filter_by(item_status=status)
    account_id = find_account_filter(account, strict=True)
    if account_id is not None:
        query = query.filter_by(account_id=account_id)
    return query.order_by(EquipmentItem.name, EquipmentItem.id).all()


@api_bp.route('/equipment', methods=['GET'])
def list_equipment():
    try:
        items = _filtered_equipment()
    except FieldError as error:
        return json_error(error.message, 400)
    return jsonify(equipment=[equipment_json(item) for item in items])


@api_bp.route('/equipment', methods=['POST'])
def post_equipment():
    try:
        item = create_equipment(_json_body())
        db.session.commit()
    except FieldError as error:
        db.session.rollback()
        return json_error(error.message, 400)
    return jsonify(equipment=equipment_json(item)), 201


@api_bp.route('/equipment/<int:item_id>', methods=['GET'])
def get_equipment(item_id):
    item = _equipment_or_404(item_id)
    if item is None:
        return json_error('Equipment not found.', 404)
    history = [maintenance_json(record) for record in maintenance_history(item)]
    return jsonify(equipment=equipment_json(item), maintenance=history)


@api_bp.route('/equipment/<int:item_id>', methods=['PATCH'])
def patch_equipment(item_id):
    item = _equipment_or_404(item_id)
    if item is None:
        return json_error('Equipment not found.', 404)
    try:
        update_equipment(item, _json_body(), partial=True)
        db.session.commit()
    except FieldError as error:
        db.session.rollback()
        return json_error(error.message, 400)
    return jsonify(equipment=equipment_json(item))


@api_bp.route('/equipment/<int:item_id>/maintenance', methods=['POST'])
def post_maintenance(item_id):
    item = _equipment_or_404(item_id)
    if item is None:
        return json_error('Equipment not found.', 404)
    try:
        record = add_maintenance_record(item, _json_body())
        db.session.commit()
    except FieldError as error:
        db.session.rollback()
        return json_error(error.message, 400)
    return jsonify(maintenance=maintenance_json(record), equipment=equipment_json(item)), 201


@api_bp.route('/accounts', methods=['GET'])
def list_accounts():
    accounts = Account.query.order_by(Account.name).all()
    return jsonify(accounts=[
        {
            'id': account.id,
            'name': account.name,
            'account_type': account.account_type,
            'location': account.location,
            'equipment_count': account.equipment_count(),
        }
        for account in accounts
    ])


@api_bp.route('/due', methods=['GET'])
def due_equipment():
    try:
        days = parse_due_days(request.args.get('days'))
    except FieldError as error:
        return json_error(error.message, 400)
    today = date.today()
    rows = []
    items = EquipmentItem.query.order_by(EquipmentItem.name, EquipmentItem.id).all()
    for item in items:
        reasons = due_reasons(item, days, today=today)
        if not reasons:
            continue
        payload = equipment_json(item)
        payload['reasons'] = reasons
        rows.append(payload)
    rows.sort(key=lambda row: (row['next_due'] is None, row['next_due'] or '', row['name']))
    return jsonify(days=days, as_of=today.isoformat(), equipment=rows)
