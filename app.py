from flask import Flask, render_template_string, request, redirect, url_for, flash, get_flashed_messages, session, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'family-chore-market-secure-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chore_market.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ---------------------------------------------------------
# Database Models
# ---------------------------------------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    role = db.Column(db.String(20), nullable=False)  # 'parent', 'adult', 'kid'
    pin = db.Column(db.String(20), default='')       # Optional access PIN

class Chore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    reward = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.DateTime, nullable=True)  # Funder specified completion time
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(30), default='Open')  # 'Open', 'Claimed', 'Pending Verification', 'Completed'
    claimed_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    creator = db.relationship('User', foreign_keys=[created_by_id])
    assignee = db.relationship('User', foreign_keys=[assigned_to_id])

class Ledger(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    adult_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    kid_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount_due = db.Column(db.Float, default=0.0)
    pending_payout = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(30), default='Settled')

    adult = db.relationship('User', foreign_keys=[adult_id])
    kid = db.relationship('User', foreign_keys=[kid_id])

class Setting(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(200), nullable=False)

def get_setting(key, default):
    s = Setting.query.get(key)
    return s.value if s else default

def set_setting(key, value):
    s = Setting.query.get(key)
    if not s:
        s = Setting(key=key, value=str(value))
        db.session.add(s)
    else:
        s.value = str(value)
    db.session.commit()

def get_or_create_ledger(adult_id, kid_id):
    ledger = Ledger.query.filter_by(adult_id=adult_id, kid_id=kid_id).first()
    if not ledger:
        ledger = Ledger(adult_id=adult_id, kid_id=kid_id, amount_due=0.0, pending_payout=0.0, status='Settled')
        db.session.add(ledger)
        db.session.commit()
    return ledger

