from database import get_db

def get_user_by_email(email):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    return cur.fetchone()

def create_user(name, email, password_hash, auth_provider="local"):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO users (name, email, password_hash, auth_provider)
        VALUES (?, ?, ?, ?)
    """, (name, email, password_hash, auth_provider))
    db.commit()