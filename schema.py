import sqlite3
import os

DB_PATH = "/data/fractoscan.db"

def create_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ----------------------
    # USERS TABLE
    # ----------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            auth_provider TEXT DEFAULT 'local',
            language TEXT DEFAULT 'en',
            phone TEXT,
            institution TEXT,
            refresh_token TEXT,
            otp TEXT,
            otp_expire INTEGER,
            otp_verified INTEGER DEFAULT 0,
            otp_last_sent INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # ----------------------
    # SCANS TABLE
    # ----------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            patient_name TEXT NOT NULL,
            patient_age INTEGER NOT NULL,
            gender TEXT CHECK(gender IN ('male','female')) DEFAULT 'male',
            anatomical_region TEXT,
            status TEXT CHECK(status IN ('uploading','analyzing','done','failed','cancelled')) DEFAULT 'uploading',
            image_url TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
    """)

    # ----------------------
    # REPORTS TABLE
    # ----------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            report_id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER UNIQUE NOT NULL,
            fracture_detected INTEGER NOT NULL CHECK (fracture_detected IN (0,1)),
            confidence REAL,
            fracture_type TEXT,
            location TEXT,
            report_pdf_url TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scan_id) REFERENCES scans(scan_id) ON DELETE CASCADE
        );
    """)

    # ----------------------
    # NOTIFICATIONS TABLE
    # ----------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0 CHECK (is_read IN (0,1)),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
    """)

    # ----------------------
    # ACTIVE ANALYSIS TABLE (للـ Cancel Scan)
    # ----------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_analysis (
            scan_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            thread_id TEXT,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
    """)

    # ----------------------
    # INDEXES (Performance)
    # ----------------------
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scans_user_id ON scans(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);")

    # إضافة عمود image_url للجداول القديمة
    try:
        cursor.execute("ALTER TABLE scans ADD COLUMN image_url TEXT")
        print("✅ Added image_url column to existing scans table")
    except:
        pass

    conn.commit()
    conn.close()
    print("Database and tables created successfully ✔")

if __name__ == "__main__":
    create_db()