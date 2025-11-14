import sqlite3
from datetime import datetime

DB_NAME = "expenses.db"

def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date TEXT NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        note TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category TEXT,
        amount REAL,
        year INTEGER,
        month INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS recurring (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        start_date TEXT,
        category TEXT,
        amount REAL,
        note TEXT,
        interval TEXT,
        last_run TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    conn.commit()
    conn.close()

def add_user(username, password_hash):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password_hash))
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid

def find_user_by_username(username):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None

def fetch_expenses(user_id=None, limit=500):
    conn = get_conn()
    cur = conn.cursor()
    if user_id:
        cur.execute("SELECT id, date, category, amount, note FROM expenses WHERE user_id=? ORDER BY date DESC LIMIT ?", (user_id, limit))
    else:
        cur.execute("SELECT id, date, category, amount, note FROM expenses ORDER BY date DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_expense(user_id, date_str, category, amount, note=""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO expenses (user_id, date, category, amount, note) VALUES (?, ?, ?, ?, ?)",
                (user_id, date_str, category, amount, note))
    conn.commit()
    conn.close()

def delete_expense(expense_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()

def get_month_summary(user_id, year, month):
    start = f"{year:04d}-{month:02d}-01"
    if month == 12:
        next_month = f"{year+1:04d}-01-01"
    else:
        next_month = f"{year:04d}-{month+1:02d}-01"
    conn = get_conn()
    cur = conn.cursor()
    if user_id:
        cur.execute("""
            SELECT category, SUM(amount) as total FROM expenses
            WHERE user_id=? AND date >= ? AND date < ?
            GROUP BY category
        """, (user_id, start, next_month))
        rows = cur.fetchall()
        cur.execute("SELECT SUM(amount) FROM expenses WHERE user_id=? AND date >= ? AND date < ?", (user_id, start, next_month))
    else:
        cur.execute("""
            SELECT category, SUM(amount) as total FROM expenses
            WHERE date >= ? AND date < ?
            GROUP BY category
        """, (start, next_month))
        rows = cur.fetchall()
        cur.execute("SELECT SUM(amount) FROM expenses WHERE date >= ? AND date < ?", (start, next_month))
    total = cur.fetchone()[0] or 0.0
    conn.close()
    result = {r["category"]: float(r["total"]) for r in rows}
    return result, float(total)

def set_budget(user_id, category, amount, year, month):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM budgets WHERE user_id=? AND category=? AND year=? AND month=?", (user_id, category, year, month))
    cur.execute("INSERT INTO budgets (user_id, category, amount, year, month) VALUES (?, ?, ?, ?, ?)",
                (user_id, category, amount, year, month))
    conn.commit()
    conn.close()

def get_budgets(user_id, year, month):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT category, amount FROM budgets WHERE user_id=? AND year=? AND month=?", (user_id, year, month))
    rows = cur.fetchall()
    conn.close()
    return {r["category"]: float(r["amount"]) for r in rows}

def add_recurring(user_id, start_date, category, amount, note, interval="monthly"):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO recurring (user_id, start_date, category, amount, note, interval, last_run) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, start_date, category, amount, note, interval, None))
    conn.commit()
    conn.close()

def get_recurring(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM recurring WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_recurring_last_run(rec_id, last_run):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE recurring SET last_run=? WHERE id=?", (last_run, rec_id))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("DB initialized")
