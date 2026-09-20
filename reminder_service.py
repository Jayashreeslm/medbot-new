from datetime import datetime
from database.db import get_connection
from services import notification_service, hardware_service


def get_pending_reminders(patient_id):
    """Reminders that have not yet been marked collected — drives the popup."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT h.*, m.medicine_name, m.dosage, m.compartment_number
           FROM medicine_history h
           JOIN medicines m ON m.id = h.medicine_id
           WHERE h.patient_id = ? AND h.event_type = 'REMINDER' AND h.collected_status = 'PENDING'
           ORDER BY h.created_at ASC""",
        (patient_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_reminder(patient_id, medicine_id, scheduled_time, operating_mode):
    """Called by the scheduler when a schedule is due. Logs the reminder and
    sends the patient notification. Returns the new history row id."""
    conn = get_connection()
    patient = conn.execute("SELECT * FROM users WHERE id = ?", (patient_id,)).fetchone()
    medicine = conn.execute("SELECT * FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur = conn.cursor()
    cur.execute(
        """INSERT INTO medicine_history
           (patient_id, medicine_id, scheduled_time, event_type, collected_status,
            intake_status, recognition_status, operating_mode, notification_status, created_at)
           VALUES (?, ?, ?, 'REMINDER', 'PENDING', 'PENDING', 'NOT_VERIFIED', ?, 'PENDING', ?)""",
        (patient_id, medicine_id, scheduled_time, operating_mode, now),
    )
    reminder_id = cur.lastrowid
    conn.commit()
    conn.close()

    status = notification_service.send_notification(
        patient_id,
        patient["phone"],
        notification_service.msg_reminder(patient["name"], medicine["medicine_name"],
                                           medicine["dosage"], medicine["compartment_number"], scheduled_time),
        "reminder", "sms", medicine_id=medicine_id,
    )

    conn = get_connection()
    conn.execute("UPDATE medicine_history SET notification_status = ? WHERE id = ?", (status, reminder_id))
    conn.commit()
    conn.close()
    return reminder_id


def dispense_medicine(reminder_id, patient_id):
    """Validates and dispenses one dose. Enforces: correct patient, correct medicine,
    correct compartment, sufficient stock, active medicine. Never allows negative quantity."""
    conn = get_connection()
    reminder = conn.execute(
        "SELECT * FROM medicine_history WHERE id = ? AND patient_id = ?", (reminder_id, patient_id)
    ).fetchone()
    if not reminder:
        conn.close()
        return {"error": "Reminder not found."}, 404

    medicine = conn.execute(
        "SELECT * FROM medicines WHERE id = ? AND patient_id = ?", (reminder["medicine_id"], patient_id)
    ).fetchone()
    if not medicine:
        conn.close()
        return {"error": "Medicine not found."}, 404

    patient = conn.execute("SELECT * FROM users WHERE id = ?", (patient_id,)).fetchone()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not medicine["active"]:
        conn.close()
        return {"error": "Medicine is inactive. Cannot dispense."}, 409

    if medicine["quantity"] <= 0:
        conn.execute(
            "UPDATE medicine_history SET event_type = 'DISPENSE_FAILED_EMPTY' WHERE id = ?", (reminder_id,)
        )
        conn.commit()
        conn.close()
        notification_service.send_notification(
            patient_id, patient["caretaker_phone"],
            notification_service.msg_empty(medicine["medicine_name"], medicine["compartment_number"]),
            "empty_compartment", "sms", medicine_id=medicine["id"],
        )
        return {"error": "COMPARTMENT EMPTY. Cannot dispense.", "stock_status": "EMPTY"}, 409

    dose = 1  # one unit per dispense event, per compartment
    if medicine["quantity"] < dose:
        conn.execute(
            "UPDATE medicine_history SET event_type = 'DISPENSE_FAILED_INSUFFICIENT_STOCK' WHERE id = ?",
            (reminder_id,),
        )
        conn.commit()
        conn.close()
        notification_service.send_notification(
            patient_id, patient["caretaker_phone"],
            notification_service.msg_insufficient_stock(
                medicine["medicine_name"], medicine["compartment_number"], medicine["quantity"], dose
            ),
            "insufficient_stock", "sms", medicine_id=medicine["id"],
        )
        return {"error": "INSUFFICIENT MEDICINE STOCK.", "available": medicine["quantity"], "required": dose}, 409

    new_quantity = max(0, medicine["quantity"] - dose)
    conn.execute(
        "UPDATE medicines SET quantity = ?, last_dispensed_at = ?, updated_at = ? WHERE id = ?",
        (new_quantity, now, now, medicine["id"]),
    )
    conn.execute(
        "UPDATE medicine_history SET dispensed_time = ? WHERE id = ?", (now, reminder_id)
    )
    conn.commit()
    conn.close()

    notification_service.send_notification(
        patient_id, patient["phone"],
        notification_service.msg_dispensed(medicine["medicine_name"], patient["name"],
                                            medicine["dosage"], medicine["compartment_number"]),
        "dispensed", "sms", medicine_id=medicine["id"],
    )

    hw_result, _ = hardware_service.send_command(
        patient_id, "DISPENSE_MEDICINE",
        {"compartment": medicine["compartment_number"], "medicine_id": medicine["id"]},
    )

    _check_stock_alerts(medicine["id"], patient_id, new_quantity, medicine["refill_threshold"])

    return {"message": "Medicine dispensed successfully.", "new_quantity": new_quantity,
            "hardware": hw_result}, 200


def _check_stock_alerts(medicine_id, patient_id, new_quantity, refill_threshold):
    conn = get_connection()
    medicine = conn.execute("SELECT * FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
    patient = conn.execute("SELECT * FROM users WHERE id = ?", (patient_id,)).fetchone()

    if new_quantity == 0:
        notification_service.send_notification(
            patient_id, patient["caretaker_phone"],
            notification_service.msg_empty(medicine["medicine_name"], medicine["compartment_number"]),
            "empty_compartment", "sms", medicine_id=medicine_id,
        )
    elif new_quantity <= refill_threshold and not medicine["low_stock_notified"]:
        notification_service.send_notification(
            patient_id, patient["caretaker_phone"],
            notification_service.msg_low_stock(medicine["medicine_name"], medicine["compartment_number"], new_quantity),
            "low_stock", "sms", medicine_id=medicine_id,
        )
        conn.execute("UPDATE medicines SET low_stock_notified = 1 WHERE id = ?", (medicine_id,))
        conn.commit()

    conn.close()


def mark_collected(reminder_id, patient_id):
    conn = get_connection()
    reminder = conn.execute(
        "SELECT * FROM medicine_history WHERE id = ? AND patient_id = ?", (reminder_id, patient_id)
    ).fetchone()
    if not reminder:
        conn.close()
        return {"error": "Reminder not found."}, 404

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """UPDATE medicine_history
           SET collection_time = ?, collected_status = 'COLLECTED', intake_status = 'COLLECTED'
           WHERE id = ?""",
        (now, reminder_id),
    )
    conn.commit()
    conn.close()
    return {"message": "Marked as collected."}, 200
