from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, abort, flash
from datetime import date, datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
import db, io, csv, os

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "replace_this_with_a_real_secret"  # change for production

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

CATEGORIES = ["Food", "Transport", "Groceries", "Entertainment", "Bills", "Other"]

class User(UserMixin):
    def __init__(self, id_, username, password):
        self.id = id_
        self.username = username
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, password FROM users WHERE id=?", (int(user_id),))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    return User(r["id"], r["username"], r["password"])

def run_recurring_jobs_for_user(user_id):
    recs = db.get_recurring(user_id)
    today = date.today()
    for r in recs:
        if r.get("interval") != "monthly":
            continue
        last_run = r.get("last_run")
        # if never run or last_run before this month -> add
        add_flag = False
        if not last_run:
            add_flag = True
        else:
            try:
                lr = datetime.fromisoformat(last_run).date()
                if lr.year < today.year or (lr.year == today.year and lr.month < today.month):
                    add_flag = True
            except:
                add_flag = True
        if add_flag:
            db.add_expense(user_id, today.isoformat(), r.get("category"), float(r.get("amount")), r.get("note"))
            db.update_recurring_last_run(r.get("id"), today.isoformat())

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        if not username or not password:
            flash("Provide username and password")
            return redirect(url_for("register"))
        existing = db.find_user_by_username(username)
        if existing:
            flash("Username taken")
            return redirect(url_for("register"))
        pwd_hash = generate_password_hash(password)
        uid = db.add_user(username, pwd_hash)
        user = User(uid, username, pwd_hash)
        login_user(user)
        return redirect(url_for("index"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        user_row = db.find_user_by_username(username)
        if not user_row or not check_password_hash(user_row["password"], password):
            flash("Invalid credentials")
            return redirect(url_for("login"))
        user = User(user_row["id"], user_row["username"], user_row["password"])
        login_user(user)
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/", methods=["GET"])
@login_required
def index():
    # run recurring items for this user (simple monthly logic)
    run_recurring_jobs_for_user(current_user.id)

    rows = db.fetch_expenses(user_id=current_user.id)
    today = date.today()
    budgets = db.get_budgets(current_user.id, today.year, today.month)
    spent_summary, total_spent = db.get_month_summary(current_user.id, today.year, today.month)
    warnings = []
    for cat, limit in budgets.items():
        spent = spent_summary.get(cat, 0.0)
        pct = (spent / limit) * 100 if limit>0 else 0
        if pct >= 100:
            warnings.append(f"Budget exceeded for {cat}: spent {spent:.2f} / {limit:.2f}")
        elif pct >= 80:
            warnings.append(f"Approaching budget for {cat}: {pct:.0f}% used")
    return render_template("index.html", expenses=rows, categories=CATEGORIES,
                           default_date=today.isoformat(), default_year=today.year, default_month=today.month,
                           warnings=warnings, budgets=budgets)

@app.route("/add", methods=["POST"])
@login_required
def add():
    d = request.form.get("date", "").strip() or date.today().isoformat()
    category = request.form.get("category", "Other").strip()
    amount = request.form.get("amount", "0").strip()
    note = request.form.get("note", "").strip()
    try:
        amt = float(amount)
    except:
        flash("Invalid amount")
        return redirect(url_for("index"))
    db.add_expense(current_user.id, d, category, amt, note)
    flash("Expense added")
    return redirect(url_for("index"))

@app.route("/delete/<int:expense_id>", methods=["POST"])
@login_required
def delete(expense_id):
    db.delete_expense(expense_id)
    flash("Deleted")
    return redirect(url_for("index"))

@app.route("/set_budget", methods=["POST"])
@login_required
def set_budget():
    category = request.form.get("category")
    amount = float(request.form.get("amount", 0))
    year = int(request.form.get("year"))
    month = int(request.form.get("month"))
    db.set_budget(current_user.id, category, amount, year, month)
    flash("Budget set")
    return redirect(url_for("index"))

@app.route("/add_recurring", methods=["POST"])
@login_required
def add_recurring():
    start_date = request.form.get("start_date", date.today().isoformat())
    category = request.form.get("category", "Other")
    amount = float(request.form.get("amount", 0))
    note = request.form.get("note", "")
    interval = request.form.get("interval", "monthly")
    db.add_recurring(current_user.id, start_date, category, amount, note, interval)
    flash("Recurring added")
    return redirect(url_for("index"))

@app.route("/month_summary")
@login_required
def month_summary():
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    if not year or not month:
        return jsonify({"error":"year and month required"}), 400
    cat_sums, total = db.get_month_summary(current_user.id, year, month)
    labels = list(cat_sums.keys())
    data = [cat_sums[k] for k in labels]
    return jsonify({"labels": labels, "data": data, "total": total})

@app.route("/export_csv")
@login_required
def export_csv():
    rows = db.fetch_expenses(user_id=current_user.id, limit=10000)
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["id","date","category","amount","note"])
    for r in rows:
        cw.writerow([r.get("id"), r.get("date"), r.get("category"), r.get("amount"), r.get("note")])
    mem = io.BytesIO()
    mem.write(si.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", download_name="expenses.csv", as_attachment=True)

@app.route("/download_db")
@login_required
def download_db():
    db_path = os.path.join(os.getcwd(), "expenses.db")
    if not os.path.exists(db_path):
        abort(404)
    return send_file(db_path, mimetype="application/octet-stream", download_name="expenses.db", as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
