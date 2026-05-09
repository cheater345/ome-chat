from flask import Flask, render_template, request, session, redirect
from flask_socketio import SocketIO, emit
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from collections import deque
import threading

app = Flask(__name__)
app.secret_key = "change_this_secret"

socketio = SocketIO(app, cors_allowed_origins="*")

lock = threading.Lock()

# ================= DB =================
def db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        email TEXT UNIQUE,
        password TEXT,
        gender TEXT,
        premium INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        ref_code TEXT,
        status TEXT DEFAULT 'pending'
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= QUEUES =================
premium_waiting = deque()
normal_waiting = deque()
partners = {}
users_online = {}

# ================= ROUTES =================
@app.route("/")
def home():
    return redirect("/register")  # REGISTER BUNGAD


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=?", (email,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user"] = user["email"]
            session["premium"] = user["premium"]
            session["gender"] = user["gender"]
            session["admin"] = user["is_admin"]
            return redirect("/")
        return "Wrong login"

    return render_template("login.html")


@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        gender = request.form["gender"]

        conn = db()
        c = conn.cursor()
        c.execute("""
        INSERT INTO users (username,email,password,gender)
        VALUES (?,?,?,?)
        """, (username,email,password,gender))
        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("register.html")


# ================= SOCKET =================
@socketio.on("connect")
def connect():
    users_online[request.sid] = True


@socketio.on("disconnect")
def disconnect():
    sid = request.sid

    users_online.pop(sid, None)

    with lock:
        if sid in premium_waiting:
            premium_waiting.remove(sid)
        if sid in normal_waiting:
            normal_waiting.remove(sid)

        if sid in partners:
            partner = partners.pop(sid)
            partners.pop(partner, None)
            emit("partner_left", room=partner)


# ================= MATCH SYSTEM =================
@socketio.on("join")
def join():
    sid = request.sid
    is_premium = session.get("premium", 0)

    with lock:

        # remove duplicates
        if sid in premium_waiting:
            premium_waiting.remove(sid)
        if sid in normal_waiting:
            normal_waiting.remove(sid)

        # remove old partner
        if sid in partners:
            partner = partners.pop(sid)
            partners.pop(partner, None)

        partner = None

        # PRIORITY MATCHING
        if premium_waiting:
            partner = premium_waiting.popleft()
        elif normal_waiting:
            partner = normal_waiting.popleft()

        if partner and partner != sid:
            partners[sid] = partner
            partners[partner] = sid

            emit("matched", {"role": "caller"}, room=sid)
            emit("matched", {"role": "callee"}, room=partner)

        else:
            if is_premium:
                premium_waiting.append(sid)
            else:
                normal_waiting.append(sid)


@socketio.on("signal")
def signal(data):
    sid = request.sid

    if sid in partners:
        emit("signal", data, room=partners[sid])


@socketio.on("next")
def next_user():
    sid = request.sid
    is_premium = session.get("premium", 0)

    with lock:

        if sid in partners:
            partner = partners.pop(sid)
            partners.pop(partner, None)
            emit("partner_left", room=partner)

        if sid in premium_waiting:
            premium_waiting.remove(sid)
        if sid in normal_waiting:
            normal_waiting.remove(sid)

        if is_premium:
            premium_waiting.append(sid)
        else:
            normal_waiting.append(sid)


# ================= RUN =================
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
