import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

import config
from database.db import init_db, get_connection
import models
from services import medicine_service, schedule_service, scheduler_service, reminder_service, notification_service, face_service, hardware_service, battery_service, history_service

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

init_db()
scheduler_service.start_scheduler()


# ---------- Auth helpers ----------

def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        if models.get_user_by_id(session["user_id"]) is None:
            # Session points at a user that no longer exists (e.g. the
            # database was reset). Clear the stale session instead of
            # crashing every route that assumes current_user() is not None.
            session.clear()
            flash("Your session expired. Please log in again.", "error")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped


def current_user():
    if "user_id" not in session:
        return None
    return models.get_user_by_id(session["user_id"])


@app.context_processor
def inject_current_user_name():
    user = current_user()
    return {"current_user_name": user["name"] if user else ""}


# ---------- Public routes ----------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/debug/face-status")
def debug_face_status():
    return jsonify({
        "available": face_service.FACE_DEPENDENCIES_AVAILABLE,
        "error": face_service.FACE_DEPENDENCIES_ERROR,
    })


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    caretaker_name = request.form.get("caretaker_name", "").strip()
    caretaker_phone = request.form.get("caretaker_phone", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    errors = []
    if not all([name, email, phone, caretaker_name, caretaker_phone, password, confirm_password]):
        errors.append("All fields are required.")
    if email and not models.valid_email(email):
        errors.append("Enter a valid email address.")
    if phone and not models.valid_indian_mobile(phone):
        errors.append("Enter a valid 10-digit Indian mobile number for the patient.")
    if caretaker_phone and not models.valid_indian_mobile(caretaker_phone):
        errors.append("Enter a valid 10-digit Indian mobile number for the caretaker.")
    if password and len(password) < 6:
        errors.append("Password must be at least 6 characters.")
    if password != confirm_password:
        errors.append("Passwords do not match.")
    if email and models.get_user_by_email(email):
        errors.append("An account with this email already exists.")

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("register.html", form=request.form)

    user_id = models.create_user(name, email, phone, caretaker_name, caretaker_phone, password)
    session["user_id"] = user_id
    flash("Registration successful. Welcome to MEDBOT.", "success")
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user = models.get_user_by_email(email) if email else None
    if not user or not models.verify_password(user, password):
        flash("Invalid email or password.", "error")
        return render_template("login.html", form=request.form)

    session["user_id"] = user["id"]
    flash(f"Welcome back, {user['name']}.", "success")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------- Protected routes ----------

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    conn = get_connection()
    medicine_count = conn.execute(
        "SELECT COUNT(*) as c FROM medicines WHERE patient_id = ?", (user["id"],)
    ).fetchone()["c"]
    battery = conn.execute(
        "SELECT * FROM battery WHERE patient_id = ?", (user["id"],)
    ).fetchone()
    hardware = conn.execute(
        "SELECT * FROM hardware WHERE patient_id = ?", (user["id"],)
    ).fetchone()
    conn.close()
    return render_template(
        "dashboard.html",
        user=user,
        medicine_count=medicine_count,
        battery=battery,
        hardware=hardware,
    )


@app.route("/profile")
@login_required
def profile():
    user = current_user()
    return render_template("profile.html", user=user)


@app.route("/medicines")
@login_required
def medicines_page():
    user = current_user()
    search = request.args.get("search", "").strip() or None
    status_filter = request.args.get("status", "all")
    active_filter = None
    if status_filter == "active":
        active_filter = 1
    elif status_filter == "inactive":
        active_filter = 0

    meds = medicine_service.list_medicines(user["id"], search=search, active_filter=active_filter)
    return render_template(
        "medicines.html", user=user, medicines=meds, search=search or "", status_filter=status_filter
    )


# ---------- Medicine API (JSON, authenticated, patient-isolated) ----------

def _validate_medicine_payload(data, patient_id, exclude_id=None):
    errors = []
    name = (data.get("medicine_name") or "").strip()
    dosage = (data.get("dosage") or "").strip()
    description = (data.get("description") or "").strip()

    try:
        compartment_number = int(data.get("compartment_number"))
        if compartment_number < 1:
            errors.append("Compartment number must be a positive integer.")
    except (TypeError, ValueError):
        compartment_number = None
        errors.append("Compartment number is required and must be a number.")

    try:
        refill_threshold = int(data.get("refill_threshold"))
        if refill_threshold < 0:
            errors.append("Refill threshold cannot be negative.")
    except (TypeError, ValueError):
        refill_threshold = None
        errors.append("Refill threshold is required and must be a number.")

    if not name:
        errors.append("Medicine name is required.")
    if not dosage:
        errors.append("Dosage is required.")

    if compartment_number is not None and medicine_service.compartment_taken(
        patient_id, compartment_number, exclude_id=exclude_id
    ):
        errors.append(f"Compartment {compartment_number} is already assigned to another medicine.")

    return errors, name, dosage, description, compartment_number, refill_threshold


@app.route("/api/medicines", methods=["GET", "POST"])
@login_required
def api_medicines():
    user = current_user()

    if request.method == "GET":
        meds = medicine_service.list_medicines(user["id"])
        return jsonify({"medicines": meds}), 200

    data = request.get_json(silent=True) or request.form
    errors, name, dosage, description, compartment_number, refill_threshold = _validate_medicine_payload(
        data, user["id"]
    )

    try:
        quantity = int(data.get("quantity"))
        if quantity < 0:
            errors.append("Quantity cannot be negative.")
    except (TypeError, ValueError):
        quantity = None
        errors.append("Quantity is required and must be a number.")

    if errors:
        return jsonify({"errors": errors}), 400

    medicine_id = medicine_service.create_medicine(
        user["id"], name, dosage, quantity, compartment_number, description, refill_threshold
    )
    medicine = medicine_service.get_medicine(medicine_id, user["id"])
    return jsonify({"message": "Medicine added successfully.", "medicine": medicine}), 201


@app.route("/api/medicines/<int:medicine_id>", methods=["PUT", "DELETE"])
@login_required
def api_medicine_detail(medicine_id):
    user = current_user()
    existing = medicine_service.get_medicine(medicine_id, user["id"])
    if not existing:
        return jsonify({"error": "Medicine not found."}), 404

    if request.method == "DELETE":
        medicine_service.delete_medicine(medicine_id, user["id"])
        return jsonify({"message": "Medicine deleted."}), 200

    data = request.get_json(silent=True) or request.form
    errors, name, dosage, description, compartment_number, refill_threshold = _validate_medicine_payload(
        data, user["id"], exclude_id=medicine_id
    )
    if errors:
        return jsonify({"errors": errors}), 400

    medicine_service.update_medicine(
        medicine_id, user["id"], name, dosage, compartment_number, description, refill_threshold
    )
    medicine = medicine_service.get_medicine(medicine_id, user["id"])
    return jsonify({"message": "Medicine updated.", "medicine": medicine}), 200


@app.route("/api/medicines/<int:medicine_id>/toggle", methods=["POST"])
@login_required
def api_medicine_toggle(medicine_id):
    user = current_user()
    existing = medicine_service.get_medicine(medicine_id, user["id"])
    if not existing:
        return jsonify({"error": "Medicine not found."}), 404

    medicine_service.set_active(medicine_id, user["id"], not existing["active"])
    medicine = medicine_service.get_medicine(medicine_id, user["id"])
    return jsonify({"message": "Status updated.", "medicine": medicine}), 200


@app.route("/api/medicines/<int:medicine_id>/refill", methods=["POST"])
@login_required
def api_medicine_refill(medicine_id):
    user = current_user()
    existing = medicine_service.get_medicine(medicine_id, user["id"])
    if not existing:
        return jsonify({"error": "Medicine not found."}), 404

    data = request.get_json(silent=True) or request.form
    try:
        quantity_added = int(data.get("quantity_added"))
        if quantity_added <= 0:
            return jsonify({"errors": ["Quantity added must be greater than 0."]}), 400
    except (TypeError, ValueError):
        return jsonify({"errors": ["Quantity added is required and must be a number."]}), 400

    new_threshold = None
    if data.get("refill_threshold") not in (None, ""):
        try:
            new_threshold = int(data.get("refill_threshold"))
        except (TypeError, ValueError):
            return jsonify({"errors": ["Refill threshold must be a number."]}), 400

    result = medicine_service.refill_medicine(medicine_id, user["id"], quantity_added, new_threshold)
    medicine = medicine_service.get_medicine(medicine_id, user["id"])
    return jsonify({"message": "Medicine refilled.", "refill": result, "medicine": medicine}), 200


@app.route("/schedule")
@login_required
def schedule_page():
    user = current_user()
    schedules = schedule_service.list_schedules(user["id"])
    meds = medicine_service.list_medicines(user["id"], active_filter=1)
    return render_template("schedule.html", user=user, schedules=schedules, medicines=meds)


# ---------- Schedule API ----------

VALID_DAY_CODES = {"SU", "MO", "TU", "WE", "TH", "FR", "SA"}


def _validate_schedule_payload(data, patient_id):
    errors = []
    medicine_id = data.get("medicine_id")
    schedule_time = (data.get("schedule_time") or "").strip()
    schedule_days = (data.get("schedule_days") or "daily").strip().lower()

    try:
        medicine_id = int(medicine_id)
        if not medicine_service.get_medicine(medicine_id, patient_id):
            errors.append("Selected medicine was not found for this patient.")
    except (TypeError, ValueError):
        medicine_id = None
        errors.append("A valid medicine must be selected.")

    if not schedule_time or len(schedule_time.split(":")) != 2:
        errors.append("Schedule time is required in HH:MM format.")
    else:
        try:
            h, m = map(int, schedule_time.split(":"))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                errors.append("Schedule time must be a valid 24-hour time.")
        except ValueError:
            errors.append("Schedule time must be numeric HH:MM.")

    if schedule_days != "daily":
        codes = [c.strip().upper() for c in schedule_days.split(",") if c.strip()]
        if not codes or any(c not in VALID_DAY_CODES for c in codes):
            errors.append("Repeat days must be 'daily' or a comma list like MO,WE,FR.")
        else:
            schedule_days = ",".join(codes)
    else:
        schedule_days = "daily"

    return errors, medicine_id, schedule_time, schedule_days


@app.route("/api/schedules", methods=["GET", "POST"])
@login_required
def api_schedules():
    user = current_user()

    if request.method == "GET":
        return jsonify({"schedules": schedule_service.list_schedules(user["id"])}), 200

    data = request.get_json(silent=True) or request.form
    errors, medicine_id, schedule_time, schedule_days = _validate_schedule_payload(data, user["id"])
    if errors:
        return jsonify({"errors": errors}), 400

    schedule_id = schedule_service.create_schedule(user["id"], medicine_id, schedule_time, schedule_days)
    schedules = schedule_service.list_schedules(user["id"])
    created = next((s for s in schedules if s["id"] == schedule_id), None)
    return jsonify({"message": "Schedule created.", "schedule": created}), 201


@app.route("/api/schedules/<int:schedule_id>", methods=["PUT", "DELETE"])
@login_required
def api_schedule_detail(schedule_id):
    user = current_user()
    existing = schedule_service.get_schedule(schedule_id, user["id"])
    if not existing:
        return jsonify({"error": "Schedule not found."}), 404

    if request.method == "DELETE":
        schedule_service.delete_schedule(schedule_id, user["id"])
        return jsonify({"message": "Schedule deleted."}), 200

    data = request.get_json(silent=True) or request.form
    errors, medicine_id, schedule_time, schedule_days = _validate_schedule_payload(data, user["id"])
    if errors:
        return jsonify({"errors": errors}), 400

    schedule_service.update_schedule(schedule_id, user["id"], schedule_time, schedule_days)
    schedules = schedule_service.list_schedules(user["id"])
    updated = next((s for s in schedules if s["id"] == schedule_id), None)
    return jsonify({"message": "Schedule updated.", "schedule": updated}), 200


@app.route("/api/schedules/<int:schedule_id>/toggle", methods=["POST"])
@login_required
def api_schedule_toggle(schedule_id):
    user = current_user()
    existing = schedule_service.get_schedule(schedule_id, user["id"])
    if not existing:
        return jsonify({"error": "Schedule not found."}), 404

    schedule_service.set_enabled(schedule_id, user["id"], not existing["enabled"])
    schedules = schedule_service.list_schedules(user["id"])
    updated = next((s for s in schedules if s["id"] == schedule_id), None)
    return jsonify({"message": "Schedule updated.", "schedule": updated}), 200


@app.route("/api/reminders/pending")
@login_required
def api_pending_reminders():
    user = current_user()
    reminders = reminder_service.get_pending_reminders(user["id"])
    return jsonify({"reminders": reminders}), 200


@app.route("/api/medicine/dispense", methods=["POST"])
@login_required
def api_dispense():
    user = current_user()
    data = request.get_json(silent=True) or request.form
    reminder_id = data.get("reminder_id")
    if not reminder_id:
        return jsonify({"error": "reminder_id is required."}), 400

    result, status_code = reminder_service.dispense_medicine(int(reminder_id), user["id"])
    return jsonify(result), status_code


@app.route("/api/medicine/collect", methods=["POST"])
@login_required
def api_collect():
    user = current_user()
    data = request.get_json(silent=True) or request.form
    reminder_id = data.get("reminder_id")
    if not reminder_id:
        return jsonify({"error": "reminder_id is required."}), 400

    result, status_code = reminder_service.mark_collected(int(reminder_id), user["id"])
    return jsonify(result), status_code


@app.route("/notifications")
@login_required
def notifications_page():
    user = current_user()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM notifications WHERE patient_id = ? ORDER BY created_at DESC LIMIT 200",
        (user["id"],),
    ).fetchall()
    conn.close()
    return render_template("notifications.html", user=user, notifications=[dict(r) for r in rows])


