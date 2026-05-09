import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect("database.db")
c = conn.cursor()

# delete old admin
c.execute("DELETE FROM users WHERE email='admin@gmail.com'")

# insert fresh hashed admin
hashed = generate_password_hash("admin123")

c.execute("""
INSERT INTO users (username,email,password,gender,premium,is_admin)
VALUES (?,?,?,?,?,?)
""", (
    "admin",
    "admin@gmail.com",
    hashed,
    "Male",
    1,
    1
))

conn.commit()
conn.close()

print("ADMIN FIXED SUCCESSFULLY")
