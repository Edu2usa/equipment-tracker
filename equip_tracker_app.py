"""
Preferred Maintenance – Equipment Tracker
Single-file Flask app. Run with:  python equip_tracker_app.py
Requirements: pip install flask flask-sqlalchemy
"""

from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'preferred-maintenance-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///equip_tracker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ═══════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════

class Account(db.Model):
    __tablename__ = 'accounts'
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(120), nullable=False)
    account_type = db.Column(db.String(50),  nullable=False)
    location     = db.Column(db.String(120), nullable=False)
    equipment_items = db.relationship('EquipmentItem', backref='account', lazy=True)

    def equipment_count(self):
        return sum(e.quantity for e in self.equipment_items)


class EquipmentItem(db.Model):
    __tablename__ = 'equipment_items'
    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(120), nullable=False)
    equipment_type   = db.Column(db.String(80),  nullable=False)
    account_id       = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    quantity         = db.Column(db.Integer, default=1)
    item_status      = db.Column(db.String(50), default='working')
    last_service_date = db.Column(db.Date, nullable=True)
    maintenance_records = db.relationship('MaintenanceRecord', backref='equipment', lazy=True)


class MaintenanceRecord(db.Model):
    __tablename__ = 'maintenance_records'
    id               = db.Column(db.Integer, primary_key=True)
    equipment_id     = db.Column(db.Integer, db.ForeignKey('equipment_items.id'), nullable=False)
    maintenance_type = db.Column(db.String(80), nullable=False)
    service_date     = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    notes            = db.Column(db.Text, nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()


# ═══════════════════════════════════════════════════════════════
# SHARED CSS + BASE TEMPLATE
# ═══════════════════════════════════════════════════════════════

CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --navy:#1b3a5c;--navy-dark:#152e4a;--red:#c0392b;--red-dark:#922b21;
  --green:#1e7e34;--amber:#856404;
  --gray-50:#f4f6f8;--gray-100:#e9ecef;--gray-300:#ced4da;
  --gray-500:#6c757d;--gray-700:#495057;--gray-900:#212529;
  --white:#ffffff;
  --shadow:0 2px 8px rgba(0,0,0,.12);--radius:8px;--radius-sm:5px;--t:.18s ease;
}
html{font-size:15px}
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:var(--gray-50);
  color:var(--gray-900);line-height:1.55;min-height:100vh;display:flex;flex-direction:column}
a{color:inherit;text-decoration:none}

/* Header */
.site-header{background:var(--navy);box-shadow:0 2px 8px rgba(0,0,0,.25);position:sticky;top:0;z-index:100}
.header-inner{max-width:1200px;margin:0 auto;padding:0 24px;display:flex;align-items:center;
  justify-content:space-between;height:64px;gap:24px}
