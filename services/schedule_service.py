from datetime import datetime, timedelta
from database.db import get_connection

DAY_CODES = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"]


def list_schedules(patient_id, medicine_id=None):
    conn = get_connection()
    query = """
        SELECT s.*, m.medicine_name, m.dosage, m.compartment_number, m.active as medicine_active
        FROM schedules s
        JOIN medicines m ON m.id = s.medicine_id
        WHERE s.patient_id = ?
    """
    params = [patient_id]
    if medicine_id:
        query += " AND s.medicine_id = ?"
        params.append(medicine_id)
    query += " ORDER BY s.schedule_time ASC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    schedules = []
    for row in rows:
        s = dict(row)
        s["next_trigger"] = compute_next_trigger(s["schedule_time"], s["schedule_days"], s["enabled"])
        schedules.append(s)
    return schedules


def get_schedule(schedule_id, patient_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM schedules WHERE id = ? AND patient_id = ?", (schedule_id, patient_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def medicine_belongs_to_patient(medicine_id, patient_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM medicines WHERE id = ? AND patient_id = ?", (medicine_id, patient_id)
    ).fetchone()
    conn.close()
    return row is not None


def create_schedule(patient_id, medicine_id, schedule_time, schedule_days):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO schedules (patient_id, medicine_id, schedule_time, schedule_days, enabled)
           VALUES (?, ?, ?, ?, 1)""",
        (patient_id, medicine_id, schedule_time, schedule_days),
    )
    schedule_id = cur.lastrowid
    conn.commit()
    conn.close()
    return schedule_id


def update_schedule(schedule_id, patient_id, schedule_time, schedule_days):
    conn = get_connection()
    conn.execute(
        """UPDATE schedules SET schedule_time = ?, schedule_days = ?
           WHERE id = ? AND patient_id = ?""",
        (schedule_time, schedule_days, schedule_id, patient_id),
    )
    conn.commit()
    conn.close()


def delete_schedule(schedule_id, patient_id):
    conn = get_connection()
    conn.execute("DELETE FROM schedules WHERE id = ? AND patient_id = ?", (schedule_id, patient_id))
    conn.commit()
    conn.close()


def set_enabled(schedule_id, patient_id, enabled):
    conn = get_connection()
    conn.execute(
        "UPDATE schedules SET enabled = ? WHERE id = ? AND patient_id = ?",
        (1 if enabled else 0, schedule_id, patient_id),
    )
    conn.commit()
    conn.close()


def compute_next_trigger(schedule_time, schedule_days, enabled, now=None):
    """Returns ISO datetime string of the next occurrence, or None if disabled."""
    if not enabled:
        return None

    now = now or datetime.now()
    hour, minute = map(int, schedule_time.split(":"))

    if schedule_days == "daily":
        allowed_weekdays = set(range(7))
    else:
        codes = [d.strip().upper() for d in schedule_days.split(",") if d.strip()]
        allowed_weekdays = {DAY_CODES.index(c) for c in codes if c in DAY_CODES}
        if not allowed_weekdays:
            allowed_weekdays = set(range(7))

    for days_ahead in range(0, 8):
        candidate_date = now.date() + timedelta(days=days_ahead)
        candidate = datetime(candidate_date.year, candidate_date.month, candidate_date.day, hour, minute)
        # Python weekday(): Monday=0 ... Sunday=6. Our DAY_CODES index: SU=0. Convert.
        python_weekday = candidate.weekday()  # Mon=0..Sun=6
        our_weekday = (python_weekday + 1) % 7  # SU=0..SA=6
        if our_weekday in allowed_weekdays and candidate > now:
            return candidate.isoformat(timespec="seconds")
    return None
