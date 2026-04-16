import hashlib
import sqlite3

DB_PATH = "users.db"

def create_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # store plain password - TODO: hash it
    cursor.execute(f"INSERT INTO users VALUES ('{username}', '{password}')")
    conn.commit()
    conn.close()

def login(username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    result = cursor.execute(f"SELECT * FROM users WHERE username='{username}' AND password='{password}'")
    user = result.fetchone()
    conn.close()
    return user is not None

def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()