.logo-link{display:flex;align-items:center;gap:10px;text-decoration:none;flex-shrink:0}
.logo-icon{display:flex;align-items:center}
.logo-text{display:flex;flex-direction:column;line-height:1.1}
.logo-preferred{font-size:.75rem;font-weight:700;letter-spacing:.12em;color:#c8d6e5;text-transform:uppercase}
.logo-maintenance{font-size:1.05rem;font-weight:800;color:var(--white);letter-spacing:.02em}
.main-nav{display:flex;align-items:center;gap:4px}
.nav-link{color:rgba(255,255,255,.75);font-size:.875rem;font-weight:500;padding:8px 16px;
  border-radius:var(--radius-sm);border-bottom:2px solid transparent;
  transition:color var(--t),background var(--t),border-color var(--t)}
.nav-link:hover{color:var(--white);background:rgba(255,255,255,.08)}
.nav-link.active{color:var(--white);font-weight:700;border-bottom-color:var(--white);background:rgba(255,255,255,.10)}

/* Flash */
.flash-wrap{max-width:1200px;margin:16px auto 0;padding:0 24px}
.flash{padding:12px 18px;border-radius:var(--radius-sm);font-size:.875rem;font-weight:500;
  margin-bottom:8px;border-left:4px solid}
.flash-success{background:#d4edda;color:#155724;border-color:#28a745}
.flash-error{background:#f8d7da;color:#721c24;border-color:#dc3545}

/* Layout */
.page-content{max-width:1200px;margin:0 auto;padding:28px 24px 48px;flex:1;width:100%}
.page-header{display:flex;align-items:center;justify-content:space-between;
  margin-bottom:24px;flex-wrap:wrap;gap:12px}
.page-header h1{font-size:2rem;font-weight:800;color:var(--navy)}
.card{background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden}
.mt-4{margin-top:24px}

/* Stats */
.stats-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:4px}
.stat-card{background:var(--white);border-radius:var(--radius);padding:24px 20px;
  box-shadow:var(--shadow);border-left:4px solid var(--navy)}
.stat-card.working{border-left-color:#28a745}
.stat-card.in-repair{border-left-color:#ffc107}
.stat-card.in-storage{border-left-color:var(--gray-500)}
.stat-label{font-size:.7rem;font-weight:700;letter-spacing:.1em;color:var(--gray-500);
  text-transform:uppercase;margin-bottom:8px}
.stat-value{font-size:2.25rem;font-weight:800;color:var(--navy);line-height:1}
.stat-value.working-val{color:#155724}
.stat-value.repair-val{color:#856404}
.stat-value.storage-val{color:var(--gray-500)}
.section-title{font-size:1.05rem;font-weight:700;color:var(--navy);
  padding:18px 20px 12px;border-bottom:1px solid var(--gray-100)}
.quick-actions{display:flex;gap:12px;padding:16px 20px 20px;flex-wrap:wrap}

/* Buttons */
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 20px;border-radius:var(--radius-sm);
  font-size:.875rem;font-weight:600;cursor:pointer;border:2px solid transparent;
  transition:background var(--t),color var(--t),border-color var(--t);white-space:nowrap}
.btn-primary{background:var(--navy);color:var(--white);border-color:var(--navy)}
.btn-primary:hover{background:var(--navy-dark);border-color:var(--navy-dark)}
.btn-outline{background:var(--white);color:var(--navy);border-color:var(--gray-300)}
.btn-outline:hover{background:var(--gray-50);border-color:var(--navy)}
.btn-danger{background:var(--white);color:var(--red);border-color:#f5c6cb}
.btn-danger:hover{background:#f8d7da;border-color:var(--red)}
.btn-sm{padding:5px 12px;font-size:.8rem}

/* Table */
.data-table{width:100%;border-collapse:collapse}
.data-table thead tr{background:var(--navy);color:var(--white)}
.data-table thead th{padding:14px 16px;font-size:.7rem;font-weight:700;
  letter-spacing:.08em;text-align:left;white-space:nowrap}
.data-table tbody tr{border-bottom:1px solid var(--gray-100);transition:background var(--t)}
.data-table tbody tr:last-child{border-bottom:none}
.data-table tbody tr:hover{background:#f0f4f8}
.data-table tbody td{padding:13px 16px;font-size:.875rem;color:var(--gray-700);vertical-align:middle}
td.bold{font-weight:600;color:var(--gray-900)}
td.notes-cell{max-width:240px;color:var(--gray-500);font-size:.82rem}
td.actions-cell{white-space:nowrap}
td.actions-cell .btn+.btn{margin-left:4px}
.empty-row{text-align:center;color:var(--gray-500);padding:32px !important;font-style:italic}
.empty-row a{color:var(--navy);font-weight:600}

/* Badges */
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:.72rem;
  font-weight:700;letter-spacing:.04em;text-transform:capitalize}
.badge-working,.badge-client{background:#d4edda;color:#155724}
.badge-in_repair{background:#fff3cd;color:#856404}
.badge-in_storage{background:#e2e3e5;color:#383d41}
.badge-warehouse{background:#cce5ff;color:#004085}
.badge-spare_pool{background:#f8d7da;color:#721c24}

/* Filters & Forms */
.filter-card{padding:16px 20px;margin-bottom:16px}
.filter-form{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.filter-form .form-control{flex:1;min-width:160px}
.form-card{padding:28px 32px;max-width:760px}
.form-group{margin-bottom:20px;flex:1;min-width:220px}
.form-row{display:flex;gap:20px;flex-wrap:wrap}
label{display:block;font-size:.8rem;font-weight:700;color:var(--gray-700);
  text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}
.form-control{width:100%;padding:9px 12px;border:1.5px solid var(--gray-300);
  border-radius:var(--radius-sm);font-size:.875rem;color:var(--gray-900);background:var(--white);
  transition:border-color var(--t),box-shadow var(--t);appearance:none;-webkit-appearance:none}
.form-control:focus{outline:none;border-color:var(--navy);box-shadow:0 0 0 3px rgba(27,58,92,.12)}
select.form-control{background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23495057'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 12px center;padding-right:32px}
textarea.form-control{resize:vertical}
.form-group-checkbox{display:flex;align-items:center;padding-top:26px}
.checkbox-label{display:flex;align-items:center;gap:8px;font-size:.875rem;font-weight:400;
  color:var(--gray-700);text-transform:none;letter-spacing:0;cursor:pointer}
.checkbox-label input[type="checkbox"]{width:16px;height:16px;accent-color:var(--navy);
  cursor:pointer;flex-shrink:0}
.form-actions{display:flex;gap:12px;margin-top:8px;padding-top:20px;border-top:1px solid var(--gray-100)}
.transfer-info{background:var(--gray-50);border-radius:var(--radius-sm);padding:16px 20px;
  margin-bottom:24px;border-left:4px solid var(--navy)}
.transfer-info p{font-size:.875rem;color:var(--gray-700);margin-bottom:6px}
.transfer-info p:last-child{margin-bottom:0}

/* Footer */
.site-footer{background:var(--navy-dark);color:rgba(255,255,255,.5);text-align:center;
  padding:14px;font-size:.78rem}

/* Responsive */
@media(max-width:768px){.stats-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:640px){
  .header-inner{padding:0 14px}
  .nav-link{padding:8px 10px;font-size:.8rem}
  .logo-text{display:none}
  .page-content{padding:16px 14px 40px}
  .page-header h1{font-size:1.5rem}
  .form-card{padding:20px 16px}
  .data-table thead th,.data-table tbody td{padding:10px;font-size:.8rem}
}
"""

LOGO_SVG = """
<svg width="32" height="28" viewBox="0 0 32 28" fill="none" xmlns="http://www.w3.org/2000/svg">
  <polygon points="16,0 32,12 26,12 16,4 6,12 0,12" fill="#c0392b"/>
  <polygon points="16,8 32,20 26,20 16,12 6,20 0,20" fill="#c0392b"/>
  <polygon points="16,16 32,28 26,28 16,20 6,28 0,28" fill="#922b21"/>
</svg>"""

BASE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{% block title %}Preferred Maintenance{% endblock %}</title>
  <style>{{ css }}</style>
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <a href="{{ url_for('dashboard') }}" class="logo-link">
      <span class="logo-icon">{{ logo_svg|safe }}</span>
      <span class="logo-text">
        <span class="logo-preferred">Preferred</span>
        <span class="logo-maintenance">Maintenance</span>
      </span>
    </a>
    <nav class="main-nav">
      <a href="{{ url_for('dashboard') }}"  class="nav-link {% if ep=='dashboard' %}active{% endif %}">Dashboard</a>
      <a href="{{ url_for('accounts') }}"   class="nav-link {% if 'account' in ep %}active{% endif %}">Accounts</a>
      <a href="{{ url_for('equipment') }}"  class="nav-link {% if 'equipment' in ep %}active{% endif %}">Equipment</a>
      <a href="{{ url_for('maintenance') }}" class="nav-link {% if 'maintenance' in ep %}active{% endif %}">Maintenance</a>
    </nav>
  </div>
</header>
{% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    <div class="flash-wrap">
      {% for cat, msg in messages %}
        <div class="flash flash-{{ cat }}">{{ msg }}</div>
      {% endfor %}
    </div>
  {% endif %}
{% endwith %}
<main class="page-content">{% block content %}{% endblock %}</main>
<footer class="site-footer">&copy; 2026 Preferred Maintenance &mdash; Equipment Tracker</footer>
</body>
</html>"""


def render(template_body, **ctx):
    """Wrap a content block inside BASE and render with shared context."""
    full = BASE.replace("{% block content %}{% endblock %}", "{% block content %}" + template_body + "{% endblock %}")
    ctx.setdefault('css', CSS)
    ctx.setdefault('logo_svg', LOGO_SVG)
    ctx.setdefault('ep', request.endpoint or '')
    return render_template_string(full, **ctx)


# ═══════════════════════════════════════════════════════════════
# TEMPLATES (inline strings)
# ═══════════════════════════════════════════════════════════════

T_DASHBOARD = """
<div class="page-header"><h1>Dashboard</h1></div>
<div class="stats-grid">
  <div class="stat-card"><div class="stat-label">TOTAL EQUIPMENT</div><div class="stat-value">{{ total }}</div></div>
  <div class="stat-card working"><div class="stat-label">WORKING</div><div class="stat-value working-val">{{ working }}</div></div>
  <div class="stat-card in-repair"><div class="stat-label">IN REPAIR</div><div class="stat-value repair-val">{{ in_repair }}</div></div>
  <div class="stat-card in-storage"><div class="stat-label">IN STORAGE</div><div class="stat-value storage-val">{{ in_storage }}</div></div>
</div>
<div class="card mt-4">
  <h2 class="section-title">Quick Actions</h2>
  <div class="quick-actions">
    <a href="{{ url_for('add_equipment') }}" class="btn btn-primary">+ Add Equipment</a>
    <a href="{{ url_for('add_maintenance') }}" class="btn btn-outline">&#128295; Log Maintenance</a>
    <a href="{{ url_for('equipment') }}" class="btn btn-outline">&#8646; Transfer Equipment</a>
  </div>
</div>
<div class="card mt-4">
  <h2 class="section-title">Recently Repaired</h2>
  <table class="data-table"><thead><tr><th>EQUIPMENT</th><th>DATE</th><th>TYPE</th><th>ACCOUNT</th><th>NOTES</th></tr></thead>
  <tbody>
    {% for r in recently_repaired %}
    <tr>
      <td class="bold">{{ r.equipment.name }}</td>
      <td>{{ r.service_date.strftime('%b %d, %Y') }}</td>
      <td>{{ r.maintenance_type }}</td>
      <td>{{ r.equipment.account.name }}</td>
      <td class="notes-cell">{{ r.notes or '—' }}</td>
    </tr>
    {% else %}<tr><td colspan="5" class="empty-row">No maintenance records yet.</td></tr>{% endfor %}
  </tbody></table>
</div>
<div class="card mt-4">
  <h2 class="section-title">Account Summary</h2>
  <table class="data-table"><thead><tr><th>ACCOUNT</th><th>TYPE</th><th>LOCATION</th><th>EQUIPMENT</th></tr></thead>
  <tbody>
    {% for a in accounts %}
    <tr>
      <td class="bold">{{ a.name }}</td>
      <td><span class="badge badge-{{ a.account_type }}">{{ a.account_type }}</span></td>
      <td>{{ a.location }}</td>
      <td>{{ a.equipment_count() }}</td>
    </tr>
    {% else %}<tr><td colspan="4" class="empty-row">No accounts yet.</td></tr>{% endfor %}
  </tbody></table>
</div>"""

T_ACCOUNTS = """
<div class="page-header">
  <h1>Accounts</h1>
  <a href="{{ url_for('add_account') }}" class="btn btn-primary">+ Add Account</a>
</div>
<div class="card">
  <table class="data-table"><thead><tr><th>NAME</th><th>TYPE</th><th>LOCATION</th><th>EQUIPMENT</th><th>ACTIONS</th></tr></thead>
  <tbody>
    {% for a in accounts %}
    <tr>
      <td class="bold">{{ a.name }}</td>
      <td><span class="badge badge-{{ a.account_type }}">{{ a.account_type }}</span></td>
      <td>{{ a.location }}</td>
      <td>{{ a.equipment_count() }}</td>
      <td class="actions-cell">
        <a href="{{ url_for('edit_account', account_id=a.id) }}" class="btn btn-sm btn-outline">Edit</a>
        <form method="POST" action="{{ url_for('delete_account', account_id=a.id) }}"
              onsubmit="return confirm('Delete account?');" style="display:inline;">
          <button type="submit" class="btn btn-sm btn-danger">Delete</button>
        </form>
      </td>
    </tr>
    {% else %}<tr><td colspan="5" class="empty-row">No accounts yet. <a href="{{ url_for('add_account') }}">Add one.</a></td></tr>{% endfor %}
  </tbody></table>
</div>"""

T_ACCOUNT_FORM = """
<div class="page-header">
  <h1>{{ action }} Account</h1>
  <a href="{{ url_for('accounts') }}" class="btn btn-outline">&#8592; Back</a>
</div>
<div class="card form-card">
  <form method="POST">
    <div class="form-group">
      <label for="name">Account Name</label>
      <input type="text" id="name" name="name" class="form-control"
             value="{{ account.name if account else '' }}" placeholder="e.g. Downtown Office A" required/>
    </div>
    <div class="form-group">
      <label for="account_type">Type</label>
      <select id="account_type" name="account_type" class="form-control">
        {% for val,label in [('client','Client'),('warehouse','Warehouse'),('spare_pool','Spare Pool')] %}
        <option value="{{ val }}" {% if account and account.account_type==val %}selected{% endif %}>{{ label }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="form-group">
      <label for="location">Location</label>
      <input type="text" id="location" name="location" class="form-control"
             value="{{ account.location if account else '' }}" placeholder="e.g. New York" required/>
    </div>
    <div class="form-actions">
      <button type="submit" class="btn btn-primary">{{ action }} Account</button>
      <a href="{{ url_for('accounts') }}" class="btn btn-outline">Cancel</a>
    </div>
  </form>
</div>"""

T_EQUIPMENT = """
<div class="page-header">
  <h1>Equipment</h1>
  <a href="{{ url_for('add_equipment') }}" class="btn btn-primary">+ Add Equipment</a>
</div>
<div class="card filter-card">
  <form method="GET" class="filter-form">
    <input type="text" name="search" class="form-control" placeholder="Search equipment..." value="{{ search }}"/>
    <select name="status" class="form-control">
      <option value="">All Status</option>
      <option value="working"    {% if status_filter=='working'    %}selected{% endif %}>Working</option>
      <option value="in_repair"  {% if status_filter=='in_repair'  %}selected{% endif %}>In Repair</option>
      <option value="in_storage" {% if status_filter=='in_storage' %}selected{% endif %}>In Storage</option>
    </select>
    <select name="account" class="form-control">
      <option value="">All Accounts</option>
      {% for a in accounts %}
      <option value="{{ a.id }}" {% if account_filter==a.id|string %}selected{% endif %}>{{ a.name }}</option>
      {% endfor %}
    </select>
    <button type="submit" class="btn btn-primary">Filter</button>
    <a href="{{ url_for('equipment') }}" class="btn btn-outline">Clear</a>
  </form>
</div>
<div class="card">
  <table class="data-table">
    <thead><tr><th>EQUIPMENT</th><th>TYPE</th><th>ACCOUNT</th><th>QTY</th><th>STATUS</th><th>LAST SERVICE</th><th>ACTIONS</th></tr></thead>
    <tbody>
      {% for item in items %}
      <tr>
        <td class="bold">{{ item.name }}</td>
        <td>{{ item.equipment_type }}</td>
        <td>{{ item.account.name }}</td>
        <td>{{ item.quantity }}</td>
        <td><span class="badge badge-{{ item.item_status }}">{{ item.item_status.replace('_',' ').title() }}</span></td>
        <td>{{ item.last_service_date.strftime('%b %d, %Y') if item.last_service_date else '—' }}</td>
        <td class="actions-cell">
          <a href="{{ url_for('edit_equipment', item_id=item.id) }}" class="btn btn-sm btn-outline">Edit</a>
          <a href="{{ url_for('transfer_equipment', item_id=item.id) }}" class="btn btn-sm btn-outline">Transfer</a>
          <form method="POST" action="{{ url_for('delete_equipment', item_id=item.id) }}"
                onsubmit="return confirm('Delete?');" style="display:inline;">
            <button type="submit" class="btn btn-sm btn-danger">Delete</button>
          </form>
        </td>
      </tr>
      {% else %}<tr><td colspan="7" class="empty-row">No equipment found. <a href="{{ url_for('add_equipment') }}">Add some.</a></td></tr>{% endfor %}
    </tbody>
  </table>
</div>"""

T_EQUIPMENT_FORM = """
<div class="page-header">
  <h1>{{ action }} Equipment</h1>
  <a href="{{ url_for('equipment') }}" class="btn btn-outline">&#8592; Back</a>
</div>
<div class="card form-card">
  <form method="POST">
    <div class="form-row">
      <div class="form-group">
        <label>Equipment Name</label>
        <input type="text" name="name" class="form-control"
               value="{{ item.name if item else '' }}" placeholder="e.g. Laptop Dell XPS" required/>
      </div>
      <div class="form-group">
        <label>Equipment Type</label>
        <input type="text" name="equipment_type" class="form-control"
               value="{{ item.equipment_type if item else '' }}" placeholder="e.g. Laptop, Printer" required/>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Account</label>
        <select name="account_id" class="form-control" required>
          <option value="">— Select Account —</option>
          {% for a in accounts %}
          <option value="{{ a.id }}" {% if item and item.account_id==a.id %}selected{% endif %}>
            {{ a.name }} ({{ a.location }})
          </option>
          {% endfor %}
        </select>
      </div>
      <div class="form-group">
        <label>Quantity</label>
        <input type="number" name="quantity" class="form-control"
               value="{{ item.quantity if item else 1 }}" min="1" required/>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Status</label>
        <select name="item_status" class="form-control">
          {% for val,label in [('working','Working'),('in_repair','In Repair'),('in_storage','In Storage')] %}
          <option value="{{ val }}" {% if item and item.item_status==val %}selected
            {% elif not item and val=='working' %}selected{% endif %}>{{ label }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="form-group">
        <label>Last Service Date</label>
        <input type="date" name="last_service_date" class="form-control"
               value="{{ item.last_service_date.isoformat() if item and item.last_service_date else '' }}"/>
      </div>
    </div>
    <div class="form-actions">
      <button type="submit" class="btn btn-primary">{{ action }} Equipment</button>
      <a href="{{ url_for('equipment') }}" class="btn btn-outline">Cancel</a>
    </div>
  </form>
</div>"""

T_TRANSFER_FORM = """
<div class="page-header">
  <h1>Transfer Equipment</h1>
  <a href="{{ url_for('equipment') }}" class="btn btn-outline">&#8592; Back</a>
</div>
<div class="card form-card">
  <div class="transfer-info">
    <p><strong>Item:</strong> {{ item.name }}</p>
    <p><strong>Current Account:</strong> {{ item.account.name }} ({{ item.account.location }})</p>
    <p><strong>Quantity:</strong> {{ item.quantity }}</p>
  </div>
  <form method="POST">
    <div class="form-group">
      <label>Transfer To</label>
      <select name="account_id" class="form-control" required>
        <option value="">— Select Destination —</option>
        {% for a in accounts %}{% if a.id != item.account_id %}
        <option value="{{ a.id }}">{{ a.name }} – {{ a.location }} ({{ a.account_type }})</option>
        {% endif %}{% endfor %}
      </select>
    </div>
    <div class="form-actions">
      <button type="submit" class="btn btn-primary">&#8646; Confirm Transfer</button>
      <a href="{{ url_for('equipment') }}" class="btn btn-outline">Cancel</a>
    </div>
  </form>
</div>"""

T_MAINTENANCE = """
<div class="page-header">
  <h1>Maintenance History</h1>
  <a href="{{ url_for('add_maintenance') }}" class="btn btn-primary">+ Log Maintenance</a>
</div>
<div class="card filter-card">
  <form method="GET" class="filter-form">
    <input type="text" name="search" class="form-control" placeholder="Search by equipment name..." value="{{ search }}"/>
    <button type="submit" class="btn btn-primary">Search</button>
    <a href="{{ url_for('maintenance') }}" class="btn btn-outline">Clear</a>
  </form>
</div>
<div class="card">
  <table class="data-table">
    <thead><tr><th>EQUIPMENT</th><th>ACCOUNT</th><th>TYPE</th><th>DATE</th><th>NOTES</th><th>ACTIONS</th></tr></thead>
    <tbody>
      {% for r in records %}
      <tr>
        <td class="bold">{{ r.equipment.name }}</td>
        <td>{{ r.equipment.account.name }}</td>
        <td>{{ r.maintenance_type }}</td>
        <td>{{ r.service_date.strftime('%b %d, %Y') }}</td>
        <td class="notes-cell">{{ r.notes or '—' }}</td>
        <td class="actions-cell">
          <form method="POST" action="{{ url_for('delete_maintenance', record_id=r.id) }}"
                onsubmit="return confirm('Delete?');" style="display:inline;">
            <button type="submit" class="btn btn-sm btn-danger">Delete</button>
          </form>
        </td>
      </tr>
      {% else %}<tr><td colspan="6" class="empty-row">No records yet. <a href="{{ url_for('add_maintenance') }}">Log one.</a></td></tr>{% endfor %}
    </tbody>
  </table>
</div>"""

T_MAINTENANCE_FORM = """
<div class="page-header">
  <h1>Log Maintenance</h1>
  <a href="{{ url_for('maintenance') }}" class="btn btn-outline">&#8592; Back</a>
</div>
<div class="card form-card">
  <form method="POST">
    <div class="form-row">
      <div class="form-group">
        <label>Equipment</label>
        <select name="equipment_id" class="form-control" required>
          <option value="">— Select Equipment —</option>
          {% for eq in equipment_list %}
          <option value="{{ eq.id }}">{{ eq.name }} – {{ eq.account.name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="form-group">
        <label>Maintenance Type</label>
        <input type="text" name="maintenance_type" class="form-control"
               placeholder="e.g. Repair, Service, Inspection" required/>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Service Date</label>
        <input type="date" name="service_date" class="form-control" value="{{ today }}" required/>
      </div>
      <div class="form-group form-group-checkbox">
        <label class="checkbox-label">
          <input type="checkbox" name="mark_working" value="yes"/>
          Mark equipment as <strong>&nbsp;Working</strong> after this service
        </label>
      </div>
    </div>
    <div class="form-group">
      <label>Notes</label>
      <textarea name="notes" class="form-control" rows="4" placeholder="Optional details..."></textarea>
    </div>
    <div class="form-actions">
      <button type="submit" class="btn btn-primary">Save Record</button>
      <a href="{{ url_for('maintenance') }}" class="btn btn-outline">Cancel</a>
    </div>
  </form>
</div>"""


# ═══════════════════════════════════════════════════════════════
# ROUTES – Dashboard
# ═══════════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    total      = db.session.query(db.func.sum(EquipmentItem.quantity)).scalar() or 0
    working    = db.session.query(db.func.sum(EquipmentItem.quantity)).filter_by(item_status='working').scalar() or 0
    in_repair  = db.session.query(db.func.sum(EquipmentItem.quantity)).filter_by(item_status='in_repair').scalar() or 0
    in_storage = db.session.query(db.func.sum(EquipmentItem.quantity)).filter_by(item_status='in_storage').scalar() or 0
    recently_repaired = MaintenanceRecord.query.order_by(MaintenanceRecord.service_date.desc()).limit(10).all()
    accounts = Account.query.all()
    return render(T_DASHBOARD, total=total, working=working, in_repair=in_repair,
                  in_storage=in_storage, recently_repaired=recently_repaired, accounts=accounts)


# ─── Accounts ────────────────────────────────────────────────

@app.route('/accounts')
def accounts():
    return render(T_ACCOUNTS, accounts=Account.query.order_by(Account.name).all())

@app.route('/accounts/add', methods=['GET', 'POST'])
def add_account():
    if request.method == 'POST':
        name     = request.form['name'].strip()
        atype    = request.form['account_type']
        location = request.form['location'].strip()
        if not name or not location:
            flash('Name and location are required.', 'error')
        else:
            db.session.add(Account(name=name, account_type=atype, location=location))
            db.session.commit()
            flash(f'Account "{name}" added.', 'success')
            return redirect(url_for('accounts'))
    return render(T_ACCOUNT_FORM, action='Add', account=None)

@app.route('/accounts/edit/<int:account_id>', methods=['GET', 'POST'])
def edit_account(account_id):
    acct = Account.query.get_or_404(account_id)
    if request.method == 'POST':
        acct.name         = request.form['name'].strip()
        acct.account_type = request.form['account_type']
        acct.location     = request.form['location'].strip()
        db.session.commit()
        flash(f'Account "{acct.name}" updated.', 'success')
        return redirect(url_for('accounts'))
    return render(T_ACCOUNT_FORM, action='Edit', account=acct)

@app.route('/accounts/delete/<int:account_id>', methods=['POST'])
def delete_account(account_id):
    acct = Account.query.get_or_404(account_id)
    if acct.equipment_items:
        flash('Cannot delete account with equipment assigned.', 'error')
    else:
        db.session.delete(acct)
        db.session.commit()
        flash('Account deleted.', 'success')
    return redirect(url_for('accounts'))


# ─── Equipment ───────────────────────────────────────────────

@app.route('/equipment')
def equipment():
    search         = request.args.get('search', '').strip()
    status_filter  = request.args.get('status', '')
    account_filter = request.args.get('account', '')
    q = EquipmentItem.query
    if search:        q = q.filter(EquipmentItem.name.ilike(f'%{search}%'))
    if status_filter: q = q.filter_by(item_status=status_filter)
    if account_filter: q = q.filter_by(account_id=int(account_filter))
    items    = q.order_by(EquipmentItem.name).all()
    all_accts = Account.query.order_by(Account.name).all()
    return render(T_EQUIPMENT, items=items, accounts=all_accts,
                  search=search, status_filter=status_filter, account_filter=account_filter)

@app.route('/equipment/add', methods=['GET', 'POST'])
def add_equipment():
    all_accts = Account.query.order_by(Account.name).all()
    if request.method == 'POST':
        lsd_raw = request.form.get('last_service_date', '').strip()
        item = EquipmentItem(
            name           = request.form['name'].strip(),
            equipment_type = request.form['equipment_type'].strip(),
            account_id     = int(request.form['account_id']),
            quantity       = int(request.form.get('quantity', 1)),
            item_status    = request.form['item_status'],
            last_service_date = datetime.strptime(lsd_raw, '%Y-%m-%d').date() if lsd_raw else None
        )
        db.session.add(item)
        db.session.commit()
        flash(f'Equipment "{item.name}" added.', 'success')
        return redirect(url_for('equipment'))
    return render(T_EQUIPMENT_FORM, action='Add', item=None, accounts=all_accts)

@app.route('/equipment/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_equipment(item_id):
    item      = EquipmentItem.query.get_or_404(item_id)
    all_accts = Account.query.order_by(Account.name).all()
    if request.method == 'POST':
        lsd_raw = request.form.get('last_service_date', '').strip()
        item.name             = request.form['name'].strip()
        item.equipment_type   = request.form['equipment_type'].strip()
        item.account_id       = int(request.form['account_id'])
        item.quantity         = int(request.form.get('quantity', 1))
        item.item_status      = request.form['item_status']
        item.last_service_date = datetime.strptime(lsd_raw, '%Y-%m-%d').date() if lsd_raw else None
        db.session.commit()
        flash(f'Equipment "{item.name}" updated.', 'success')
        return redirect(url_for('equipment'))
    return render(T_EQUIPMENT_FORM, action='Edit', item=item, accounts=all_accts)

@app.route('/equipment/delete/<int:item_id>', methods=['POST'])
def delete_equipment(item_id):
    item = EquipmentItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('Equipment deleted.', 'success')
    return redirect(url_for('equipment'))

@app.route('/equipment/transfer/<int:item_id>', methods=['GET', 'POST'])
def transfer_equipment(item_id):
    item      = EquipmentItem.query.get_or_404(item_id)
    all_accts = Account.query.order_by(Account.name).all()
    if request.method == 'POST':
        old = item.account.name
        item.account_id = int(request.form['account_id'])
        db.session.commit()
        flash(f'"{item.name}" transferred from {old} to {item.account.name}.', 'success')
        return redirect(url_for('equipment'))
    return render(T_TRANSFER_FORM, item=item, accounts=all_accts)


# ─── Maintenance ─────────────────────────────────────────────

@app.route('/maintenance')
def maintenance():
    search = request.args.get('search', '').strip()
    q = MaintenanceRecord.query.join(EquipmentItem)
    if search: q = q.filter(EquipmentItem.name.ilike(f'%{search}%'))
    records = q.order_by(MaintenanceRecord.service_date.desc()).all()
    return render(T_MAINTENANCE, records=records, search=search)

@app.route('/maintenance/add', methods=['GET', 'POST'])
def add_maintenance():
    equipment_list = EquipmentItem.query.order_by(EquipmentItem.name).all()
    if request.method == 'POST':
        sd  = datetime.strptime(request.form['service_date'], '%Y-%m-%d').date()
        rec = MaintenanceRecord(
            equipment_id     = int(request.form['equipment_id']),
            maintenance_type = request.form['maintenance_type'].strip(),
            service_date     = sd,
            notes            = request.form.get('notes', '').strip()
        )
        db.session.add(rec)
        eq = EquipmentItem.query.get(rec.equipment_id)
        if eq and (eq.last_service_date is None or sd > eq.last_service_date):
            eq.last_service_date = sd
        if request.form.get('mark_working') == 'yes' and eq:
            eq.item_status = 'working'
        db.session.commit()
        flash('Maintenance record logged.', 'success')
        return redirect(url_for('maintenance'))
    return render(T_MAINTENANCE_FORM, equipment_list=equipment_list, today=date.today().isoformat())

@app.route('/maintenance/delete/<int:record_id>', methods=['POST'])
def delete_maintenance(record_id):
    rec = MaintenanceRecord.query.get_or_404(record_id)
    db.session.delete(rec)
    db.session.commit()
    flash('Maintenance record deleted.', 'success')
    return redirect(url_for('maintenance'))


# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("Starting Preferred Maintenance Equipment Tracker...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)
