from flask import Flask, render_template_string, request, redirect, url_for, flash, get_flashed_messages, session, Response
from flask_sqlalchemy import SQLAlchemy
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
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(30), default='Open')

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
# Routes
# ---------------------------------------------------------

@app.route('/')
def home():
    users = User.query.all()
    html = """
    <div class="bg-white p-6 rounded-xl shadow-md max-w-lg mx-auto">
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
    """
    return render_page(html, users=users)


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
    return redirect(url_for('home'))


@app.route('/update_pin/<int:user_id>', methods=['POST'])
def update_pin(user_id):
    user = User.query.get_or_404(user_id)
    new_pin = request.form.get('new_pin', '').strip()
    user.pin = new_pin
    db.session.commit()
    flash("PIN updated successfully!", "success")
    return redirect(url_for('dashboard', user_id=user.id))


@app.route('/export_backup')
def export_backup():
    data = {
        "users": [{"id": u.id, "name": u.name, "role": u.role, "pin": u.pin} for u in User.query.all()],
        "chores": [{"id": c.id, "title": c.title, "reward": c.reward, "created_by": c.created_by_id, "assigned_to": c.assigned_to_id, "status": c.status} for c in Chore.query.all()],
        "ledgers": [{"id": l.id, "adult_id": l.adult_id, "kid_id": l.kid_id, "amount_due": l.amount_due, "status": l.status} for l in Ledger.query.all()]
    }
    return Response(
        json.dumps(data, indent=4),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=family_chore_market_backup.json"}
    )


def adult_portal(adult):
    kids = User.query.filter_by(role='kid').all()
    all_users = User.query.all()
    my_chores = Chore.query.filter_by(created_by_id=adult.id).all()
    ledgers = Ledger.query.filter_by(adult_id=adult.id).all()

    # Build mailto string for easy email backup sharing
    ledger_text = "Family Chore Market - Ledger Backup Summary%0A%0A"
    for l in ledgers:
        ledger_text += f"- {l.kid.name} earned R{l.amount_due:.2f} from {adult.name} (Status: {l.status})%0A"

    html = f"""
    <div class="space-y-6">
        <div class="bg-white p-6 rounded-xl shadow-md border-l-4 border-indigo-600 flex justify-between items-center">
            <div>
                <h2 class="text-2xl font-bold">{{{{ adult.name }}}}'s Portal</h2>
                <p class="text-slate-500 text-sm">Funder & Chore Administrator</p>
            </div>
            <span class="bg-indigo-100 text-indigo-700 font-bold px-3 py-1 rounded-full text-xs uppercase">{{{{ adult.role }}}}</span>
        </div>

        {% if adult.role == 'parent' %}
        <!-- Backup & Recovery Card -->
        <div class="bg-white p-6 rounded-xl shadow-md border border-indigo-100">
            <h3 class="font-bold text-slate-800 text-lg mb-2">💾 Data Backup & Recovery</h3>
            <p class="text-slate-500 text-sm mb-4">Download a local JSON backup of all users, chores, and ledgers, or email the daily ledger summary.</p>
            <div class="flex flex-wrap gap-3">
                <a href="/export_backup" class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-2 rounded-lg text-sm transition">
                    ⬇️ Download JSON Backup
                </a>
                <a href="mailto:?subject=Family%20Chore%20Market%20Daily%20Backup&body={ledger_text}" class="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-4 py-2 rounded-lg text-sm transition">
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
                        <span class="font-semibold text-slate-700">{{{{ u.name }}}} <span class="text-xs text-slate-400">({{{{ u.role }}}})</span></span>
                        <form action="/update_pin/{{{{ u.id }}}}" method="POST" class="flex gap-2">
                            <input type="text" name="new_pin" value="{{{{ u.pin }}}}" placeholder="New PIN" 
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
            <form action="/update_pin/{{{{ adult.id }}}}" method="POST" class="flex gap-3">
                <input type="text" name="new_pin" value="{{{{ adult.pin }}}}" placeholder="Enter new PIN" required
                       class="border border-slate-300 p-2 rounded-lg flex-grow focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-2 rounded-lg transition">
                    Save PIN
                </button>
            </form>
        </div>
        {% endif %}

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">📝 Post a New Chore</h3>
            <form action="/post_chore/{{{{ adult.id }}}}" method="POST" class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <input type="text" name="title" placeholder="Chore Description (e.g. Clean Bedroom)" required 
                       class="sm:col-span-2 border border-slate-300 p-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <div class="flex gap-2">
                    <span class="self-center font-bold text-slate-600">R</span>
                    <input type="number" step="0.50" min="1" name="reward" placeholder="Reward" required 
                           class="border border-slate-300 p-2 rounded-lg w-full focus:outline-none focus:ring-2 focus:ring-indigo-500">
                    <button type="submit" class="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-4 py-2 rounded-lg transition">
                        Post
                    </button>
                </div>
            </form>
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">💰 Your Kid Ledgers</h3>
            {% if ledgers %}
                <div class="divide-y">
                    {% for l in ledgers %}
                        <div class="py-3 flex flex-col sm:flex-row justify-between items-center gap-2">
                            <div>
                                <span class="font-semibold text-slate-800">{{{{ l.kid.name }}}}</span>
                                <div class="text-sm text-slate-500">
                                    Earned Unpaid: <span class="font-bold text-emerald-600">R{{{ "%.2f"|format(l.amount_due) }}}</span>
                                </div>
                            </div>
                            <div>
                                {% if l.status == 'Pending Confirmation' %}
                                    <span class="bg-amber-100 text-amber-700 px-3 py-1 rounded-lg text-xs font-bold">
                                        Pending Confirmation (R{{{ "%.2f"|format(l.pending_payout) }}})
                                    </span>
                                {% elif l.amount_due > 0 %}
                                    <form action="/pay_kid/{{{{ adult.id }}}}/{{{{ l.kid.id }}}}" method="POST" class="inline">
                                        <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-1.5 rounded-lg transition">
                                            Mark Paid (R{{{ "%.2f"|format(l.amount_due) }}})
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
                <p class="text-slate-500 text-sm italic">No active ledgers yet. Assign and complete chores to generate balances.</p>
            {% endif %}
        </div>

        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">📋 Chores Posted by You</h3>
            {% if my_chores %}
                <div class="space-y-3">
                    {% for c in my_chores %}
                        <div class="border p-3 rounded-lg flex justify-between items-center">
                            <div>
                                <h4 class="font-bold text-slate-800">{{{{ c.title }}}}</h4>
                                <p class="text-xs text-slate-500">
                                    Reward: R{{{ "%.2f"|format(c.reward) }}} | 
                                    Assignee: {{{{ c.assignee.name if c.assignee else 'Unassigned' }}}}
                                </p>
                            </div>
                            <div>
                                {% if c.status == 'Pending Verification' %}
                                    <form action="/verify_chore/{{{{ adult.id }}}}/{{{{ c.id }}}}" method="POST">
                                        <button type="submit" class="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-3 py-1.5 rounded transition">
                                            Verify & Approve
                                        </button>
                                    </form>
                                {% else %}
                                    <span class="px-2.5 py-1 text-xs rounded-full font-bold
                                        {% if c.status == 'Open' %}bg-blue-100 text-blue-700
                                        {% else %}bg-slate-100 text-slate-600{% endif %}">
                                        {{{{ c.status }}}}
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
    </div>
    """
    return render_page(html, adult=adult, kids=kids, all_users=all_users, my_chores=my_chores, ledgers=ledgers)


def kid_portal(kid):
    open_chores = Chore