# ---------------------------------------------------------
# Base HTML Layout
# ---------------------------------------------------------
BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Family Chore Market</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 text-slate-800 font-sans min-h-screen">
    <nav class="bg-indigo-600 text-white shadow-md p-4 mb-6 flex justify-between items-center">
        <h1 class="text-xl font-bold">🏡 Family Chore Market</h1>
        <a href="/" class="text-sm bg-indigo-800 hover:bg-indigo-900 px-3 py-1.5 rounded transition">Switch Profile / Home</a>
    </nav>

    <div class="max-w-4xl mx-auto px-4 pb-12">
        {% set messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          {% for category, message in messages %}
            <div class="p-4 mb-4 rounded-lg {% if category == 'error' %}bg-red-100 text-red-700{% else %}bg-green-100 text-green-700{% endif %} font-medium">
              {{ message }}
            </div>
          {% endfor %}
        {% endif %}

        {{ content|safe }}
    </div>
</body>
</html>
"""

def render_page(inner_html, **context):
    from jinja2 import Template
    context['get_flashed_messages'] = get_flashed_messages
    rendered_inner = Template(inner_html).render(**context)
    return Template(BASE_LAYOUT).render(content=rendered_inner, **context)

# ---------------------------------------------------------
# Routes & Views
# ---------------------------------------------------------

@app.route('/')
def home():
    users = User.query.all()
    
    lb_days = int(get_setting('leaderboard_days', '7'))
    cutoff = datetime.utcnow() - timedelta(days=lb_days)
    
    kids = User.query.filter_by(role='kid').all()
    leaderboard = []
    for k in kids:
        earned = db.session.query(db.func.sum(Chore.reward)).filter(
            Chore.assigned_to_id == k.id,
            Chore.status == 'Completed',
            Chore.completed_at >= cutoff
        ).scalar() or 0.0
        leaderboard.append({"name": k.name, "earned": earned})
    
    leaderboard = sorted(leaderboard, key=lambda x: x['earned'], reverse=True)

    html = """
    <div class="space-y-6 max-w-lg mx-auto">
        <div class="bg-white p-6 rounded-xl shadow-md border-l-4 border-amber-500">
            <h3 class="font-bold text-slate-800 text-lg mb-1">🏆 Top Earners (Past {{ lb_days }} Days)</h3>
            <p class="text-xs text-slate-500 mb-3">Keep up the great work! Refreshed automatically.</p>
            {% if leaderboard %}
                <div class="divide-y">
                    {% for entry in leaderboard %}
                        <div class="py-2 flex justify-between items-center text-sm">
                            <span class="font-semibold text-slate-700">{{ loop.index }}. {{ entry.name }}</span>
                            <span class="font-bold text-emerald-600">R{{ "%.2f"|format(entry.earned) }}</span>
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <p class="text-xs text-slate-400 italic">No earnings recorded for this period yet.</p>
            {% endif %}
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h2 class="text-2xl font-bold mb-4 text-center text-slate-800">Select Your Profile</h2>
            <div class="space-y-3">
                {% for u in users %}
                    <div class="flex items-center justify-between p-3 border rounded-lg hover:bg-slate-50 transition">
                        <div>
                            <span class="font-semibold text-lg text-slate-800">{{ u.name }}</span>
                            <span class="ml-2 px-2 py-0.5 text-xs rounded uppercase font-bold 
                                {% if u.role == 'parent' %}bg-purple-100 text-purple-700
                                {% elif u.role == 'adult' %}bg-blue-100 text-blue-700
                                {% else %}bg-green-100 text-green-700{% endif %}">
                                {{ u.role }}
                            </span>
                        </div>
                        <a href="/access/{{ u.id }}" class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded text-sm font-semibold">
                            {% if u.pin %}🔒 Enter Portal{% else %}Open Portal{% endif %}
                        </a>
                    </div>
                {% endfor %}
            </div>
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md border border-slate-200">
            <h3 class="font-bold text-slate-800 text-md mb-2">🔄 Restore Backup (JSON)</h3>
            <form action="/upload_backup" method="POST" enctype="multipart/form-data" class="flex flex-col sm:flex-row gap-2">
                <input type="file" name="backup_file" accept=".json" required class="text-xs text-slate-500 file:mr-2 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 flex-grow">
                <button type="submit" class="bg-slate-800 hover:bg-slate-900 text-white text-xs font-semibold px-4 py-2 rounded transition">
                    Restore
                </button>
            </form>
        </div>
    </div>
    """
    return render_page(html, users=users, leaderboard=leaderboard, lb_days=lb_days)


@app.route('/access/<int:user_id>')
def access_profile(user_id):
    user = User.query.get_or_404(user_id)
    if not user.pin:
        session['user_id'] = user.id
        session['user_role'] = user.role
        return redirect(url_for('dashboard', user_id=user.id))
    
    html = """
    <div class="bg-white p-6 rounded-xl shadow-md max-w-md mx-auto text-center">
        <h2 class="text-2xl font-bold mb-2 text-slate-800">🔒 Enter PIN for {{ user.name }}</h2>
        <p class="text-slate-500 text-sm mb-6">This profile is secured with a PIN.</p>
        <form action="/verify_pin/{{ user.id }}" method="POST" class="space-y-4">
            <input type="password" name="pin" placeholder="Enter PIN" required autofocus
                   class="border border-slate-300 p-3 rounded-lg w-full text-center text-xl tracking-widest focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold w-full py-3 rounded-lg transition">
                Unlock Portal
            </button>
        </form>
        <div class="mt-4">
            <a href="/" class="text-sm text-slate-500 hover:underline">← Back to Profile Selection</a>
        </div>
    </div>
    """
    return render_page(html, user=user)


@app.route('/verify_pin/<int:user_id>', methods=['POST'])
def verify_pin(user_id):
    user = User.query.get_or_404(user_id)
    entered_pin = request.form.get('pin', '')
    if user.pin == entered_pin:
        session['user_id'] = user.id
        session['user_role'] = user.role
        return redirect(url_for('dashboard', user_id=user.id))
    else:
        flash("Incorrect PIN. Please try again.", "error")
        return redirect(url_for('access_profile', user_id=user.id))


@app.route('/dashboard/<int:user_id>')
def dashboard(user_id):
    if session.get('user_id') != user_id:
        flash("Please log in with your profile PIN first.", "error")
        return redirect(url_for('access_profile', user_id=user_id))

    user = User.query.get_or_404(user_id)
    if user.role == 'kid':
        return kid_portal(user)
    else:
        return adult_portal(user)


@app.route('/add_user', methods=['POST'])
def add_user():
    name = request.form.get('name', '').strip()
    role = request.form.get('role', 'kid')
    pin = request.form.get('pin', '').strip()
    if name:
        if not User.query.filter_by(name=name).first():
            new_u = User(name=name, role=role, pin=pin)
            db.session.add(new_u)
            db.session.commit()
            flash(f"Added member: {name} ({role})", "success")
        else:
            flash("A family member with that name already exists.", "error")
    
    current_user_id = session.get('user_id')
    if current_user_id:
        return redirect(url_for('dashboard', user_id=current_user_id))
    return redirect(url_for('home'))


@app.route('/update_pin/<int:user_id>', methods=['POST'])
def update_pin(user_id):
    user = User.query.get_or_404(user_id)
    new_pin = request.form.get('new_pin', '').strip()
    user.pin = new_pin
    db.session.commit()
    flash("PIN updated successfully!", "success")
    
    current_user_id = session.get('user_id')
    if current_user_id:
        return redirect(url_for('dashboard', user_id=current_user_id))
    return redirect(url_for('dashboard', user_id=user.id))


@app.route('/update_settings', methods=['POST'])
def update_settings():
    release_hours = request.form.get('release_hours', '1')
    leaderboard_days = request.form.get('leaderboard_days', '7')
    penalty_grace_hours = request.form.get('penalty_grace_hours', '0')
    penalty_percent = request.form.get('penalty_percent', '10')

    set_setting('release_hours', release_hours)
    set_setting('leaderboard_days', leaderboard_days)
    set_setting('penalty_grace_hours', penalty_grace_hours)
    set_setting('penalty_percent', penalty_percent)

    flash("Platform settings and penalty rules updated successfully!", "success")
    return redirect(url_for('dashboard', user_id=session.get('user_id')))


@app.route('/export_backup')
def export_backup():
    data = {
        "users": [{"id": u.id, "name": u.name, "role": u.role, "pin": u.pin} for u in User.query.all()],
        "chores": [{"id": c.id, "title": c.title, "reward": c.reward, "created_by": c.created_by_id, "assigned_to": c.assigned_to_id, "status": c.status, "due_date": c.due_date.strftime('%Y-%m-%dT%H:%M') if c.due_date else None} for c in Chore.query.all()],
        "ledgers": [{"id": l.id, "adult_id": l.adult_id, "kid_id": l.kid_id, "amount_due": l.amount_due, "status": l.status} for l in Ledger.query.all()]
    }
    return Response(
        json.dumps(data, indent=4),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=family_chore_market_backup.json"}
    )


@app.route('/upload_backup', methods=['POST'])
def upload_backup():
    if 'backup_file' not in request.files:
        flash("No backup file selected.", "error")
        return redirect(url_for('home'))
    file = request.files['backup_file']
    if file.filename == '':
        flash("No backup file selected.", "error")
        return redirect(url_for('home'))
    try:
        data = json.load(file)
        db.drop_all()
        db.create_all()

        for u_data in data.get("users", []):
            u = User(id=u_data["id"], name=u_data["name"], role=u_data["role"], pin=u_data.get("pin", ""))
            db.session.add(u)
        db.session.commit()

        for c_data in data.get("chores", []):
            due = datetime.strptime(c_data["due_date"], '%Y-%m-%dT%H:%M') if c_data.get("due_date") else None
            c = Chore(
                id=c_data["id"], title=c_data["title"], reward=c_data["reward"],
                created_by_id=c_data["created_by"], assigned_to_id=c_data["assigned_to"], status=c_data["status"], due_date=due
            )
            db.session.add(c)
        db.session.commit()

        for l_data in data.get("ledgers", []):
            l = Ledger(
                id=l_data["id"], adult_id=l_data["adult_id"], kid_id=l_data["kid_id"],
                amount_due=l_data["amount_due"], status=l_data.get("status", "Settled")
            )
            db.session.add(l)
        db.session.commit()

        flash("Backup restored successfully!", "success")
    except Exception as e:
        flash(f"Error restoring backup: {str(e)}", "error")
    return redirect(url_for('home'))


@app.route('/adjust_ledger/<int:ledger_id>', methods=['POST'])
def adjust_ledger(ledger_id):
    ledger = Ledger.query.get_or_404(ledger_id)
    try:
        new_amount = float(request.form.get('amount_due', 0))
        ledger.amount_due = new_amount
        db.session.commit()
        flash(f"Manually updated ledger balance for {ledger.kid.name}.", "success")
    except ValueError:
        flash("Invalid amount entered.", "error")
    return redirect(url_for('dashboard', user_id=ledger.adult_id))


def adult_portal(adult):
    kids = User.query.filter_by(role='kid').all()
    all_users = User.query.all()
    my_chores = Chore.query.filter_by(created_by_id=adult.id).all()
    ledgers = Ledger.query.filter_by(adult_id=adult.id).all()

    release_hours = get_setting('release_hours', '1')
    leaderboard_days = get_setting('leaderboard_days', '7')
    penalty_grace_hours = get_setting('penalty_grace_hours', '0')
    penalty_percent = get_setting('penalty_percent', '10')

    ledger_text = f"Family Chore Market - Ledger Summary for {adult.name}%0A%0A"
    for l in ledgers:
        ledger_text += f"- {l.kid.name}: R{l.amount_due:.2f} unpaid (Status: {l.status})%0A"

    filter_period = request.args.get('filter_period', 'all')
    audit_query = Chore.query.filter(Chore.status == 'Completed')
    if filter_period == '7days':
        audit_query = audit_query.filter(Chore.completed_at >= datetime.utcnow() - timedelta(days=7))
    elif filter_period == '30days':
        audit_query = audit_query.filter(Chore.completed_at >= datetime.utcnow() - timedelta(days=30))
    audit_chores = audit_query.order_by(Chore.completed_at.desc()).all()

    html = """
    <div class="space-y-6">
        <div class="bg-white p-6 rounded-xl shadow-md border-l-4 border-indigo-600 flex justify-between items-center">
            <div>
                <h2 class="text-2xl font-bold">{{ adult.name }}'s Portal</h2>
                <p class="text-slate-500 text-sm">Funder & Chore Administrator</p>
            </div>
            <span class="bg-indigo-100 text-indigo-700 font-bold px-3 py-1 rounded-full text-xs uppercase">{{ adult.role }}</span>
        </div>

        {% if adult.role == 'parent' %}
        <div class="bg-white p-6 rounded-xl shadow-md border border-indigo-100">
            <h3 class="font-bold text-slate-800 text-lg mb-2">⚙️ Platform Variables & System-Wide Penalty Rules</h3>
            <form action="/update_settings" method="POST" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                    <label class="block text-xs font-semibold text-slate-600 mb-1">Kid Release Buffer (Hours)</label>
                    <input type="number" step="0.5" name="release_hours" value="{{ release_hours }}" required class="border border-slate-300 p-2 rounded-lg w-full text-sm">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-600 mb-1">Leaderboard Period (Days)</label>
                    <input type="number" name="leaderboard_days" value="{{ leaderboard_days }}" required class="border border-slate-300 p-2 rounded-lg w-full text-sm">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-600 mb-1">Late Penalty Grace Period (Hours)</label>
                    <input type="number" step="0.5" name="penalty_grace_hours" value="{{ penalty_grace_hours }}" required class="border border-slate-300 p-2 rounded-lg w-full text-sm">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-600 mb-1">Late Penalty Rate (%)</label>
                    <input type="number" step="1" name="penalty_percent" value="{{ penalty_percent }}" required class="border border-slate-300 p-2 rounded-lg w-full text-sm">
                </div>
                <div class="sm:col-span-2">
                    <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-2 rounded-lg text-sm transition w-full sm:w-auto">
                        Save Rules & Variables
                    </button>
                </div>
            </form>
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md border border-indigo-100">
            <h3 class="font-bold text-slate-800 text-lg mb-2">💾 Data Backup & Recovery</h3>
            <p class="text-slate-500 text-sm mb-4">Download a local JSON backup or share your active ledger summary via email.</p>
            <div class="flex flex-wrap gap-3">
                <a href="/export_backup" class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-2 rounded-lg text-sm transition">
                    ⬇️ Download JSON Backup
                </a>
                <a href="mailto:?subject=Family%20Chore%20Market%20Ledger%20Summary&body={{ ledger_text }}" class="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-4 py-2 rounded-lg text-sm transition">
                    📧 Email Ledger Summary
                </a>
            </div>
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">➕ Add Family Member</h3>
            <form action="/add_user" method="POST" class="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <input type="text" name="name" placeholder="Name (e.g. Granny)" required 
                       class="border border-slate-300 p-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <select name="role" class="border border-slate-300 p-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500">
                    <option value="kid">Kid</option>
                    <option value="adult">Adult / Funder</option>
                    <option value="parent">Parent (Admin)</option>
                </select>
                <input type="text" name="pin" placeholder="Optional PIN" 
                       class="border border-slate-300 p-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-2 rounded-lg transition">
                    Add Member
                </button>
            </form>
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">🔑 Manage Household PINs</h3>
            <div class="divide-y">
                {% for u in all_users %}
                    <div class="py-2 flex justify-between items-center">
                        <span class="font-semibold text-slate-700">{{ u.name }} <span class="text-xs text-slate-400">({{ u.role }})</span></span>
                        <form action="/update_pin/{{ u.id }}" method="POST" class="flex gap-2">
                            <input type="text" name="new_pin" value="{{ u.pin }}" placeholder="New PIN" 
                                   class="border border-slate-300 p-1 text-sm rounded w-24 focus:outline-none focus:ring-1 focus:ring-indigo-500">
                            <button type="submit" class="bg-slate-800 hover:bg-slate-900 text-white text-xs px-3 py-1 rounded transition">
                                Update PIN
                            </button>
                        </form>
                    </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}

        {% if adult.role != 'parent' %}
        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">🔒 Change Your PIN</h3>
            <form action="/update_pin/{{ adult.id }}" method="POST" class="flex gap-3">
                <input type="text" name="new_pin" value="{{ adult.pin }}" placeholder="Enter new PIN" required
                       class="border border-slate-300 p-2 rounded-lg flex-grow focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-2 rounded-lg transition">
                    Save PIN
                </button>
            </form>
        </div>
        {% endif %}

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">📝 Post a New Chore</h3>
            <form action="/post_chore/{{ adult.id }}" method="POST" class="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <input type="text" name="title" placeholder="Description (e.g. Dishes)" required 
                       class="sm:col-span-2 border border-slate-300 p-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm">
                <div class="flex gap-1 items-center">
                    <span class="font-bold text-slate-600 text-sm">R</span>
                    <input type="number" step="1" min="1" name="reward" placeholder="Reward" required 
                           class="border border-slate-300 p-2 rounded-lg w-full focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm">
                </div>
                <input type="datetime-local" name="due_date" required 
                       class="border border-slate-300 p-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm">
                <button type="submit" class="sm:col-span-4 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-2 rounded-lg transition text-sm">
                    Post Chore
                </button>
            </form>
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">💰 Your Kid Ledgers & Manual Adjustments</h3>
            {% if ledgers %}
                <div class="divide-y">
                    {% for l in ledgers %}
                        <div class="py-3 flex flex-col sm:flex-row justify-between items-center gap-3">
                            <div>
                                <span class="font-semibold text-slate-800">{{ l.kid.name }}</span>
                                <div class="text-sm text-slate-500">
                                    Earned Unpaid: <span class="font-bold text-emerald-600">R{{ "%.2f"|format(l.amount_due) }}</span>
                                </div>
                                <form action="/adjust_ledger/{{ l.id }}" method="POST" class="mt-1 flex items-center gap-2">
                                    <span class="text-xs text-slate-500">Manual Override R:</span>
                                    <input type="number" step="1" name="amount_due" value="{{ l.amount_due }}" 
                                           class="border border-slate-300 p-1 text-xs rounded w-24 focus:outline-none focus:ring-1 focus:ring-indigo-500">
                                    <button type="submit" class="bg-slate-700 hover:bg-slate-800 text-white text-xs px-2.5 py-1 rounded transition">
                                        Set Balance
                                    </button>
                                </form>
                            </div>
                            <div>
                                {% if l.status == 'Pending Confirmation' %}
                                    <span class="bg-amber-100 text-amber-700 px-3 py-1 rounded-lg text-xs font-bold">
                                        Pending Confirmation (R{{ "%.2f"|format(l.pending_payout) }})
                                    </span>
                                {% elif l.amount_due > 0 %}
                                    <form action="/pay_kid/{{ adult.id }}/{{ l.kid.id }}" method="POST" class="inline">
                                        <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-1.5 rounded-lg transition">
                                            Mark Paid (R{{ "%.2f"|format(l.amount_due) }})
                                        </button>
                                    </form>
                                {% else %}
                                    <span class="text-slate-400 text-xs font-semibold">Settled</span>
                                {% endif %}
                            </div>
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <p class="text-slate-500 text-sm italic">No active ledgers yet.</p>
            {% endif %}
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">📋 Chores Posted by You</h3>
            {% if my_chores %}
                <div class="space-y-3">
                    {% for c in my_chores %}
                        <div class="border p-3 rounded-lg flex justify-between items-center">
                            <div>
                                <h4 class="font-bold text-slate-800">{{ c.title }}</h4>
                                <p class="text-xs text-slate-500">
                                    Reward: R{{ "%.2f"|format(c.reward) }} | 
                                    Due: {{ c.due_date.strftime('%a %H:%M') if c.due_date else 'No deadline' }} | 
                                    Assignee: {{ c.assignee.name if c.assignee else 'Unassigned' }} | Status: {{ c.status }}
                                </p>
                            </div>
                            <div>
                                {% if c.status == 'Pending Verification' %}
                                    <form action="/verify_chore/{{ adult.id }}/{{ c.id }}" method="POST">
                                        <button type="submit" class="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-3 py-1.5 rounded transition">
                                            Verify & Approve
                                        </button>
                                    </form>
                                {% else %}
                                    <span class="px-2.5 py-1 text-xs rounded-full font-bold bg-slate-100 text-slate-600">
                                        {{ c.status }}
                                    </span>
                                {% endif %}
                            </div>
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <p class="text-slate-500 text-sm italic">You haven't posted any chores yet.</p>
            {% endif %}
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md">
            <div class="flex flex-col sm:flex-row justify-between items-center mb-4 gap-3">
                <h3 class="font-bold text-slate-800 text-lg">📜 Verified Chores Audit Log</h3>
                <form method="GET" class="flex gap-2">
                    <select name="filter_period" onchange="this.form.submit()" class="border border-slate-300 p-1.5 rounded text-xs">
                        <option value="all" {% if filter_period == 'all' %}selected{% endif %}>All Time</option>
                        <option value="7days" {% if filter_period == '7days' %}selected{% endif %}>Past 7 Days</option>
                        <option value="30days" {% if filter_period == '30days' %}selected{% endif %}>Past 30 Days</option>
                    </select>
                </form>
            </div>
            {% if audit_chores %}
                <div class="divide-y text-xs">
                    {% for ac in audit_chores %}
                        <div class="py-2 flex justify-between items-center">
                            <div>
                                <span class="font-semibold text-slate-800">{{ ac.title }}</span>
                                <span class="text-slate-500">(Done by <strong>{{ ac.assignee.name if ac.assignee else 'Unknown' }}</strong> for <strong>{{ ac.creator.name }}</strong>)</span>
                            </div>
                            <div class="text-right">
                                <span class="font-bold text-emerald-600">R{{ "%.2f"|format(ac.reward) }}</span>
                                <div class="text-slate-400">{{ ac.completed_at.strftime('%Y-%m-%d %H:%M') if ac.completed_at else '' }}</div>
                            </div>
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <p class="text-slate-500 text-sm italic">No completed chores recorded for this period.</p>
            {% endif %}
        </div>
    </div>
    """
    return render_page(html, adult=adult, kids=kids, all_users=all_users, my_chores=my_chores, ledgers=ledgers, release_hours=release_hours, leaderboard_days=leaderboard_days, penalty_grace_hours=penalty_grace_hours, penalty_percent=penalty_percent, audit_chores=audit_chores, filter_period=filter_period, ledger_text=ledger_text)


def kid_portal(kid):
    all_chores = Chore.query.filter(Chore.status.in_(['Open', 'Claimed'])).all()
    my_chores = Chore.query.filter_by(assigned_to_id=kid.id).all()
    ledgers = Ledger.query.filter_by(kid_id=kid.id).all()
    locked_adult_ids = [l.adult_id for l in ledgers if l.status == 'Pending Confirmation']

    release_hours = float(get_setting('release_hours', '1'))
    now = datetime.utcnow()

    html = """
    <div class="space-y-6">
        <div class="bg-white p-6 rounded-xl shadow-md border-l-4 border-emerald-500 flex justify-between items-center">
            <div>
                <h2 class="text-2xl font-bold">{{ kid.name }}'s Portal</h2>
                <p class="text-slate-500 text-sm">Kid Dashboard</p>
            </div>
            <span class="bg-emerald-100 text-emerald-700 font-bold px-3 py-1 rounded-full text-xs uppercase">KID</span>
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">🔒 Change Your PIN</h3>
            <form action="/update_pin/{{ kid.id }}" method="POST" class="flex gap-3">
                <input type="text" name="new_pin" value="{{ kid.pin }}" placeholder="Enter new PIN" required
                       class="border border-slate-300 p-2 rounded-lg flex-grow focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <button type="submit" class="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-4 py-2 rounded-lg transition">
                    Save PIN
                </button>
            </form>
        </div>

        {% for l in ledgers %}
            {% if l.status == 'Pending Confirmation' %}
                <div class="bg-amber-50 border-l-4 border-amber-500 p-4 rounded-r-xl shadow-sm flex flex-col sm:flex-row justify-between items-center gap-3">
                    <div>
                        <h4 class="font-bold text-amber-800">Payout Pending Confirmation</h4>
                        <p class="text-xs text-amber-700">
                            <strong>{{ l.adult.name }}</strong> marked <strong>R{{ "%.2f"|format(l.pending_payout) }}</strong> as paid. Please confirm receipt.
                        </p>
                    </div>
                    <form action="/confirm_payment/{{ kid.id }}/{{ l.id }}" method="POST">
                        <button type="submit" class="bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold px-4 py-2 rounded-lg transition">
                            Confirm Received
                        </button>
                    </form>
                </div>
            {% endif %}
        {% endfor %}

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">💵 Your Earnings by Funder</h3>
            {% if ledgers %}
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {% for l in ledgers %}
                        <div class="border p-3 rounded-lg flex justify-between items-center">
                            <span class="font-semibold text-slate-700">{{ l.adult.name }}</span>
                            <span class="font-bold text-emerald-600 text-lg">R{{ "%.2f"|format(l.amount_due) }}</span>
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <p class="text-slate-500 text-sm italic">No balances recorded yet.</p>
            {% endif %}
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">🛒 Chore Market</h3>
            {% if all_chores %}
                <div class="space-y-3">
                    {% for c in all_chores %}
                        <div class="border p-3 rounded-lg flex justify-between items-center">
                            <div>
                                <h4 class="font-bold text-slate-800">{{ c.title }}</h4>
                                <p class="text-xs text-slate-500">
                                    Posted by: <strong class="text-indigo-600">{{ c.creator.name }}</strong> | Reward: <strong class="text-emerald-600">R{{ "%.2f"|format(c.reward) }}</strong> | 
                                    Due: <strong class="text-slate-700">{{ c.due_date.strftime('%a %H:%M') if c.due_date else 'Flexible' }}</strong>
                                    {% if c.status == 'Claimed' %}
                                        <br><span class="text-amber-600 font-semibold">Claimed by {{ c.assignee.name }}</span>
                                    {% endif %}
                                </p>
                            </div>
                            <div>
                                {% if c.status == 'Open' %}
                                    {% if c.created_by_id in locked_adult_ids %}
                                        <span class="text-xs font-bold text-red-500 bg-red-50 px-2.5 py-1 rounded">
                                            Blocked (Confirm Payment)
                                        </span>
                                    {% else %}
                                        <form action="/claim_chore/{{ kid.id }}/{{ c.id }}" method="POST">
                                            <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold px-3 py-1.5 rounded transition">
                                                Claim
                                            </button>
                                        </form>
                                    {% endif %}
                                {% elif c.status == 'Claimed' and c.assigned_to_id == kid.id %}
                                    {% set can_release = c.claimed_at and (now - c.claimed_at).total_seconds() < (release_hours * 3600) %}
                                    {% if can_release %}
                                        <form action="/release_chore/{{ kid.id }}/{{ c.id }}" method="POST">
                                            <button type="submit" class="bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold px-3 py-1.5 rounded transition" title="Release back to pool without penalty">
                                                Release
                                            </button>
                                        </form>
                                    {% else %}
                                        <span class="text-xs text-slate-400">Claimed</span>
                                    {% endif %}
                                {% else %}
                                    <span class="text-xs text-slate-400">Claimed</span>
                                {% endif %}
                            </div>
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <p class="text-slate-500 text-sm italic">No chores available right now.</p>
            {% endif %}
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">📌 My Claimed Chores</h3>
            {% if my_chores %}
                <div class="space-y-3">
                    {% for c in my_chores %}
                        <div class="border p-3 rounded-lg flex justify-between items-center">
                            <div>
                                <h4 class="font-bold text-slate-800">{{ c.title }}</h4>
                                <p class="text-xs text-slate-500">
                                    Funder: {{ c.creator.name }} | R{{ "%.2f"|format(c.reward) }} | 
                                    Due: {{ c.due_date.strftime('%a %H:%M') if c.due_date else 'Flexible' }}
                                </p>
                            </div>
                            <div>
                                {% if c.status == 'Claimed' %}
                                    <form action="/complete_chore/{{ kid.id }}/{{ c.id }}" method="POST">
                                        <button type="submit" class="bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold px-3 py-1.5 rounded transition">
                                            Mark Done
                                        </button>
                                    </form>
                                {% else %}
                                    <span class="px-2.5 py-1 text-xs rounded-full font-bold
                                        {% if c.status == 'Pending Verification' %}bg-amber-100 text-amber-700
                                        {% else %}bg-green-100 text-green-700{% endif %}">
                                        {{ c.status }}
                                    </span>
                                {% endif %}
                            </div>
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <p class="text-slate-500 text-sm italic">You haven't claimed any chores yet.</p>
            {% endif %}
        </div>
    </div>
    """
    return render_page(html, kid=kid, all_chores=all_chores, my_chores=my_chores, ledgers=ledgers, locked_adult_ids=locked_adult_ids, release_hours=release_hours, now=now)


@app.route('/post_chore/<int:adult_id>', methods=['POST'])
def post_chore(adult_id):
    title = request.form.get('title', '').strip()
    due_date_raw = request.form.get('due_date', '').strip()
    try:
        reward = float(request.form.get('reward', 0))
    except ValueError:
        reward = 0

    due_date = None
    if due_date_raw:
        try:
            due_date = datetime.strptime(due_date_raw, '%Y-%m-%dT%H:%M')
        except ValueError:
            due_date = None

    if title and reward > 0:
        chore = Chore(title=title, reward=reward, due_date=due_date, created_by_id=adult_id, status='Open')
        db.session.add(chore)
        db.session.commit()
        flash("Chore posted successfully!", "success")
    return redirect(url_for('dashboard', user_id=adult_id))


@app.route('/claim_chore/<int:kid_id>/<int:chore_id>', methods=['POST'])
def claim_chore(kid_id, chore_id):
    chore = Chore.query.get_or_404(chore_id)
    ledger = Ledger.query.filter_by(adult_id=chore.created_by_id, kid_id=kid_id).first()
    
    if ledger and ledger.status == 'Pending Confirmation':
        flash("Confirm your pending payment from this adult first!", "error")
        return redirect(url_for('dashboard', user_id=kid_id))

    if chore.status == 'Open':
        chore.assigned_to_id = kid_id
        chore.status = 'Claimed'
        chore.claimed_at = datetime.utcnow()
        db.session.commit()
        flash("Chore claimed successfully!", "success")
    return redirect(url_for('dashboard', user_id=kid_id))


@app.route('/release_chore/<int:kid_id>/<int:chore_id>', methods=['POST'])
def release_chore(kid_id, chore_id):
    chore = Chore.query.get_or_404(chore_id)
    release_hours = float(get_setting('release_hours', '1'))
    
    if chore.assigned_to_id == kid_id and chore.status == 'Claimed':
        if chore.claimed_at and (datetime.utcnow() - chore.claimed_at).total_seconds() < (release_hours * 3600):
            chore.assigned_to_id = None
            chore.status = 'Open'
            chore.claimed_at = None
            db.session.commit()
            flash("Chore released back to the open market.", "success")
        else:
            flash("Release window has expired.", "error")
    return redirect(url_for('dashboard', user_id=kid_id))


@app.route('/complete_chore/<int:kid_id>/<int:chore_id>', methods=['POST'])
def complete_chore(kid_id, chore_id):
    chore = Chore.query.get_or_404(chore_id)
    if chore.assigned_to_id == kid_id and chore.status == 'Claimed':
        chore.status = 'Pending Verification'
        db.session.commit()
        flash("Chore submitted for verification!", "success")
    return redirect(url_for('dashboard', user_id=kid_id))


@app.route('/verify_chore/<int:adult_id>/<int:chore_id>', methods=['POST'])
def verify_chore(adult_id, chore_id):
    chore = Chore.query.get_or_404(chore_id)
    if chore.created_by_id == adult_id and chore.status == 'Pending Verification':
        now = datetime.utcnow()
        chore.status = 'Completed'
        chore.completed_at = now

        final_reward = chore.reward
        penalty_grace = float(get_setting('penalty_grace_hours', '0'))
        penalty_rate = float(get_setting('penalty_percent', '10'))

        if chore.due_date:
            deadline = chore.due_date + timedelta(hours=penalty_grace)
            if now > deadline:
                penalty_amount = round(chore.reward * (penalty_rate / 100.0))
                final_reward = max(0.0, chore.reward - penalty_amount)

        ledger = get_or_create_ledger(adult_id=adult_id, kid_id=chore.assigned_to_id)
        ledger.amount_due += final_reward
        db.session.commit()
        
        if final_reward < chore.reward:
            flash(f"Chore verified late! Penalty applied: Earned R{final_reward:.0f} (Original R{chore.reward:.0f}).", "success")
        else:
            flash("Chore verified on time! Full reward credited.", "success")

    return redirect(url_for('dashboard', user_id=adult_id))


@app.route('/pay_kid/<int:adult_id>/<int:kid_id>', methods=['POST'])
def pay_kid(adult_id, kid_id):
    ledger = Ledger.query.filter_by(adult_id=adult_id, kid_id=kid_id).first()
    if ledger and ledger.amount_due > 0:
        ledger.pending_payout = ledger.amount_due
        ledger.amount_due = 0.0
        ledger.status = 'Pending Confirmation'
        db.session.commit()
        flash("Payout initiated. Waiting for kid to confirm receipt.", "success")
    return redirect(url_for('dashboard', user_id=adult_id))


@app.route('/confirm_payment/<int:kid_id>/<int:ledger_id>', methods=['POST'])
def confirm_payment(kid_id, ledger_id):
    ledger = Ledger.query.get_or_404(ledger_id)
    if ledger.kid_id == kid_id and ledger.status == 'Pending Confirmation':
        ledger.pending_payout = 0.0
        ledger.status = 'Settled'
        db.session.commit()
        flash("Payment receipt confirmed! Ledger is settled.", "success")
    return redirect(url_for('dashboard', user_id=kid_id))


with app.app_context():
    db.create_all()
    if not User.query.first():
        mom = User(name="Mom", role="parent", pin="1234")
        db.session.add(mom)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
