import sqlite3
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def get_connection():
    """Return a new SQLite connection with dict-like row access and FK support."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables if they do not already exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone TEXT NOT NULL,
        caretaker_name TEXT NOT NULL,
        caretaker_phone TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        profile_image TEXT,
        face_data TEXT,
        face_consent INTEGER DEFAULT 0,
        operating_mode TEXT DEFAULT 'fixed',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS medicines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        medicine_name TEXT NOT NULL,
        dosage TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 0,
        initial_quantity INTEGER NOT NULL DEFAULT 0,
        compartment_number INTEGER NOT NULL,
        description TEXT,
        refill_threshold INTEGER NOT NULL DEFAULT 5,
        active INTEGER DEFAULT 1,
        low_stock_notified INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_dispensed_at TEXT,
        last_refilled_at TEXT,
        FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE (patient_id, compartment_number)
    );

    CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        medicine_id INTEGER NOT NULL,
        schedule_time TEXT NOT NULL,
        schedule_days TEXT NOT NULL DEFAULT 'daily',
        enabled INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (medicine_id) REFERENCES medicines(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS medicine_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        medicine_id INTEGER,
        scheduled_time TEXT,
        dispensed_time TEXT,
        collection_time TEXT,
        recognition_status TEXT,
        collected_status TEXT,
        intake_status TEXT,
        notification_status TEXT,
        operating_mode TEXT,
        event_type TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        medicine_id INTEGER,
        recipient_number TEXT,
        message TEXT NOT NULL,
        notification_type TEXT NOT NULL,
        channel TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS hardware (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL UNIQUE,
        esp32_ip TEXT DEFAULT '192.168.1.50',
        port INTEGER DEFAULT 80,
        connection_status TEXT DEFAULT 'disconnected',
        last_seen TEXT,
        FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS face_encodings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        angle_label TEXT NOT NULL,
        encoding_json TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS battery (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL UNIQUE,
        chemistry TEXT DEFAULT 'LiFePO4',
        series_cells INTEGER DEFAULT 4,
        parallel_cells INTEGER DEFAULT 1,
        capacity_mah INTEGER DEFAULT 3000,
        full_voltage REAL DEFAULT 14.6,
        low_voltage REAL DEFAULT 12.0,
        critical_voltage REAL DEFAULT 11.0,
        adc_pin INTEGER DEFAULT 34,
        voltage_divider_ratio REAL DEFAULT 5.0,
        calibration_factor REAL DEFAULT 1.0,
        percentage REAL DEFAULT 100,
        voltage REAL DEFAULT 14.6,
        charging INTEGER DEFAULT 0,
        status TEXT DEFAULT 'EXCELLENT',
        low_battery_notified INTEGER DEFAULT 0,
        critical_battery_notified INTEGER DEFAULT 0,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized at:", config.DATABASE_PATH)
