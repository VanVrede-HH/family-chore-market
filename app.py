from flask import Flask, render_template_string, request, redirect, url_for, flash, get_flashed_messages, session, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'family-chore-market-secure-key'

# Handle PostgreSQL connection string from Render environment variable
db_uri = os.environ.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///chore_market.db')
if db_uri.startswith("postgres://"):
    db_uri = db_uri.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_uri.startswith("postgresql://"):
    db_uri = db_uri.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELS ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'Parent', 'Adult', 'Kid'
    pin = db.Column(db.String(10), nullable=False)
    balance = db.Column(db.Float, default=0.0)

class Chore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    reward = db.Column(db.Float, nullable=False)
    funder_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(20), default='Open')  # Open, Claimed, Verification Requested, Completed, Penalty Applied
    due_date = db.Column(db.DateTime, nullable=True)
    grace_period_days = db.Column(db.Integer, default=1)
    penalty_rate = db.Column(db.Float, default=0.10)
    penalty_applied = db.Column(db.Boolean, default=False)
    
    funder = db.relationship('User', foreign_keys=[funder_id])
    worker = db.relationship('User', foreign_keys=[assigned_to])

class SystemConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    penalty_rate = db.Column(db.Float, default=0.10)
    grace_period_days = db.Column(db.Integer, default=1)
    leaderboard_duration_days = db.Column(db.Integer, default=30)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    action = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class Ledger(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    from_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    to_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), nullable=False)