@app.route("/api/notification/test", methods=["POST"])
@login_required
def api_notification_test():
    user = current_user()
    data = request.get_json(silent=True) or request.form
    channel = data.get("channel", "sms")
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Message is required."}), 400

    recipient = user["phone"] if channel != "email" else user["email"]
    status = notification_service.send_notification(user["id"], recipient, message, "test", channel)
    return jsonify({"message": "Notification processed.", "status": status}), 200


@app.route("/face-recognition")
@login_required
def face_recognition_page():
    user = current_user()
    status = face_service.get_registration_status(user["id"])
    return render_template("face_recognition.html", user=user, status=status,
                            dependencies_available=face_service.FACE_DEPENDENCIES_AVAILABLE)


@app.route("/api/face/register", methods=["POST"])
@login_required
def api_face_register():
    user = current_user()
    data = request.get_json(silent=True) or {}
    image_b64 = data.get("image")
    angle = data.get("angle")
    consent = data.get("consent", False)

    if not consent and not user["face_consent"]:
        return jsonify({"error": "Consent is required before registering face data."}), 400
    if not image_b64:
        return jsonify({"error": "image is required."}), 400

    result, status_code = face_service.register_face_sample(user["id"], image_b64, angle)
    return jsonify(result), status_code


@app.route("/api/face/recognize", methods=["POST"])
@login_required
def api_face_recognize():
    user = current_user()
    data = request.get_json(silent=True) or {}
    image_b64 = data.get("image")
    if not image_b64:
        return jsonify({"error": "image is required."}), 400

    result, status_code = face_service.recognize(image_b64, user["id"])
    return jsonify(result), status_code


