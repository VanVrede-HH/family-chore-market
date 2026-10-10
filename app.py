from datetime import datetime
from flask import Flask, flash, redirect, render_template_string, request, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chores.db"
app.config["SECRET_KEY"] = "supersecretkey"
db = SQLAlchemy(app)


class User(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(50), nullable=False)
  role = db.Column(db.String(20), nullable=False)
  balance = db.Column(db.Float, default=0.0)


class Chore(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  title = db.Column(db.String(100), nullable=False)
  reward = db.Column(db.Float, nullable=False)
  penalty = db.Column(db.Float, nullable=False)
  status = db.Column(db.String(20), default="Open")
  assigned_kid_id = db.Column(
      db.Integer, db.ForeignKey("user.id"), nullable=True
  )
  deadline = db.Column(db.DateTime, nullable=True)


with app.app_context():
  db.create_all()
  if not User.query.first():
    db.session.add(User(name="Mom (Parent)", role="parent"))
    db.session.add(User(name="Alex (Kid)", role="kid", balance=0.0))
    db.session.add(User(name="Sam (Kid)", role="kid", balance=0.0))
    db.session.commit()

# --- HTML TEMPLATES ---

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Household Chore Board</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 font-sans pb-12">
    <nav class="bg-indigo-600 text-white p-4 shadow-md">
        <div class="container mx-auto flex justify-between items-center">
            <h1 class="text-xl font-bold">🏠 Family Chore Market</h1>
            <a href="/" class="bg-indigo-700 px-3 py-1 rounded text-sm font-medium">Home / Switch User</a>
        </div>
    </nav>
    <div class="container mx-auto p-4 max-w-2xl mt-4">
        {{ content | safe }}
    </div>
</body>
</html>
"""

INDEX_HTML = """
<div class="bg-white p-6 rounded-lg shadow-md">
    <h2 class="text-2xl font-bold mb-4 text-gray-800">Select Your Profile</h2>
    <div class="space-y-3">
        {% for user in users %}
            <div class="flex justify-between items-center p-3 bg-gray-50 border rounded-lg">
                <div>
                    <span class="font-semibold text-lg text-gray-800">{{ user.name }}</span>
                    <span class="text-xs uppercase px-2 py-0.5 rounded ml-2 {% if user.role == 'parent' %}bg-purple-100 text-purple-700{% else %}bg-green-100 text-green-700{% endif %}">{{ user.role }}</span>
                </div>
                <div>
                    {% if user.role == 'parent' %}
                        <a href="/parent" class="bg-indigo-600 text-white px-4 py-2 rounded text-sm font-medium">Open Dashboard</a>
                    {% else %}
                        <a href="/kid/{{ user.id }}" class="bg-green-600 text-white px-4 py-2 rounded text-sm font-medium">Open Portal (Bal: R{{ "%.2f"|format(user.balance) }})</a>
                    {% endif %}
                </div>
            </div>
        {% endfor %}
    </div>
</div>
"""

PARENT_HTML = """
<div class="bg-white p-6 rounded-lg shadow-md mb-6">
    <h2 class="text-2xl font-bold mb-4 text-gray-800">Parent Dashboard</h2>
    
    <form action="/parent/add" method="POST" class="space-y-4 mb-6 border-b pb-6">
        <h3 class="font-semibold text-lg text-indigo-600">Publish New Chore</h3>
        <div>
            <label class="block text-sm font-medium text-gray-700">Chore Title</label>
            <input type="text" name="title" required class="w-full mt-1 p-2 border rounded-md">
        </div>
        <div class="grid grid-cols-2 gap-4">
            <div>
                <label class="block text-sm font-medium text-gray-700">Reward (R)</label>
                <input type="number" step="0.01" name="reward" required class="w-full mt-1 p-2 border rounded-md">
            </div>
            <div>
                <label class="block text-sm font-medium text-gray-700">Penalty (R)</label>
                <input type="number" step="0.01" name="penalty" required class="w-full mt-1 p-2 border rounded-md">
            </div>
        </div>
        <button type="submit" class="w-full bg-indigo-600 text-white py-2 rounded-md font-semibold">Publish Chore</button>
    </form>

    <h3 class="font-semibold text-lg text-indigo-600 mb-3">Chores Awaiting Verification</h3>
    <div class="space-y-3">
        {% if not pending_chores %}
            <p class="text-gray-500 text-sm">No chores pending review.</p>
        {% endif %}
        {% for chore in pending_chores %}
            <div class="p-3 bg-yellow-50 border border-yellow-200 rounded-lg flex justify-between items-center">
                <div>
                    <p class="font-bold text-gray-800">{{ chore.title }}</p>
                    <p class="text-xs text-gray-600">Reward: R{{ chore.reward }} | Claimed by Kid ID: {{ chore.assigned_kid_id }}</p>
                </div>
                <a href="/parent/approve/{{ chore.id }}" class="bg-green-600 text-white px-3 py-1 rounded text-sm font-medium">Approve & Pay</a>
            </div>
        {% endfor %}
    </div>
</div>
"""

KID_HTML = """
<div class="bg-white p-6 rounded-lg shadow-md mb-6">
    <div class="flex justify-between items-center mb-4">
        <h2 class="text-2xl font-bold text-gray-800">{{ kid.name }}'s Portal</h2>
        <div class="bg-green-100 text-green-800 px-3 py-1 rounded-full font-bold text-sm">Wallet: R{{ "%.2f"|format(kid.balance) }}</div>
    </div>

    <h3 class="font-semibold text-lg text-indigo-600 mb-3">Available Chore Marketplace</h3>
    <div class="space-y-3 mb-6">
        {% if not open_chores %}
            <p class="text-gray-500 text-sm">No chores available right now.</p>
        {% endif %}
        {% for chore in open_chores %}
            <div class="p-4 bg-gray-50 border rounded-lg flex justify-between items-center">
                <div>
                    <h4 class="font-bold text-gray-800">{{ chore.title }}</h4>
                    <p class="text-xs text-green-600 font-semibold">Reward: R{{ chore.reward }} | Penalty Risk: R{{ chore.penalty }}</p>
                </div>
                <form action="/kid/claim/{{ kid.id }}/{{ chore.id }}" method="POST" class="flex items-center space-x-2">
                    <input type="datetime-local" name="deadline" required class="p-1 border rounded text-xs">
                    <button type="submit" class="bg-indigo-600 text-white px-3 py-1 rounded text-sm">Claim</button>
                </form>
            </div>
        {% endfor %}
    </div>

    <h3 class="font-semibold text-lg text-indigo-600 mb-3">My Claimed Chores</h3>
    <div class="space-y-3">
        {% if not my_chores %}
            <p class="text-gray-500 text-sm">You have no active claimed chores.</p>
        {% endif %}
        {% for chore in my_chores %}
            <div class="p-4 bg-blue-50 border border-blue-200 rounded-lg flex justify-between items-center">
                <div>
                    <h4 class="font-bold text-gray-800">{{ chore.title }}</h4>
                    <p class="text-xs text-gray-600">Due: {{ chore.deadline }}</p>
                </div>
                <a href="/kid/complete/{{ chore.id }}" class="bg-blue-600 text-white px-3 py-1 rounded text-sm font-medium">Mark Done</a>
            </div>
        {% endfor %}
    </div>
</div>
"""

# --- ROUTES ---


@app.route("/")
def index():
  users = User.query.all()
  content = render_template_string(INDEX_HTML, users=users)
  return render_template_string(BASE_TEMPLATE, content=content)


@app.route("/parent")
def parent_dashboard():
  pending_chores = Chore.query.filter_by(status="Completed").all()
  content = render_template_string(
      PARENT_HTML, pending_chores=pending_chores
  )
  return render_template_string(BASE_TEMPLATE, content=content)


@app.route("/parent/add", methods=["POST"])
def add_chore():
  title = request.form.get("title")
  reward = float(request.form.get("reward"))
  penalty = float(request.form.get("penalty"))

  new_chore = Chore(title=title, reward=reward, penalty=penalty, status="Open")
  db.session.add(new_chore)
  db.session.commit()
  return redirect(url_for("parent_dashboard"))


@app.route("/parent/approve/<int:chore_id>")
def approve_chore(chore_id):
  chore = Chore.query.get_or_404(chore_id)
  if chore.status == "Completed" and chore.assigned_kid_id:
    kid = User.query.get(chore.assigned_kid_id)
    if kid:
      kid.balance += chore.reward
      chore.status = "Approved"
      db.session.commit()
  return redirect(url_for("parent_dashboard"))


@app.route("/kid/<int:kid_id>")
def kid_portal(kid_id):
  kid = User.query.get_or_404(kid_id)
  open_chores = Chore.query.filter_by(status="Open").all()
  my_chores = Chore.query.filter_by(
      assigned_kid_id=kid.id, status="Claimed"
  ).all()
  content = render_template_string(
      KID_HTML, kid=kid, open_chores=open_chores, my_chores=my_chores
  )
  return render_template_string(BASE_TEMPLATE, content=content)


@app.route("/kid/claim/<int:kid_id>/<int:chore_id>", methods=["POST"])
def claim_chore(kid_id, chore_id):
  chore = Chore.query.get_or_404(chore_id)
  if chore.status == "Open":
    deadline_str = request.form.get("deadline")
    if deadline_str:
      chore.deadline = datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M")
    chore.assigned_kid_id = kid_id
    chore.status = "Claimed"
    db.session.commit()
  return redirect(url_for("kid_portal", kid_id=kid_id))


@app.route("/kid/complete/<int:chore_id>")
def complete_chore(chore_id):
  chore = Chore.query.get_or_404(chore_id)
  kid_id = chore.assigned_kid_id
  if chore.status == "Claimed":
    chore.status = "Completed"
    db.session.commit()
  return redirect(url_for("kid_portal", kid_id=kid_id))


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000, debug=True)
