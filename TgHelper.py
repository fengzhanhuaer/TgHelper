import os
import sqlite3
from pathlib import Path
from flask import Flask, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "users.db"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me")
app.config["APP_NAME"] = "TgHelper"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
        """
    )
    db.commit()


def has_users() -> bool:
    db = get_db()
    cur = db.execute("SELECT COUNT(1) AS cnt FROM users")
    row = cur.fetchone()
    return row["cnt"] > 0


@app.before_request
def ensure_db_initialized():
    init_db()


@app.context_processor
def inject_app_name():
    return {"app_name": app.config.get("APP_NAME", "TgHelper")}


@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("home"))
    if not has_users():
        return redirect(url_for("register"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if has_users() and "user" in session:
        return redirect(url_for("home"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm", "").strip()

        if not username or not password:
            error = "用户名和密码不能为空。"
        elif password != confirm:
            error = "两次输入的密码不一致。"
        else:
            db = get_db()
            try:
                db.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                db.commit()
                session["user"] = username
                return redirect(url_for("home"))
            except sqlite3.IntegrityError:
                error = "用户名已存在。"

    return render_template("register.html", error=error, has_users=has_users())


@app.route("/login", methods=["GET", "POST"])
def login():
    if not has_users():
        return redirect(url_for("register"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        db = get_db()
        cur = db.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user"] = username
            return redirect(url_for("home"))
        error = "用户名或密码错误。"

    return render_template("login.html", error=error)


@app.route("/home")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("home.html", username=session["user"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=15018, debug=False)