@app.route("/api/face/delete", methods=["POST"])
@login_required
def api_face_delete():
    user = current_user()
    result = face_service.delete_face_data(user["id"])
    return jsonify(result), 200


@app.route("/api/face/status")
@login_required
def api_face_status():
    user = current_user()
    return jsonify(face_service.get_registration_status(user["id"])), 200


@app.route("/hardware")
@login_required
def hardware_page():
    user = current_user()
    config = hardware_service.get_config(user["id"])
    battery = battery_service.get_battery(user["id"])
    return render_template("hardware.html", user=user, config=config, battery=battery)


@app.route("/api/hardware/status")
@login_required
def api_hardware_status():
    user = current_user()
    config = hardware_service.get_config(user["id"])
    return jsonify({"config": config}), 200


@app.route("/api/hardware/test", methods=["POST"])
@login_required
def api_hardware_test():
    user = current_user()
    result = hardware_service.test_connection(user["id"])
    return jsonify(result), 200


@app.route("/api/hardware/config", methods=["POST"])
@login_required
def api_hardware_config():
    user = current_user()
    data = request.get_json(silent=True) or request.form
    esp32_ip = (data.get("esp32_ip") or "").strip()
    try:
        port = int(data.get("port"))
    except (TypeError, ValueError):
        return jsonify({"errors": ["Port must be a number."]}), 400

    if not esp32_ip:
        return jsonify({"errors": ["ESP32 IP address is required."]}), 400
    if not (1 <= port <= 65535):
        return jsonify({"errors": ["Port must be between 1 and 65535."]}), 400

    config = hardware_service.update_config(user["id"], esp32_ip, port)
    return jsonify({"message": "Hardware configuration updated.", "config": config}), 200


