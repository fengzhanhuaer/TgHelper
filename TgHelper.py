import os
import sqlite3
import asyncio
import threading
import webbrowser
import socket
from datetime import datetime
from pathlib import Path
from secrets import token_urlsafe
from flask import Flask, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import socks
from telethon import TelegramClient
from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError
from telethon.sessions import StringSession

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "users.db"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me")
app.config["APP_NAME"] = "TgHelper"
app.config["TELEGRAM_API_ID"] = os.environ.get("TELEGRAM_API_ID")
app.config["TELEGRAM_API_HASH"] = os.environ.get("TELEGRAM_API_HASH")


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
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tg_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT NOT NULL,
            account_name TEXT NOT NULL,
            session_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tg_login_flows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT NOT NULL,
            phone TEXT NOT NULL,
            account_name TEXT,
            session_text TEXT NOT NULL,
            phone_code_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    db.commit()


def has_users() -> bool:
    db = get_db()
    cur = db.execute("SELECT COUNT(1) AS cnt FROM users")
    row = cur.fetchone()
    return row["cnt"] > 0


def create_session_token(username: str) -> str:
    token = token_urlsafe(32)
    db = get_db()
    db.execute(
        "INSERT INTO sessions (token, username, created_at) VALUES (?, ?, ?)",
        (token, username, datetime.utcnow().isoformat()),
    )
    db.commit()
    return token


def get_username_by_token(token: str) -> str | None:
    db = get_db()
    cur = db.execute("SELECT username FROM sessions WHERE token = ?", (token,))
    row = cur.fetchone()
    return row["username"] if row else None


def delete_session_token(token: str) -> None:
    db = get_db()
    db.execute("DELETE FROM sessions WHERE token = ?", (token,))
    db.commit()


