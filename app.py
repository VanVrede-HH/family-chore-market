from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'family-chore-market-secret-key'
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

class Chore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    reward = db.Column(db.Float, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(30), default='Open')  # 'Open', 'Pending Verification', 'Completed'

    creator = db.relationship('User', foreign_keys=[created_by_id])
    assignee = db.relationship('User', foreign_keys=[assigned_to_id])

class Ledger(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    adult_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    kid_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount_due = db.Column(db.Float, default=0.0)
    pending_payout = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(30), default='Settled')  # 'Settled', 'Pending Confirmation'

    adult = db.relationship('User', foreign_keys=[adult_id])
    kid = db.relationship('User', foreign_keys=[kid_id])

# Helper function to get or create a ledger entry
def get_or_create_ledger(adult_id, kid_id):
    ledger = Ledger.query.filter_by(adult_id=adult_id, kid_id=kid_id).first()
    if not ledger:
        ledger = Ledger(adult_id=adult_id, kid_id=kid_id, amount_due=0.0, pending_payout=0.0, status='Settled')
        db.session.add(ledger)
        db.session.commit()
    return ledger

# ---------------------------------------------------------
# Single Page Template
# ---------------------------------------------------------
TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Family Chore Market</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 text-slate-800 font-sans min-h-screen">
    <!-- Navigation Bar -->
    <nav class="bg-indigo-600 text-white shadow-md p-4 mb-6 flex justify-between items-center">
        <h1 class="text-xl font-bold">🏡 Family Chore Market</h1>
        <a href="/" class="text-sm bg-indigo-800 hover:bg-indigo-900 px-3 py-1.5 rounded transition">Switch Profile / Home</a>
    </nav>

    <div class="max-w-4xl mx-auto px-4 pb-12">
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="p-4 mb-4 rounded-lg {% if category == 'error' %}bg-red-100 text-red-700{% else %}bg-green-100 text-green-700{% endif %} font-medium">
                {{ message }}
              </div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------

@app.route('/')
def home():
    users = User.query.all()
    template = TEMPLATE + """
    {% block content %}
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
                    {% if u.role in ['parent', 'adult'] %}
                        <a href="/adult/{{ u.id }}" class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded text-sm font-semibold">Portal</a>
                    {% else %}
                        <a href="/kid/{{ u.id }}" class="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-1.5 rounded text-sm font-semibold">Portal</a>
                    {% endif %}
                </div>
            {% endfor %}
        </div>
    </div>
    {% endblock %}
    """
    return render_template_string(template, users=users)


@app.route('/add_user', methods=['POST'])
def add_user():
    name = request.form.get('name', '').strip()
    role = request.form.get('role', 'kid')
    if name:
        if not User.query.filter_by(name=name).first():
            new_u = User(name=name, role=role)
            db.session.add(new_u)
            db.session.commit()
            flash(f"Added member: {name} ({role})", "success")
        else:
            flash("A family member with that name already exists.", "error")
    return redirect(request.referrer or url_for('home'))