@app.route("/api/hardware/command", methods=["POST"])
@login_required
def api_hardware_command():
    user = current_user()
    data = request.get_json(silent=True) or request.form
    command = (data.get("command") or "").strip().upper()
    result, status_code = hardware_service.send_command(user["id"], command)
    return jsonify(result), status_code


@app.route("/api/movement", methods=["POST"])
@login_required
def api_movement():
    user = current_user()
    data = request.get_json(silent=True) or request.form
    direction = (data.get("direction") or "").strip().upper()
    direction_map = {
        "FORWARD": "MOVE_FORWARD", "BACKWARD": "MOVE_BACKWARD",
        "LEFT": "TURN_LEFT", "RIGHT": "TURN_RIGHT", "STOP": "STOP_MOTOR",
    }
    if direction not in direction_map:
        return jsonify({"error": "direction must be one of forward, backward, left, right, stop."}), 400

    if user["operating_mode"] == "fixed" and direction != "STOP":
        return jsonify({"error": "Movement is disabled in Fixed Position Mode."}), 409

    result, status_code = hardware_service.send_command(user["id"], direction_map[direction])
    return jsonify(result), status_code


@app.route("/api/search/start", methods=["POST"])
@login_required
def api_search_start():
    user = current_user()
    if user["operating_mode"] == "fixed":
        return jsonify({"error": "Patient search is disabled in Fixed Position Mode."}), 409
    result, status_code = hardware_service.send_command(user["id"], "START_SEARCH_MODE")
    return jsonify(result), status_code