async def send_tg_login_code(phone: str) -> tuple[bool, str | None, str | None, str | None]:
    api_id = app.config.get("TELEGRAM_API_ID")
    api_hash = app.config.get("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        return False, "未配置 TELEGRAM_API_ID/TELEGRAM_API_HASH。", None, None

    try:
        session = StringSession()
        client = TelegramClient(
            session,
            int(api_id),
            api_hash,
            proxy=get_configured_proxy(),
            connection_retries=1,
            retry_delay=1,
        )
        await client.connect()
        result = await client.send_code_request(phone)
        session_text = client.session.save()
        await client.disconnect()
        return True, None, session_text, result.phone_code_hash
    except TimeoutError:
        return False, "连接超时，请检查代理或网络。", None, None
    except Exception as exc:
        detail = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
        return False, f"发送验证码失败：{detail}", None, None


async def complete_tg_login(phone: str, session_text: str, phone_code_hash: str, code: str, password: str | None) -> tuple[bool, str | None, str | None, str | None]:
    api_id = app.config.get("TELEGRAM_API_ID")
    api_hash = app.config.get("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        return False, "未配置 TELEGRAM_API_ID/TELEGRAM_API_HASH。", None, None

    try:
        client = TelegramClient(
            StringSession(session_text),
            int(api_id),
            api_hash,
            proxy=get_configured_proxy(),
            connection_retries=1,
            retry_delay=1,
        )
        await client.connect()
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                await client.disconnect()
                return False, "需要两步验证密码。", None, None
            await client.sign_in(password=password)
        me = await client.get_me()
        final_session = client.session.save()
        await client.disconnect()
        display_name = me.username or (me.phone if hasattr(me, "phone") else None)
        return True, None, display_name, final_session
    except PhoneCodeInvalidError:
        return False, "验证码错误。", None, None
    except TimeoutError:
        return False, "连接超时，请检查代理或网络。", None, None
    except Exception as exc:
        detail = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
        return False, f"登录失败：{detail}", None, None


def require_login():
    if "user" in session:
        return session["user"]
    token = request.args.get("token") or request.form.get("token")
    if token:
        username = get_username_by_token(token)
        if username:
            session["user"] = username
            return username
    return None


def get_configured_proxy():
    host = app.config.get("PROXY_HOST")
    port = app.config.get("PROXY_PORT")
    if not host or not port:
        return None

    try:
        port_value = int(port)
    except ValueError:
        return None

    username = app.config.get("PROXY_USERNAME")
    password = app.config.get("PROXY_PASSWORD")
    if username or password:
        return (socks.SOCKS5, host, port_value, True, username, password)
    return (socks.SOCKS5, host, port_value, True)


def test_proxy_connection() -> tuple[bool, str]:
    proxy = get_configured_proxy()
    if not proxy:
        return False, "未配置代理。"

    api_id = app.config.get("TELEGRAM_API_ID")
    api_hash = app.config.get("TELEGRAM_API_HASH")
    if api_id and api_hash:
        try:
            async def _telethon_ping():
                session = StringSession()
                client = TelegramClient(
                    session,
                    int(api_id),
                    api_hash,
                    proxy=proxy,
                    connection_retries=1,
                    retry_delay=1,
                )
                await client.connect()
                await client.disconnect()

            run_async(_telethon_ping())
            return True, "代理可用，已连通 Telegram。"
        except Exception as exc:
            detail = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
            return False, f"代理不可用：{detail}"

    try:
        sock = socks.socksocket()
        sock.set_proxy(*proxy)
        sock.settimeout(6)
        sock.connect(("api.telegram.org", 443))
        sock.close()
        return True, "代理可用。"
    except Exception as exc:
        detail = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
        return False, f"代理不可用：{detail}"


def load_api_config():
    db = get_db()
    rows = db.execute(
        "SELECT key, value FROM app_settings WHERE key IN ('telegram_api_id', 'telegram_api_hash', 'proxy_host', 'proxy_port', 'proxy_username', 'proxy_password')"
    ).fetchall()
    data = {row["key"]: row["value"] for row in rows}
    app.config["TELEGRAM_API_ID"] = os.environ.get("TELEGRAM_API_ID") or data.get("telegram_api_id")
    app.config["TELEGRAM_API_HASH"] = os.environ.get("TELEGRAM_API_HASH") or data.get("telegram_api_hash")
    app.config["PROXY_HOST"] = data.get("proxy_host")
    app.config["PROXY_PORT"] = data.get("proxy_port")
    app.config["PROXY_USERNAME"] = data.get("proxy_username")
    app.config["PROXY_PASSWORD"] = data.get("proxy_password")


def run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@app.before_request
def ensure_db_initialized():
    init_db()
    load_api_config()


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
                token = create_session_token(username)
                return redirect(url_for("home", token=token))
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
            token = create_session_token(username)
            return redirect(url_for("home", token=token))
        error = "用户名或密码错误。"

    return render_template("login.html", error=error)


@app.route("/home")
def home():
    token = request.args.get("token")
    username = require_login()
    if not username:
        return redirect(url_for("login"))
    return render_template("home.html", username=username, token=token)


@app.route("/logout")
def logout():
    token = request.args.get("token")
    if token:
        delete_session_token(token)
    session.clear()
    return redirect(url_for("login"))


@app.route("/accounts/delete/<int:account_id>", methods=["POST"])
def delete_account(account_id: int):
    username = require_login()
    if not username:
        return redirect(url_for("login"))

    token = request.form.get("token")
    db = get_db()
    db.execute("DELETE FROM tg_accounts WHERE id = ? AND owner = ?", (account_id, username))
    db.commit()
    return redirect(url_for("accounts", token=token) if token else url_for("accounts"))


@app.route("/accounts")
def accounts():
    token = request.args.get("token")
    error = request.args.get("error")
    username = require_login()
    if not username:
        return redirect(url_for("login"))

    db = get_db()
    accounts_list = db.execute(
        "SELECT id, account_name, session_text, created_at FROM tg_accounts WHERE owner = ? ORDER BY id DESC",
        (username,),
    ).fetchall()

    return render_template(
        "accounts.html",
        username=username,
        token=token,
        accounts=accounts_list,
        error=error,
    )


@app.route("/settings/api", methods=["GET", "POST"])
def api_settings():
    token = request.args.get("token") or request.form.get("token")
    username = require_login()
    if not username:
        return redirect(url_for("login"))

    message = None
    if request.method == "POST":
        api_id = request.form.get("api_id", "").strip()
        api_hash = request.form.get("api_hash", "").strip()
        if not api_id or not api_hash:
            message = "API ID 和 API Hash 不能为空。"
        else:
            db = get_db()
            db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('telegram_api_id', ?)", (api_id,))
            db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('telegram_api_hash', ?)", (api_hash,))
            db.commit()
            load_api_config()
            message = "已保存。"

    return render_template(
        "api_settings.html",
        token=token,
        api_id=app.config.get("TELEGRAM_API_ID") or "",
        api_hash=app.config.get("TELEGRAM_API_HASH") or "",
        message=message,
    )


@app.route("/settings/proxy", methods=["GET", "POST"])
def proxy_settings():
    token = request.args.get("token") or request.form.get("token")
    username = require_login()
    if not username:
        return redirect(url_for("login"))

    message = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "test":
            ok, message = test_proxy_connection()
        else:
            proxy_host = request.form.get("proxy_host", "").strip()
            proxy_port = request.form.get("proxy_port", "").strip()
            proxy_username = request.form.get("proxy_username", "").strip()
            proxy_password = request.form.get("proxy_password", "").strip()

            if (proxy_host and not proxy_port) or (proxy_port and not proxy_host):
                message = "代理地址与端口需同时填写，或同时留空。"
            else:
                db = get_db()
                if proxy_host and proxy_port:
                    db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('proxy_host', ?)", (proxy_host,))
                    db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('proxy_port', ?)", (proxy_port,))
                    db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('proxy_username', ?)", (proxy_username,))
                    db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('proxy_password', ?)", (proxy_password,))
                else:
                    db.execute("DELETE FROM app_settings WHERE key IN ('proxy_host', 'proxy_port', 'proxy_username', 'proxy_password')")
                db.commit()
                load_api_config()
                message = "已保存。"

    return render_template(
        "proxy_settings.html",
        token=token,
        proxy_host=app.config.get("PROXY_HOST") or "",
        proxy_port=app.config.get("PROXY_PORT") or "",
        proxy_username=app.config.get("PROXY_USERNAME") or "",
        proxy_password=app.config.get("PROXY_PASSWORD") or "",
        message=message,
    )


@app.route("/tg/login/start", methods=["POST"])
def tg_login_start():
    username = require_login()
    if not username:
        return redirect(url_for("login"))

    token = request.form.get("token")
    phone = request.form.get("phone", "").strip()
    account_name = request.form.get("account_name", "").strip()
    if not phone:
        return redirect(url_for("accounts", token=token, error="请输入手机号。") if token else url_for("accounts", error="请输入手机号。"))

    ok, error, session_text, phone_code_hash = run_async(send_tg_login_code(phone))
    if not ok:
        return redirect(url_for("accounts", token=token, error=error) if token else url_for("accounts", error=error))

    db = get_db()
    cur = db.execute(
        "INSERT INTO tg_login_flows (owner, phone, account_name, session_text, phone_code_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (username, phone, account_name or None, session_text, phone_code_hash, datetime.utcnow().isoformat()),
    )
    db.commit()
    flow_id = cur.lastrowid
    return redirect(url_for("tg_login_verify", flow_id=flow_id, token=token) if token else url_for("tg_login_verify", flow_id=flow_id))


@app.route("/tg/login/verify", methods=["GET", "POST"])
def tg_login_verify():
    token = request.args.get("token") or request.form.get("token")
    flow_id = request.args.get("flow_id") or request.form.get("flow_id")
    username = require_login()
    if not username:
        return redirect(url_for("login"))
    if not flow_id:
        return redirect(url_for("accounts", token=token, error="缺少登录流程信息。") if token else url_for("accounts", error="缺少登录流程信息。"))

    db = get_db()
    flow = db.execute(
        "SELECT * FROM tg_login_flows WHERE id = ? AND owner = ?",
        (flow_id, username),
    ).fetchone()
    if not flow:
        return redirect(url_for("accounts", token=token, error="登录流程已过期。") if token else url_for("accounts", error="登录流程已过期。"))

    if request.method == "GET":
        return render_template(
            "tg_login_verify.html",
            token=token,
            flow_id=flow_id,
            phone=flow["phone"],
            error=request.args.get("error"),
        )

    code = request.form.get("code", "").strip()
    password = request.form.get("password", "").strip() or None
    if not code:
        return redirect(
            url_for("tg_login_verify", flow_id=flow_id, token=token, error="请输入验证码。")
            if token
            else url_for("tg_login_verify", flow_id=flow_id, error="请输入验证码。")
        )

    ok, error, display_name, final_session = run_async(
        complete_tg_login(
            phone=flow["phone"],
            session_text=flow["session_text"],
            phone_code_hash=flow["phone_code_hash"],
            code=code,
            password=password,
        )
    )
    if not ok:
        return redirect(
            url_for("tg_login_verify", flow_id=flow_id, token=token, error=error)
            if token
            else url_for("tg_login_verify", flow_id=flow_id, error=error)
        )

    account_name = flow["account_name"] or display_name or flow["phone"]
    db.execute(
        "INSERT INTO tg_accounts (owner, account_name, session_text, created_at) VALUES (?, ?, ?, ?)",
        (username, account_name, final_session or flow["session_text"], datetime.utcnow().isoformat()),
    )
    db.execute("DELETE FROM tg_login_flows WHERE id = ? AND owner = ?", (flow_id, username))
    db.commit()
    return redirect(url_for("accounts", token=token) if token else url_for("accounts"))


if __name__ == "__main__":
    def _open_browser():
        webbrowser.open("http://127.0.0.1:15018/")

    is_dev = os.environ.get("TGHELPER_DEV") == "1"
    if not is_dev or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(0.8, _open_browser).start()

    app.run(host="0.0.0.0", port=15018, debug=is_dev, use_reloader=is_dev)
