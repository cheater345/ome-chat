# app.py

from flask import Flask, render_template, request, redirect, session, jsonify
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = "putangina_826292626_jshejekehehemo"

socketio = SocketIO(app, cors_allowed_origins="*")

# ================= DATABASE =================

def db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
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
    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        reference TEXT,
        status TEXT DEFAULT 'pending'
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= CREATE ADMIN =================

def create_admin():

    conn = db()
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE email='admin@gmail.com'")
    admin = c.fetchone()

    if not admin:

        c.execute("""
        INSERT INTO users(username,email,password,gender,premium,is_admin)
        VALUES(?,?,?,?,?,?)
        """, (
            "admin",
            "admin@gmail.com",
            generate_password_hash("admin123"),
            "Male",
            1,
            1
        ))

        conn.commit()

    conn.close()

create_admin()

# ================= ROUTES =================

@app.route("/")
def home():

    if "user" not in session:
        return redirect("/login")

    return render_template("index.html")


# ================= LOGIN =================

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
            session["gender"] = user["gender"]
            session["premium"] = user["premium"]
            session["admin"] = user["is_admin"]

            return redirect("/")

        return "Wrong login"

    return render_template("login.html")


# ================= REGISTER =================

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
        INSERT INTO users(username,email,password,gender)
        VALUES(?,?,?,?)
        """, (
            username,
            email,
            password,
            gender
        ))

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("register.html")


# ================= PREMIUM =================

@app.route("/get-premium")
def get_premium():

    if "user" not in session:
        return jsonify({"premium":0})

    conn = db()
    c = conn.cursor()

    c.execute("""
    SELECT premium
    FROM users
    WHERE email=?
    """, (session["user"],))

    user = c.fetchone()

    conn.close()

    return jsonify({
        "premium": user["premium"]
    })


# ================= BUY PREMIUM =================

@app.route("/buy-premium", methods=["POST"])
def buy_premium():

    ref = request.form["reference"]

    conn = db()
    c = conn.cursor()

    c.execute("""
    INSERT INTO payments(user_email,reference,status)
    VALUES(?,?,?)
    """, (
        session["user"],
        ref,
        "pending"
    ))

    conn.commit()
    conn.close()

    return redirect(f"/processing?ref={ref}")


@app.route("/processing")
def processing():

    ref = request.args.get("ref")

    return render_template("processingpay.html", ref=ref)


# ================= ADMIN LOGIN =================

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = db()
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE email=?", (email,))
        user = c.fetchone()

        conn.close()

        if user and user["is_admin"] == 1 and check_password_hash(user["password"], password):

            session["admin"] = True

            return redirect("/admin")

        return "Invalid admin"

    return render_template("admin_login.html")


# ================= ADMIN PANEL =================

@app.route("/admin")
def admin():

    if not session.get("admin"):
        return redirect("/admin/login")

    conn = db()
    c = conn.cursor()

    c.execute("SELECT * FROM payments ORDER BY id DESC")
    payments = c.fetchall()

    conn.close()

    return render_template("admin.html", payments=payments)


@app.route("/admin/approve/<int:id>")
def approve(id):

    if not session.get("admin"):
        return "Forbidden"

    conn = db()
    c = conn.cursor()

    c.execute("SELECT * FROM payments WHERE id=?", (id,))
    pay = c.fetchone()

    if pay:

        c.execute("""
        UPDATE users
        SET premium=1
        WHERE email=?
        """, (pay["user_email"],))

        c.execute("""
        UPDATE payments
        SET status='approved'
        WHERE id=?
        """, (id,))

    conn.commit()
    conn.close()

    return redirect("/admin")


@app.route("/admin/reject/<int:id>")
def reject(id):

    if not session.get("admin"):
        return "Forbidden"

    conn = db()
    c = conn.cursor()

    c.execute("""
    UPDATE payments
    SET status='rejected'
    WHERE id=?
    """, (id,))

    conn.commit()
    conn.close()

    return redirect("/admin")


# ================= MATCHING =================

waiting = []
partners = {}
user_data = {}


@socketio.on("connect")
def connect():

    user_data[request.sid] = {
        "gender": session.get("gender"),
        "filter": "all"
    }


# ================= GENDER FILTER =================

@socketio.on("setFilter")
def set_filter(data):

    sid = request.sid

    conn = db()
    c = conn.cursor()

    c.execute("""
    SELECT premium
    FROM users
    WHERE email=?
    """, (session["user"],))

    user = c.fetchone()

    conn.close()

    if not user:
        return

    if user["premium"] != 1:
        return

    user_data[sid]["filter"] = data["gender"]


# ================= JOIN =================

@socketio.on("join")
def join():

    sid = request.sid

    my_gender = user_data[sid]["gender"]
    my_filter = user_data[sid]["filter"]

    found = None

    for other in waiting:

        if other == sid:
            continue

        other_gender = user_data[other]["gender"]
        other_filter = user_data[other]["filter"]

        # MY FILTER
        if my_filter == "boy" and other_gender != "Male":
            continue

        if my_filter == "girl" and other_gender != "Female":
            continue

        # THEIR FILTER
        if other_filter == "boy" and my_gender != "Male":
            continue

        if other_filter == "girl" and my_gender != "Female":
            continue

        found = other
        break

    if found:

        waiting.remove(found)

        partners[sid] = found
        partners[found] = sid

        emit("matched", {
            "role":"caller"
        }, room=sid)

        emit("matched", {
            "role":"callee"
        }, room=found)

    else:

        if sid not in waiting:
            waiting.append(sid)


# ================= SIGNALING =================

@socketio.on("signal")
def signal(data):

    sid = request.sid

    if sid in partners:

        emit("signal", data, room=partners[sid])


# ================= CHAT =================

@socketio.on("msg")
def msg(data):

    sid = request.sid

    if sid in partners:
        emit("msg", data, room=partners[sid])


# ================= NEXT =================

@socketio.on("next")
def next_user():

    sid = request.sid

    if sid in partners:

        p = partners[sid]

        emit("end", room=p)

        partners.pop(p, None)
        partners.pop(sid, None)

    if sid not in waiting:
        waiting.append(sid)


# ================= DISCONNECT =================

@socketio.on("disconnect")
def disconnect():

    sid = request.sid

    if sid in waiting:
        waiting.remove(sid)

    if sid in partners:

        p = partners[sid]

        emit("end", room=p)

        partners.pop(p, None)
        partners.pop(sid, None)

    user_data.pop(sid, None)


# ================= START =================

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
