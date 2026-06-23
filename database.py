import os
import sqlite3

DB_PATH = os.environ.get("DATABASE_PATH", "/data/fractoscan.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")          # ← مهم جداً
    conn.execute("PRAGMA synchronous=NORMAL")       # ← توازن بين الأمان والسرعة
    conn.row_factory = sqlite3.Row
    return conn