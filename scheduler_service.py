import threading
import time as time_module
from datetime import datetime

from database.db import get_connection
from services import reminder_service

_scheduler_started = False
_scheduler_mode = "UNKNOWN"


def check_due_schedules():
    """Finds enabled schedules whose time+day match right now, and logs one
    SCHEDULED_TRIGGER history event per due schedule per minute (no duplicates)."""
    now = datetime.now()
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


def _fallback_loop(interval_seconds):
    while True:
        try:
            check_due_schedules()
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
