from datetime import datetime
from database.db import get_connection


def compute_stock_status(quantity, refill_threshold):
    if quantity <= 0:
        return "EMPTY"
    if quantity <= refill_threshold:
        return "LOW"
    return "AVAILABLE"


def list_medicines(patient_id, search=None, active_filter=None):
    """active_filter: None (all), 1 (active only), 0 (inactive only)"""
    conn = get_connection()
    query = "SELECT * FROM medicines WHERE patient_id = ?"
    params = [patient_id]

    if search:
        query += " AND medicine_name LIKE ?"
        params.append(f"%{search}%")

    if active_filter in (0, 1):
        query += " AND active = ?"
        params.append(active_filter)

    query += " ORDER BY compartment_number ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    medicines = []
    for row in rows:
        m = dict(row)
        m["stock_status"] = compute_stock_status(m["quantity"], m["refill_threshold"])
        medicines.append(m)
    return medicines


def get_medicine(medicine_id, patient_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM medicines WHERE id = ? AND patient_id = ?", (medicine_id, patient_id)
    ).fetchone()
    conn.close()
    if not row:
        return None
    m = dict(row)
    m["stock_status"] = compute_stock_status(m["quantity"], m["refill_threshold"])
    return m


def compartment_taken(patient_id, compartment_number, exclude_id=None):
    conn = get_connection()
    if exclude_id:
        row = conn.execute(
            "SELECT id FROM medicines WHERE patient_id = ? AND compartment_number = ? AND id != ?",
            (patient_id, compartment_number, exclude_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM medicines WHERE patient_id = ? AND compartment_number = ?",
            (patient_id, compartment_number),
        ).fetchone()
    conn.close()
    return row is not None


def create_medicine(patient_id, medicine_name, dosage, quantity, compartment_number,
                     description, refill_threshold):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO medicines
           (patient_id, medicine_name, dosage, quantity, initial_quantity, compartment_number,
            description, refill_threshold, active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (patient_id, medicine_name.strip(), dosage.strip(), quantity, quantity,
         compartment_number, description.strip() if description else "", refill_threshold),
    )
    medicine_id = cur.lastrowid
    conn.commit()
    conn.close()
    return medicine_id


def update_medicine(medicine_id, patient_id, medicine_name, dosage, compartment_number,
                     description, refill_threshold):
    conn = get_connection()
    conn.execute(
        """UPDATE medicines
           SET medicine_name = ?, dosage = ?, compartment_number = ?, description = ?,
               refill_threshold = ?, updated_at = ?
           WHERE id = ? AND patient_id = ?""",
        (medicine_name.strip(), dosage.strip(), compartment_number,
         description.strip() if description else "", refill_threshold,
         datetime.now().isoformat(timespec="seconds"), medicine_id, patient_id),
    )
    conn.commit()
    conn.close()


def delete_medicine(medicine_id, patient_id):
    conn = get_connection()
    conn.execute("DELETE FROM medicines WHERE id = ? AND patient_id = ?", (medicine_id, patient_id))
    conn.commit()
    conn.close()


def set_active(medicine_id, patient_id, active):
    conn = get_connection()
    conn.execute(
        "UPDATE medicines SET active = ?, updated_at = ? WHERE id = ? AND patient_id = ?",
        (1 if active else 0, datetime.now().isoformat(timespec="seconds"), medicine_id, patient_id),
    )
    conn.commit()
    conn.close()


def refill_medicine(medicine_id, patient_id, quantity_added, new_threshold=None):
    """Adds stock, resets low-stock notification flag, logs a REFILL history event."""
    conn = get_connection()
    med = conn.execute(
        "SELECT * FROM medicines WHERE id = ? AND patient_id = ?", (medicine_id, patient_id)
    ).fetchone()
    if not med:
        conn.close()
        return None

    before = med["quantity"]
    after = before + quantity_added
    threshold = new_threshold if new_threshold is not None else med["refill_threshold"]
    now = datetime.now().isoformat(timespec="seconds")

    conn.execute(
        """UPDATE medicines
           SET quantity = ?, refill_threshold = ?, low_stock_notified = 0,
               last_refilled_at = ?, updated_at = ?
           WHERE id = ? AND patient_id = ?""",
        (after, threshold, now, now, medicine_id, patient_id),
    )
    conn.execute(
        """INSERT INTO medicine_history
           (patient_id, medicine_id, event_type, notification_status, created_at)
           VALUES (?, ?, 'REFILL', 'N/A', ?)""",
        (patient_id, medicine_id, now),
    )
    conn.commit()
    conn.close()
    return {"before": before, "added": quantity_added, "after": after}
