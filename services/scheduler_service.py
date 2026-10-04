import threading
import time as time_module
from datetime import datetime, timedelta

from database.db import get_connection
from services import notification_service, reminder_service
from services.time_service import database_timestamp, now_kolkata

_scheduler_started = False
_scheduler_mode = "UNKNOWN"
_last_inventory_scan = None


def check_due_schedules():
    """Finds enabled schedules whose time+day match right now, and logs one
    SCHEDULED_TRIGGER history event per due schedule per minute (no duplicates)."""
    now = now_kolkata()
    current_time_str = now.strftime("%H:%M")
    # Our day codes: SU=0..SA=6. Python weekday(): Mon=0..Sun=6.
    our_weekday_index = (now.weekday() + 1) % 7
    day_codes = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"]
    today_code = day_codes[our_weekday_index]
    minute_window = now.strftime("%Y-%m-%d %H:%M")

    conn = get_connection()
    due = conn.execute(
        """SELECT s.*, m.medicine_name, m.dosage, m.compartment_number, m.active as medicine_active
           FROM schedules s JOIN medicines m ON m.id = s.medicine_id
           WHERE s.enabled = 1 AND s.schedule_time = ? AND m.active = 1""",
        (current_time_str,),
    ).fetchall()

    triggered = []
    for row in due:
        days = row["schedule_days"]
        if days != "daily" and today_code not in [d.strip().upper() for d in days.split(",")]:
            continue

        # Avoid duplicate trigger within the same minute (e.g. multiple check ticks)
        already_logged = conn.execute(
            """SELECT id FROM medicine_history
               WHERE patient_id = ? AND medicine_id = ? AND event_type = 'REMINDER'
               AND created_at LIKE ?""",
            (row["patient_id"], row["medicine_id"], f"{minute_window}%"),
        ).fetchone()
        if already_logged:
            continue

        patient = conn.execute("SELECT operating_mode FROM users WHERE id = ?", (row["patient_id"],)).fetchone()
        operating_mode = patient["operating_mode"] if patient else "fixed"
        triggered.append({"patient_id": row["patient_id"], "medicine_id": row["medicine_id"],
                           "medicine_name": row["medicine_name"], "scheduled_time": current_time_str,
                           "operating_mode": operating_mode})

    conn.close()

    # Create reminders (and send patient notifications) outside the connection above,
    # since reminder_service opens its own connections.
    for t in triggered:
        reminder_service.create_reminder(t["patient_id"], t["medicine_id"], t["scheduled_time"], t["operating_mode"])

    return triggered


def check_inventory_alerts(patient_id=None):
    """Notify patients/caretakers about expiring stock and due refills."""
    today = now_kolkata().date()
    expiry_limit = (today + timedelta(days=30)).isoformat()
    conn = get_connection()
    query = """SELECT m.*, u.name, u.phone, u.caretaker_phone
               FROM medicines m JOIN users u ON u.id = m.patient_id
               WHERE m.active = 1 AND (m.quantity <= m.refill_threshold
                   OR m.expiry_date <= ? OR m.refill_due_date <= ?)"""
    params = [expiry_limit, today.isoformat()]
    if patient_id is not None:
        query += " AND m.patient_id = ?"
        params.append(patient_id)
    medicines = conn.execute(query, params).fetchall()
    conn.close()

    delivered = []
    for medicine in medicines:
        alerts = []
        if medicine["quantity"] <= 0:
            alerts.append(("empty_compartment", notification_service.msg_empty(
                medicine["medicine_name"], medicine["compartment_number"], medicine["refill_threshold"]
            )))
        elif medicine["quantity"] <= medicine["refill_threshold"]:
            alerts.append(("low_stock", notification_service.msg_low_stock(
                medicine["medicine_name"], medicine["compartment_number"], medicine["quantity"], medicine["refill_threshold"]
            )))
        if medicine["expiry_date"] and medicine["expiry_date"] < today.isoformat():
            alerts.append(("expired", f"MEDBOT Expiry Alert: {medicine['medicine_name']} expired on {medicine['expiry_date']} (batch {medicine['batch_no'] or 'not specified'}). Do not dispense this stock."))
        elif medicine["expiry_date"] and today.isoformat() <= medicine["expiry_date"] <= expiry_limit:
            alerts.append(("expiry", f"MEDBOT Expiry Alert: {medicine['medicine_name']} expires on {medicine['expiry_date']} (batch {medicine['batch_no'] or 'not specified'}). Please review the stock."))
        if medicine["refill_due_date"] and medicine["refill_due_date"] <= today.isoformat():
            alerts.append(("refill_due", f"MEDBOT Refill Alert: A refill is due for {medicine['medicine_name']}. Current quantity: {medicine['quantity']}."))

        for alert_type, message in alerts:
            conn = get_connection()
            already_sent = conn.execute(
                """SELECT id FROM notifications WHERE patient_id = ? AND medicine_id = ?
                   AND notification_type = ? AND created_at >= ? LIMIT 1""",
                (medicine["patient_id"], medicine["id"], alert_type,
                 today.isoformat() + " 00:00:00"),
            ).fetchone()
            conn.close()
            if already_sent:
                continue
            notification_service.send_notification(
                medicine["patient_id"], medicine["caretaker_phone"], message,
                alert_type, "sms", medicine_id=medicine["id"],
            )
            delivered.append({"medicine_id": medicine["id"], "type": alert_type})
    return delivered


def run_daily_checks_if_due():
    global _last_inventory_scan
    today = now_kolkata().date()
    if now_kolkata().hour >= 8 and _last_inventory_scan != today:
        check_inventory_alerts()
        _last_inventory_scan = today
    notification_service.process_due_retries()


def _fallback_loop(interval_seconds):
    while True:
        try:
            check_due_schedules()
            run_daily_checks_if_due()
        except Exception as e:
            print("[MEDBOT scheduler] check failed:", e)
        time_module.sleep(interval_seconds)


def start_scheduler():
    """Starts the background schedule checker. Uses APScheduler if installed,
    otherwise falls back to a simple daemon thread (SCHEDULER SIMULATION MODE)."""
    global _scheduler_started, _scheduler_mode
    if _scheduler_started:
        return _scheduler_mode

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(check_due_schedules, "interval", seconds=30, id="medbot_schedule_check")
        scheduler.add_job(notification_service.process_due_retries, "interval", minutes=1,
                  id="medbot_notification_retries")
        scheduler.add_job(check_inventory_alerts, "cron", hour=8, minute=0,
                  timezone="Asia/Kolkata", id="medbot_daily_inventory_scan")
        scheduler.start()
        _scheduler_mode = "APSCHEDULER"
    except ImportError:
        thread = threading.Thread(target=_fallback_loop, args=(30,), daemon=True)
        thread.start()
        _scheduler_mode = "SCHEDULER_SIMULATION_MODE"

    _scheduler_started = True
    print(f"[MEDBOT] Schedule checker started in {_scheduler_mode}")
    return _scheduler_mode


def get_scheduler_mode():
    return _scheduler_mode
