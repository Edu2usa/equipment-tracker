"""Shared website sign-in, CSRF, and database-backed login lockout.

One username and one password, both from the environment (APP_LOGIN_USER and
APP_LOGIN_PASSWORD). Sessions are Flask's signed cookie, using SECRET_KEY, and
last 180 days so a phone stays signed in.

The shared password may be short, so guessing is limited here and the counters
live in login_lockouts (not process memory). That still works when Vercel runs
each request on a different instance:

- Same network: 8 wrong passwords in 15 minutes locks that network.
- Everybody: 40 wrong passwords in 15 minutes locks sign-in for every network.
- The first lock lasts 15 minutes. The next lock doubles (30, 60, ...) up to 24 hours.
- A successful sign-in clears the lock for that network only.
- After 24 hours with no wrong try, the doubling penalty resets.
- Wrong tries during a lock are ignored and do not extend it.

The password is slow-hashed (PBKDF2) and compared in constant time. The API
token is a long secret, so it is SHA-256 hashed and compared in constant time.
"""
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from models import LoginLockout, db

IP_FAILURE_LIMIT = 8
GLOBAL_FAILURE_LIMIT = 40
IP_WINDOW = timedelta(minutes=15)
GLOBAL_WINDOW = timedelta(minutes=15)
LOCK_BASE = timedelta(minutes=15)
LOCK_MAX = timedelta(hours=24)
LEVEL_DECAY = timedelta(hours=24)
SESSION_DAYS = 180
PBKDF2_ITERATIONS = 120_000
_LOGIN_SALT = b'preferred-maintenance-equipment-tracker-login-v1'
_SERVERLESS_KEYS = (
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
_UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
_app = None


def running_on_serverless():
    return any(os.environ.get(key) for key in _SERVERLESS_KEYS)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def login_is_configured():
    user = (os.environ.get('APP_LOGIN_USER') or '').strip()
    password = os.environ.get('APP_LOGIN_PASSWORD') or ''
    return bool(user) and password != ''


def production_misconfigured():
    if not running_on_serverless():
        return False
    if not (os.environ.get('SECRET_KEY') or '').strip():
        return True
    return not login_is_configured()


def _iterations():
    if _app is not None and _app.config.get('TESTING'):
        return 1
    return PBKDF2_ITERATIONS


def _password_digest(value):
    raw = '' if value is None else str(value)
    return hashlib.pbkdf2_hmac('sha256', raw.encode('utf-8'), _LOGIN_SALT, _iterations())


def _sha256(value):
    raw = '' if value is None else str(value)
    return hashlib.sha256(raw.encode('utf-8')).digest()


def passwords_match(submitted, expected):
    return hmac.compare_digest(_password_digest(submitted), _password_digest(expected))


def token_match(submitted, expected):
    # Always hash both sides so a missing header and a wrong token take the same path.
    supplied = submitted or ''
    wanted = expected or ''
    ok = hmac.compare_digest(_sha256(supplied), _sha256(wanted))
    return bool(supplied) and bool(wanted) and ok


def login_stamp():
    user = (os.environ.get('APP_LOGIN_USER') or '').strip()
    password = os.environ.get('APP_LOGIN_PASSWORD') or ''
    secret = (os.environ.get('SECRET_KEY') or '').encode('utf-8')
    if not secret and _app is not None:
        secret = str(_app.secret_key).encode('utf-8')
    return hmac.new(secret, f'{user}\n{password}'.encode('utf-8'), hashlib.sha256).hexdigest()


def session_is_valid():
    if not session.get('authenticated'):
        return False
    expected = login_stamp()
    supplied = session.get('login_stamp') or ''
    if not expected or not supplied or len(supplied) != len(expected):
        return False
    return hmac.compare_digest(supplied, expected)


def current_csrf_token():
    token = session.get('_csrf')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf'] = token
    return token


def csrf_ok():
    expected = session.get('_csrf') or ''
    supplied = request.form.get('csrf_token') or ''
    if not expected or not supplied:
        return False
    return hmac.compare_digest(_sha256(supplied), _sha256(expected))


def safe_next(value):
    if not value or not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate.startswith('/') or candidate.startswith('//') or '\\' in candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return None
    return candidate


def client_ip():
    raw = (request.headers.get('X-Real-IP') or '').strip()
    if not raw:
        forwarded = request.headers.get('X-Forwarded-For') or ''
        raw = forwarded.split(',')[0].strip()
    if not raw:
        raw = (request.remote_addr or '').strip()
    raw = raw[:64]
    if not re.fullmatch(r'[0-9A-Fa-f:.]+', raw or ''):
        return 'unknown'
    return raw


def bearer_token():
    header = request.headers.get('Authorization') or ''
    scheme, _, value = header.partition(' ')
    if scheme.lower() != 'bearer':
        return ''
    return value.strip()


def migration_needed(error):
    text = f'{type(error).__name__} {error}'.lower()
    markers = (
        'undefinedcolumn',
        'no such column',
        'login_lockouts',
        'service_interval_days',
        'serial_number',
        'invoice_ref',
        'undefinedtable',
    )
    return any(marker in text for marker in markers)


def _get_row(bucket, key, now):
    row = LoginLockout.query.filter_by(bucket=bucket, bucket_key=key).first()
    if row:
        return row
    row = LoginLockout(
        bucket=bucket,
        bucket_key=key,
        failures=0,
        window_started=now,
        lockout_level=0,
        updated_at=now,
    )
    db.session.add(row)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        row = LoginLockout.query.filter_by(bucket=bucket, bucket_key=key).one()
    return row


def _lock_delay(level):
    delay = LOCK_BASE * (2 ** max(level, 0))
    if delay > LOCK_MAX:
        return LOCK_MAX
    return delay


def _prepare_window(row, now, window):
    currently_locked = row.locked_until is not None and row.locked_until > now
    quiet = row.updated_at is not None and now - row.updated_at >= LEVEL_DECAY
    if quiet and not currently_locked:
        row.lockout_level = 0
    if row.locked_until is not None and row.locked_until <= now:
        row.locked_until = None
        row.failures = 0
        row.window_started = now
    if row.window_started is None or now - row.window_started >= window:
        row.failures = 0
        row.window_started = now


def _record_failure(row, now, limit, window):
    if row.locked_until is not None and row.locked_until > now:
        return row.locked_until
    _prepare_window(row, now, window)
    row.failures = (row.failures or 0) + 1
    row.updated_at = now
    if row.failures >= limit:
        delay = _lock_delay(row.lockout_level or 0)
        row.locked_until = now + delay
        row.lockout_level = (row.lockout_level or 0) + 1
        row.failures = 0
        row.window_started = now
        return row.locked_until
    return None


def _active_until(row, now):
    if row.locked_until is not None and row.locked_until > now:
        return row.locked_until
    return None


def _purge_old_ip_rows(now):
    cutoff = now - timedelta(days=7)
    LoginLockout.query.filter(
        LoginLockout.bucket == 'ip',
        LoginLockout.updated_at < cutoff,
        db.or_(LoginLockout.locked_until.is_(None), LoginLockout.locked_until < now),
    ).delete(synchronize_session=False)


def lock_status(ip):
    now = utcnow()
    ip_row = _get_row('ip', ip, now)
    global_row = _get_row('global', '*', now)
    deadlines = [item for item in (_active_until(ip_row, now), _active_until(global_row, now)) if item]
    if deadlines:
        db.session.commit()
        return max(deadlines)
    return None


def note_failure(ip):
    now = utcnow()
    ip_row = _get_row('ip', ip, now)
    global_row = _get_row('global', '*', now)
    until_ip = _record_failure(ip_row, now, IP_FAILURE_LIMIT, IP_WINDOW)
    until_global = _record_failure(global_row, now, GLOBAL_FAILURE_LIMIT, GLOBAL_WINDOW)
    _purge_old_ip_rows(now)
    db.session.commit()
    deadlines = [item for item in (until_ip, until_global) if item]
    return max(deadlines) if deadlines else None


def note_success(ip):
    now = utcnow()
    ip_row = _get_row('ip', ip, now)
    ip_row.failures = 0
    ip_row.locked_until = None
    ip_row.lockout_level = 0
    ip_row.window_started = now
    ip_row.updated_at = now
    _purge_old_ip_rows(now)
    db.session.commit()


def wait_phrase(until):
    seconds = int((until - utcnow()).total_seconds())
    minutes = max(1, (seconds + 59) // 60)
    unit = 'minute' if minutes == 1 else 'minutes'
    return f'{minutes} {unit}'


def _reject_login(message, status=401):
    flash(message, 'error')
    next_url = safe_next(request.form.get('next') or request.args.get('next'))
    body = render_template('login.html', next_url=next_url)
    response = _app.make_response(body)
    response.status_code = status
    return response


def login():
    if production_misconfigured() or not login_is_configured():
        return render_template('login_not_configured.html'), 503
    if session_is_valid():
        return redirect(safe_next(request.args.get('next')) or url_for('dashboard'))
    if request.method == 'GET':
        return render_template('login.html', next_url=safe_next(request.args.get('next')))

    ip = client_ip()
    try:
        blocked_until = lock_status(ip)
    except SQLAlchemyError as error:
        db.session.rollback()
        _app.logger.error('Login lockout check failed: %s', type(error).__name__)
        if migration_needed(error):
            return render_template('migration_required.html'), 503
        return render_template('database_unavailable.html'), 503
    if blocked_until:
        return _reject_login(
            f'Too many sign-in attempts. Try again in {wait_phrase(blocked_until)}.',
            status=429,
        )

    submitted_user = (request.form.get('username') or '').strip()
    submitted_password = request.form.get('password') or ''
    expected_user = (os.environ.get('APP_LOGIN_USER') or '').strip()
    expected_password = os.environ.get('APP_LOGIN_PASSWORD') or ''
    user_ok = passwords_match(submitted_user, expected_user)
    password_ok = passwords_match(submitted_password, expected_password)
    if not (user_ok and password_ok):
        try:
            locked_until = note_failure(ip)
        except SQLAlchemyError as error:
            db.session.rollback()
            _app.logger.error('Login lockout update failed: %s', type(error).__name__)
            if migration_needed(error):
                return render_template('migration_required.html'), 503
            return render_template('database_unavailable.html'), 503
        if locked_until:
            return _reject_login(
                f'Too many sign-in attempts. Try again in {wait_phrase(locked_until)}.',
                status=429,
            )
        return _reject_login('That username or password is not right.')

    try:
        note_success(ip)
    except SQLAlchemyError as error:
        db.session.rollback()
        _app.logger.error('Login lockout reset failed: %s', type(error).__name__)
        return render_template('database_unavailable.html'), 503

    next_url = safe_next(request.form.get('next') or request.args.get('next'))
    session.clear()
    session.permanent = True
    session['authenticated'] = True
    session['user'] = expected_user
    session['login_stamp'] = login_stamp()
    session['_csrf'] = secrets.token_urlsafe(32)
    return redirect(next_url or url_for('dashboard'))


def logout():
    session.clear()
    flash('You are signed out.', 'success')
    return redirect(url_for('login'))


def init_app(app):
    global _app
    _app = app
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=SESSION_DAYS)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = running_on_serverless()
    app.add_url_rule('/login', 'login', login, methods=['GET', 'POST'])
    app.add_url_rule('/logout', 'logout', logout, methods=['POST'])

    @app.before_request
    def protect_pages_and_forms():
        if request.endpoint == 'static' or request.path.startswith('/static/'):
            return None
        if request.path.startswith('/api/'):
            return None
        if production_misconfigured():
            return render_template('login_not_configured.html'), 503
        if request.method in _UNSAFE_METHODS and not csrf_ok():
            return render_template('csrf_error.html'), 400
        if request.endpoint in ('login', 'logout'):
            return None
        if not login_is_configured():
            return None
        if session_is_valid():
            return None
        target = request.full_path if request.method == 'GET' else request.path
        if target.endswith('?'):
            target = target[:-1]
        dest = safe_next(target)
        if dest:
            return redirect(url_for('login', next=dest))
        return redirect(url_for('login'))

    @app.context_processor
    def inject_security():
        return {
            'csrf_token': current_csrf_token,
            'signed_in': session_is_valid(),
            'login_required': login_is_configured(),
        }
