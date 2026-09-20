import re
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_connection

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INDIAN_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")


def valid_email(email):
    return bool(EMAIL_RE.match(email or ""))


def valid_indian_mobile(number):
    """Accepts a 10-digit Indian mobile number, optionally prefixed with +91 or 0."""
    if not number:
        return False
    cleaned = number.strip().replace(" ", "").replace("-", "")
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]
    return bool(INDIAN_MOBILE_RE.match(cleaned))


def normalize_mobile(number):
    cleaned = number.strip().replace(" ", "").replace("-", "")
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]
    return cleaned


def get_user_by_email(email):
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
    conn.close()
    return row


def get_user_by_id(user_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row


def create_user(name, email, phone, caretaker_name, caretaker_phone, password):
    """Creates a user + default hardware/battery rows. Returns new user id."""
    password_hash = generate_password_hash(password)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO users (name, email, phone, caretaker_name, caretaker_phone, password_hash)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name.strip(), email.lower().strip(), normalize_mobile(phone),
         caretaker_name.strip(), normalize_mobile(caretaker_phone), password_hash),
    )
    user_id = cur.lastrowid

    # Every patient gets a default hardware config and battery record
    cur.execute(
        "INSERT INTO hardware (patient_id, esp32_ip, port, connection_status) VALUES (?, ?, ?, 'disconnected')",
        (user_id, "192.168.1.50", 80),
    )
    cur.execute(
        """INSERT INTO battery (patient_id, chemistry, series_cells, parallel_cells, capacity_mah,
           full_voltage, low_voltage, critical_voltage, percentage, voltage, status)
           VALUES (?, 'LiFePO4', 4, 1, 3000, 14.6, 12.0, 11.0, 100, 14.6, 'EXCELLENT')""",
        (user_id,),
    )
    conn.commit()
    conn.close()
    return user_id


def verify_password(user_row, password):
    return check_password_hash(user_row["password_hash"], password)