@app.route("/api/search/stop", methods=["POST"])
@login_required
def api_search_stop():
    user = current_user()
    result, status_code = hardware_service.send_command(user["id"], "STOP_SEARCH_MODE")
    return jsonify(result), status_code


@app.route("/api/mode", methods=["POST"])
@login_required
def api_set_mode():
    user = current_user()
    data = request.get_json(silent=True) or request.form
    mode = (data.get("mode") or "").strip().lower()
    confirm = bool(data.get("confirm"))

    if mode not in ("fixed", "move"):
        return jsonify({"error": "mode must be 'fixed' or 'move'."}), 400
    if not confirm:
        return jsonify({"error": "Confirmation required to switch modes.", "needs_confirmation": True}), 400

    if mode == "move" and not battery_service.can_enter_move_mode(user["id"]):
        battery = battery_service.get_battery(user["id"])
        return jsonify({
            "error": f"Cannot switch to Move Mode: battery is CRITICAL ({battery['percentage']}%). Charge MEDBOT first.",
        }), 409

    conn = get_connection()
    conn.execute("UPDATE users SET operating_mode = ? WHERE id = ?", (mode, user["id"]))
    conn.commit()
    conn.close()

    if mode == "fixed":
        hardware_service.send_command(user["id"], "STOP_SEARCH_MODE")
        hardware_service.send_command(user["id"], "STOP_MOTOR")

    return jsonify({"message": f"Switched to {'Fixed Position' if mode == 'fixed' else 'Move'} Mode.", "mode": mode}), 200


@app.route("/api/battery")
@login_required
def api_battery():
    user = current_user()
    battery = battery_service.get_battery(user["id"])
    return jsonify({"battery": battery}), 200


@app.route("/api/battery/update", methods=["POST"])
@login_required
def api_battery_update():
    user = current_user()
    data = request.get_json(silent=True) or request.form
    charging = bool(data.get("charging", False))

    if data.get("adc_voltage") is not None:
        try:
            adc_voltage = float(data.get("adc_voltage"))
        except (TypeError, ValueError):
            return jsonify({"error": "adc_voltage must be a number."}), 400
        result, status_code = battery_service.update_from_adc_reading(user["id"], adc_voltage, charging)
    elif data.get("voltage") is not None:
        try:
            voltage = float(data.get("voltage"))
        except (TypeError, ValueError):
            return jsonify({"error": "voltage must be a number."}), 400
        result, status_code = battery_service.update_direct(user["id"], voltage, charging)
    else:
        return jsonify({"error": "Provide either 'voltage' or 'adc_voltage'."}), 400

    return jsonify(result), status_code


@app.route("/history")
@login_required
def history_page():
    user = current_user()
    range_filter = request.args.get("range", "all")
    medicine_id = request.args.get("medicine_id", type=int)
    search = request.args.get("search", "").strip() or None

    records = history_service.list_history(user["id"], range_filter, medicine_id, search)
    medicines = medicine_service.list_medicines(user["id"])
    return render_template(
        "history.html", user=user, records=records, medicines=medicines,
        range_filter=range_filter, medicine_id=medicine_id, search=search or "",
    )


@app.route("/api/history")
@login_required
def api_history():
    user = current_user()
    range_filter = request.args.get("range", "all")
    medicine_id = request.args.get("medicine_id", type=int)
    search = request.args.get("search", "").strip() or None
    records = history_service.list_history(user["id"], range_filter, medicine_id, search)
    return jsonify({"history": records}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=config.DEBUG, host="0.0.0.0", port=port)