@app.route('/adult/<int:user_id>')
def adult_dashboard(user_id):
    adult = User.query.get_or_404(user_id)
    if adult.role not in ['parent', 'adult']:
        return redirect(url_for('home'))

    all_users = User.query.all()
    kids = User.query.filter_by(role='kid').all()
    my_chores = Chore.query.filter_by(created_by_id=adult.id).all()
    ledgers = Ledger.query.filter_by(adult_id=adult.id).all()

    template = TEMPLATE + """
    {% block content %}
    <div class="space-y-6">
        <!-- Header -->
        <div class="bg-white p-6 rounded-xl shadow-md border-l-4 border-indigo-600 flex justify-between items-center">
            <div>
                <h2 class="text-2xl font-bold">{{ adult.name }}'s Portal</h2>
                <p class="text-slate-500 text-sm">Funder & Chore Administrator</p>
            </div>
            <span class="bg-indigo-100 text-indigo-700 font-bold px-3 py-1 rounded-full text-xs uppercase">{{ adult.role }}</span>
        </div>

        {% if adult.role == 'parent' %}
        <!-- Parent Super Admin: Add Household Members -->
        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">➕ Add Family Member</h3>
            <form action="/add_user" method="POST" class="flex flex-col sm:flex-row gap-3">
                <input type="text" name="name" placeholder="Member Name (e.g. Gabrielle, Granny)" required 
                       class="border border-slate-300 p-2 rounded-lg flex-grow focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <select name="role" class="border border-slate-300 p-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500">
                    <option value="kid">Kid</option>
                    <option value="adult">Adult / Funder</option>
                    <option value="parent">Parent (Admin)</option>
                </select>
                <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-2 rounded-lg transition">
                    Add Member
                </button>
            </form>
        </div>
        {% endif %}

        <!-- Post a New Chore -->
        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">📝 Post a New Chore</h3>
            <form action="/post_chore/{{ adult.id }}" method="POST" class="grid grid-cols-1 sm:grid-cols-3 gap-3">
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

        <!-- Managed Ledgers / Payouts -->
        <div class="bg-white p-6 rounded-xl shadow-md">
            <h3 class="font-bold text-slate-800 text-lg mb-3">💰 Your Kid Ledgers</h3>
            {% if ledgers %}
                <div class="divide-y">
                    {% for l in ledgers %}
                        <div class="py-3 flex flex-col sm:flex-row justify-between items-center gap-2">
                            <div>
                                <span class="font-semibold text-slate-800">{{ l.kid.name }}</span>
                                <div class="text-sm text-slate-500">
                                    Earned Unpaid: <span class="font-bold text-emerald-600">R{{ "%.2f"|format(l.amount_due) }}</span>
                                </div>
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
                <p class="text-slate-500 text-sm italic">No active ledgers yet. Assign and complete chores to generate balances.</p>
            {% endif %}
        </div>

        <!-- Posted Chores Status -->
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
                                    Assignee: {{ c.assignee.name if c.assignee else 'Unassigned' }}
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
                                    <span class="px-2.5 py-1 text-xs rounded-full font-bold
                                        {% if c.status == 'Open' %}bg-blue-100 text-blue-700
                                        {% else %}bg-slate-100 text-slate-600{% endif %}">
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
    </div>
    {% endblock %}
    """
    return render_template_string(template, adult=adult, kids=kids, my_chores=my_chores, ledgers=ledgers)


@app.route('/post_chore/<int:adult_id>', methods=['POST'])
def post_chore(adult_id):
    title = request.form.get('title', '').strip()
    try:
        reward = float(request.form.get('reward', 0))
    except ValueError:
        reward = 0

    if title and reward > 0:
        chore = Chore(title=title, reward=reward, created_by_id=adult_id, status='Open')
        db.session.add(chore)
        db.session.commit()
        flash("Chore posted successfully!", "success")
    return redirect(url_for('adult_dashboard', user_id=adult_id))


@app.route('/kid/<int:user_id>')
def kid_dashboard(user_id):
    kid = User.query.get_or_404(user_id)
    if kid.role != 'kid':
        return redirect(url_for('home'))

    open_chores = Chore.query.filter_by(status='Open').all()
    my_chores = Chore.query.filter_by(assigned_to_id=kid.id).all()
    ledgers = Ledger.query.filter_by(kid_id=kid.id).all()

    # Determine locked adults due to pending payments
    locked_adult_ids = [l.adult_id for l in ledgers if l.status == 'Pending Confirmation']

    template = TEMPLATE + """
    {% block content %}
    <div class="space-y-6">
        <!-- Header -->
        <div class="bg-white p-6 rounded-xl shadow-md border-l-4 border-emerald-500 flex justify-between items-center">
            <div>
                <h2 class="text-2xl font-bold">{{ kid.name }}'s Portal</h2>
                <p class="text-slate-500 text-sm">Kid Dashboard</p>
            </div>
            <span class="bg-emerald-100 text-emerald-700 font-bold px-3 py-1 rounded-full text-xs uppercase">KID</span>
        </div>

        <!-- Pending Confirmations -->
        {% for l in ledgers %}
            {% if l.status == 'Pending Confirmation' %}
                <div class="
