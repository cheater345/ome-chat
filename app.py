from flask import Flask, render_template, request, session, redirect, jsonify
from flask_socketio import SocketIO, emit
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "hosojsjskshvksjsv"

socketio = SocketIO(app, cors_allowed_origins="*")

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


# ================= ROUTES =================
@app.route("/")
def home():
    if "user" not in session:
        return redirect("/register")
    return render_template("index.html")


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


# ================= GCASH =================
@app.route("/buy-premium", methods=["POST"])
def buy_premium():
    if "user" not in session:
        return redirect("/login")

    ref = request.form["reference"]

    conn = db()
    c = conn.cursor()
    c.execute("""
    INSERT INTO payments (user_email, ref_code, status)
    VALUES (?,?,?)
    """, (session["user"], ref, "pending"))
    conn.commit()
    conn.close()

    return redirect("/processing")


@app.route("/processing")
def processing():
    return render_template("processingpay.html")


# ================= SOCKET MATCH SYSTEM =================
waiting = []
partners = {}
users_online = {}


@socketio.on("connect")
def connect():
    users_online[request.sid] = session.get("user")


@socketio.on("disconnect")
def disconnect():
    sid = request.sid

    users_online.pop(sid, None)

    if sid in waiting:
        waiting.remove(sid)

    if sid in partners:
        p = partners[sid]
        emit("partner_left", room=p)
        partners.pop(p, None)
        partners.pop(sid, None)


# ================= FIXED MATCHING =================
@socketio.on("join")
def join():
    sid = request.sid

    if sid in waiting:
        waiting.remove(sid)

    if waiting:
        partner = waiting.pop(0)

        partners[sid] = partner
        partners[partner] = sid

        emit("matched", {"role": "caller"}, room=sid)
        emit("matched", {"role": "callee"}, room=partner)
    else:
        waiting.append(sid)


@socketio.on("signal")
def signal(data):
    sid = request.sid
    if sid in partners:
        emit("signal", data, room=partners[sid])


@socketio.on("next")
def next_user():
    sid = request.sid

    if sid in partners:
        p = partners[sid]
        emit("partner_left", room=p)
        partners.pop(p, None)
        partners.pop(sid, None)

    if sid in waiting:
        waiting.remove(sid)

    waiting.append(sid)


# ================= ADMIN =================
@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/login")

    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM payments ORDER BY id DESC")
    payments = c.fetchall()
    conn.close()

    return render_template("admin.html", payments=payments)


@app.route("/approve/<int:id>")
def approve(id):
    conn = db()
    c = conn.cursor()

    c.execute("UPDATE payments SET status='approved' WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect("/admin")


@app.route("/reject/<int:id>")
def reject(id):
    conn = db()
    c = conn.cursor()

    c.execute("UPDATE payments SET status='rejected' WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect("/admin")


# ================= RUN =================
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