# --- HTML TEMPLATE ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Family Chore Market</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen pb-12 font-sans">
    <nav class="bg-slate-800 border-b border-slate-700 p-4 mb-6 sticky top-0 z-50">
        <div class="max-w-4xl mx-auto flex justify-between items-center">
            <h1 class="text-xl font-bold text-amber-400 tracking-wide">🏆 Family Chore Market</h1>
            {% if session.get('user_id') %}
            <div class="flex items-center gap-4">
                <span class="text-sm bg-slate-700 px-3 py-1 rounded-full text-slate-300">
                    Logged in as <strong class="text-white">{{ current_user.name }}</strong> ({{ current_user.role }})
                </span>
                <a href="{{ url_for('logout') }}" class="text-xs bg-red-600 hover:bg-red-500 px-3 py-1.5 rounded font-semibold transition">Logout</a>
            </div>
            {% endif %}
        </div>
    </nav>

    <div class="max-w-4xl mx-auto px-4">
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="bg-amber-500/10 border border-amber-500 text-amber-300 px-4 py-3 rounded-lg mb-6 shadow-lg">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% if not session.get('user_id') %}
        <!-- LOGIN PORTAL -->
        <div class="max-w-md mx-auto bg-slate-800 p-8 rounded-xl border border-slate-700 shadow-2xl">
            <h2 class="text-2xl font-bold mb-6 text-center text-slate-100">Select Profile & Enter PIN</h2>
            <form action="{{ url_for('login') }}" method="POST" class="space-y-4">
                <div>
                    <label class="block text-sm font-medium mb-1 text-slate-300">User Profile</label>
                    <select name="user_id" class="w-full bg-slate-900 border border-slate-700 rounded p-2.5 text-white focus:ring-2 focus:ring-amber-400 outline-none">
                        {% for u in users %}
                            <option value="{{ u.id }}">{{ u.name }} ({{ u.role }})</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label class="block text-sm font-medium mb-1 text-slate-300">PIN Code</label>
                    <input type="password" name="pin" required placeholder="****" maxlength="10"
                           class="w-full bg-slate-900 border border-slate-700 rounded p-2.5 text-white text-center text-xl tracking-widest focus:ring-2 focus:ring-amber-400 outline-none">
                </div>
                <button type="submit" class="w-full bg-amber-500 hover:bg-amber-400 text-slate-900 font-bold py-3 rounded-lg transition shadow-md">
                    Access Market
                </button>
            </form>
        </div>
        {% else %}

        <!-- DASHBOARD -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <!-- LEADERBOARD -->
            <div class="bg-slate-800 p-5 rounded-xl border border-slate-700">
                <h3 class="font-bold text-lg mb-3 text-amber-400 flex items-center gap-2">🏅 Balance Leaderboard</h3>
                <div class="space-y-2">
                    {% for u in leaderboard %}
                    <div class="flex justify-between items-center bg-slate-900/60 px-3 py-2 rounded">
                        <span class="text-sm font-medium">{{ u.name }} <span class="text-xs text-slate-500">({{ u.role }})</span></span>
                        <span class="font-bold text-amber-400">R {{ "%.2f"|format(u.balance) }}</span>
                    </div>
                    {% endfor %}
                </div>
            </div>

            <!-- CHORE CREATION -->
            <div class="md:col-span-2 bg-slate-800 p-5 rounded-xl border border-slate-700">
                <h3 class="font-bold text-lg mb-3 text-amber-400">➕ Post a New Chore</h3>
                <form action="{{ url_for('create_chore') }}" method="POST" class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <input type="text" name="title" placeholder="Chore Description" required
                           class="bg-slate-900 border border-slate-700 rounded p-2 text-sm text-white focus:ring-1 focus:ring-amber-400 outline-none">
                    <input type="number" step="1" min="1" name="reward" placeholder="Reward Amount (R)" required
                           class="bg-slate-900 border border-slate-700 rounded p-2 text-sm text-white focus:ring-1 focus:ring-amber-400 outline-none">
                    <div>
                        <label class="block text-xs text-slate-400 mb-1">Due Date (Optional)</label>
                        <input type="date" name="due_date"
                               class="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-white focus:ring-1 focus:ring-amber-400 outline-none">
                    </div>
                    <div class="flex items-end">
                        <button type="submit" class="w-full bg-amber-500 hover:bg-amber-400 text-slate-900 font-bold py-2 rounded text-sm transition">
                            Post Chore
                        </button>
                    </div>
                </form>
            </div>
        </div>

        <!-- CHORE MARKET LIST -->
        <div class="bg-slate-800 p-6 rounded-xl border border-slate-700 mb-8">
            <h3 class="font-bold text-xl mb-4 text-slate-100">📋 Active Chores</h3>
            <div class="space-y-3">
                {% for c in chores %}
                <div class="bg-slate-900 p-4 rounded-lg border border-slate-700 flex flex-col md:flex-row justify-between md:items-center gap-3">
                    <div>
                        <div class="flex items-center gap-2">
                            <h4 class="font-bold text-lg text-white">{{ c.title }}</h4>
                            <span class="text-xs px-2 py-0.5 rounded font-semibold
                                {% if c.status == 'Open' %}bg-blue-500/20 text-blue-400 border border-blue-500/30
                                {% elif c.status == 'Claimed' %}bg-yellow-500/20 text-yellow-400 border border-yellow-500/30
                                {% elif c.status == 'Verification Requested' %}bg-purple-500/20 text-purple-400 border border-purple-500/30
                                {% else %}bg-green-500/20 text-green-400 border border-green-500/30{% endif %}">
                                {{ c.status }}
                            </span>
                        </div>
                        <p class="text-xs text-slate-400 mt-1">
                            Funder: <strong class="text-slate-200">{{ c.funder.name }}</strong> | 
                            Reward: <strong class="text-amber-400">R {{ "%.2f"|format(c.reward) }}</strong>
                            {% if c.due_date %} | Due: <span class="text-slate-300">{{ c.due_date.strftime('%Y-%m-%d') }}</span>{% endif %}
                            {% if c.worker %} | Worker: <strong class="text-slate-200">{{ c.worker.name }}</strong>{% endif %}
                        </p>
                    </div>

                    <div class="flex items-center gap-2">
                        {% if c.status == 'Open' %}
                            <form action="{{ url_for('claim_chore', chore_id=c.id) }}" method="POST">
                                <button type="submit" class="bg-blue-600 hover:bg-blue-500 text-white text-xs px-3 py-2 rounded font-semibold transition">
                                    Claim Chore
                                </button>
                            </form>
                        {% elif c.status == 'Claimed' and c.assigned_to == current_user.id %}
                            <form action="{{ url_for('request_verification', chore_id=c.id) }}" method="POST">
                                <button type="submit" class="bg-purple-600 hover:bg-purple-500 text-white text-xs px-3 py-2 rounded font-semibold transition">
                                    Mark Done
                                </button>
                            </form>
                        {% elif c.status == 'Verification Requested' and (c.funder_id == current_user.id or current_user.role == 'Parent') %}
                            <form action="{{ url_for('verify_chore', chore_id=c.id) }}" method="POST">
                                <button type="submit" class="bg-green-600 hover:bg-green-500 text-white text-xs px-3 py-2 rounded font-semibold transition">
                                    Approve & Pay
                                </button>
                            </form>
                        {% endif %}
                    </div>
                </div>
                {% else %}
                <p class="text-slate-400 text-sm italic">No active chores available at the moment.</p>
                {% endfor %}
            </div>
        </div>

        {% if current_user.role == 'Parent' %}
        <!-- PARENT ADMIN CONTROLS -->
        <div class="bg-slate-800 p-6 rounded-xl border border-slate-700 space-y-6">
            <h3 class="font-bold text-xl text-amber-400 border-b border-slate-700 pb-3">⚙️ Parent Administration</h3>
            
            <!-- CONFIG SETTINGS -->
            <form action="{{ url_for('update_config') }}" method="POST" class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                    <label class="block text-xs text-slate-300 mb-1">Late Penalty Rate (%)</label>
                    <input type="number" step="1" min="0" max="100" name="penalty_rate" value="{{ (config.penalty_rate * 100)|int }}"
                           class="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-white focus:ring-1 focus:ring-amber-400 outline-none">
                </div>
                <div>
                    <label class="block text-xs text-slate-300 mb-1">Grace Period (Days)</label>
                    <input type="number" min="0" name="grace_period_days" value="{{ config.grace_period_days }}"
                           class="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-white focus:ring-1 focus:ring-amber-400 outline-none">
                </div>
                <div class="flex items-end">
                    <button type="submit" class="w-full bg-slate-700 hover:bg-slate-600 text-white font-semibold py-2 rounded text-sm transition">
                        Save System Settings
                    </button>
                </div>
            </form>

            <!-- BACKUP & RESTORE -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-slate-700 pt-4">
                <div>
                    <h4 class="font-semibold text-sm mb-2 text-slate-200">Export Backup</h4>
                    <a href="{{ url_for('export_backup') }}" class="inline-block bg-slate-700 hover:bg-slate-600 text-white text-xs px-4 py-2 rounded font-semibold transition">
                        📥 Download JSON Backup
                    </a>
                </div>
                <div>
                    <h4 class="font-semibold text-sm mb-2 text-slate-200">Restore Backup</h4>
                    <form action="{{ url_for('import_backup') }}" method="POST" enctype="multipart/form-data" class="flex gap-2">
                        <input type="file" name="backup_file" accept=".json" required
                               class="bg-slate-900 border border-slate-700 rounded p-1 text-xs text-slate-300 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-slate-700 file:text-white">
                        <button type="submit" class="bg-amber-500 hover:bg-amber-400 text-slate-900 font-bold text-xs px-3 py-1.5 rounded transition">
                            Restore
                        </button>
                    </form>
                </div>
            </div>
        </div>
        {% endif %}

        {% endif %}
    </div>
</body>
</html>
"""

# --- INITIALIZATION ---

@app.before_request
def initialize_system():
    db.create_all()
    if not SystemConfig.query.first():
        db.session.add(SystemConfig(penalty_rate=0.10, grace_period_days=1))
    if not User.query.first():
        # Default profiles
        db.session.add(User(name="Mom", role="Parent", pin="1234", balance=0.0))
        db.session.add(User(name="Dad", role="Parent", pin="1234", balance=0.0))
        db.session.add(User(name="Kid 1", role="Kid", pin="0000", balance=0.0))
    db.session.commit()

# --- ROUTES ---

@app.route('/')
def index():
    users = User.query.all()
    current_user = User.query.get(session.get('user_id')) if session.get('user_id') else None
    leaderboard = User.query.order_by(User.balance.desc()).all()
    chores = Chore.query.all()
    config = SystemConfig.query.first()
    return render_template_string(HTML_TEMPLATE, users=users, current_user=current_user, leaderboard=leaderboard, chores=chores, config=config)

@app.route('/login', methods=['POST'])
def login():
    user_id = request.form.get('user_id')
    pin = request.form.get('pin')
    user = User.query.get(user_id)
    if user and user.pin == pin:
        session['user_id'] = user.id
        flash(f"Welcome back, {user.name}!")
    else:
        flash("Invalid PIN code. Please try again.")
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/create_chore', methods=['POST'])
def create_chore():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('index'))
    
    title = request.form.get('title')
    reward = float(request.form.get('reward', 0))
    due_date_str = request.form.get('due_date')
    due_date = datetime.strptime(due_date_str, '%Y-%m-%d') if due_date_str else None
    
    config = SystemConfig.query.first()
    chore = Chore(
        title=title,
        reward=reward,
        funder_id=user_id,
        due_date=due_date,
        grace_period_days=config.grace_period_days,
        penalty_rate=config.penalty_rate
    )
    db.session.add(chore)
    db.session.commit()
    flash("Chore posted successfully!")
    return redirect(url_for('index'))

@app.route('/claim_chore/<int:chore_id>', methods=['POST'])
def claim_chore(chore_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('index'))
    
    chore = Chore.query.get(chore_id)
    if chore and chore.status == 'Open':
        chore.status = 'Claimed'
        chore.assigned_to = user_id
        db.session.commit()
        flash("Chore claimed!")
    return redirect(url_for('index'))

@app.route('/request_verification/<int:chore_id>', methods=['POST'])
def request_verification(chore_id):
    chore = Chore.query.get(chore_id)
    if chore and chore.assigned_to == session.get('user_id'):
        chore.status = 'Verification Requested'
        db.session.commit()
        flash("Verification requested from funder.")
    return redirect(url_for('index'))

@app.route('/verify_chore/<int:chore_id>', methods=['POST'])
def verify_chore(chore_id):
    chore = Chore.query.get(chore_id)
    if chore and chore.status == 'Verification Requested':
        worker = User.query.get(chore.assigned_to)
        
        # Calculate late penalty rounded to nearest Rand
        final_reward = chore.reward
        if chore.due_date and datetime.now() > (chore.due_date + timedelta(days=chore.grace_period_days)):
            penalty = round(chore.reward * chore.penalty_rate)
            final_reward = max(0.0, chore.reward - penalty)
            chore.penalty_applied = True
            
        worker.balance += final_reward
        chore.status = 'Completed'
        
        # Log to ledger
        db.session.add(Ledger(
            from_user_id=chore.funder_id,
            to_user_id=worker.id,
            amount=final_reward,
            description=f"Completed chore: {chore.title}"
        ))
        db.session.commit()
        flash(f"Chore approved! R {final_reward:.2f} credited to {worker.name}.")
    return redirect(url_for('index'))

@app.route('/update_config', methods=['POST'])
def update_config():
    user = User.query.get(session.get('user_id'))
    if user and user.role == 'Parent':
        config = SystemConfig.query.first()
        config.penalty_rate = float(request.form.get('penalty_rate', 10)) / 100.0
        config.grace_period_days = int(request.form.get('grace_period_days', 1))
        db.session.commit()
        flash("System configuration updated.")
    return redirect(url_for('index'))

@app.route('/export_backup')
def export_backup():
    user = User.query.get(session.get('user_id'))
    if not user or user.role != 'Parent':
        return redirect(url_for('index'))
    
    data = {
        "users": [{"id": u.id, "name": u.name, "role": u.role, "pin": u.pin, "balance": u.balance} for u in User.query.all()],
        "chores": [{"id": c.id, "title": c.title, "reward": c.reward, "funder_id": c.funder_id, "assigned_to": c.assigned_to, "status": c.status} for c in Chore.query.all()]
    }
    return Response(json.dumps(data, indent=2), mimetype='application/json', headers={'Content-Disposition': 'attachment;filename=chore_backup.json'})

@app.route('/import_backup', methods=['POST'])
def import_backup():
    user = User.query.get(session.get('user_id'))
    if not user or user.role != 'Parent':
        return redirect(url_for('index'))
    
    file = request.files.get('backup_file')
    if file:
        data = json.load(file)
        db.drop_all()
        db.create_all()
        
        for u in data.get('users', []):
            db.session.add(User(id=u['id'], name=u['name'], role=u['role'], pin=u['pin'], balance=u['balance']))
        for c in data.get('chores', []):
            db.session.add(Chore(id=c['id'], title=c['title'], reward=c['reward'], funder_id=c['funder_id'], assigned_to=c.get('assigned_to'), status=c['status']))
            
        db.session.commit()
        flash("Backup restored successfully!")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
