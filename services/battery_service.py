from database.db import get_connection
from services import notification_service, hardware_service
from services.time_service import database_timestamp


def get_battery(patient_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM battery WHERE patient_id = ?", (patient_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def compute_percentage(voltage, full_voltage, critical_voltage):
    """Linear interpolation between critical_voltage (0%) and full_voltage (100%)."""
    if full_voltage <= critical_voltage:
        return 100.0
    pct = (voltage - critical_voltage) / (full_voltage - critical_voltage) * 100
    return max(0.0, min(100.0, round(pct, 1)))


def compute_status(percentage):
    if percentage >= 80:
        return "EXCELLENT"
    if percentage >= 50:
        return "GOOD"
    if percentage >= 30:
        return "MODERATE"
    if percentage >= 20:
        return "LOW"
    return "CRITICAL"


def _actual_voltage_from_adc(adc_voltage, divider_ratio, calibration_factor):
    """Actual Battery Voltage = ADC Measured Voltage x Voltage Divider Ratio x Calibration Factor.
    Never feed full pack voltage directly into an ESP32 ADC pin — this formula assumes it has
    already been safely stepped down through a voltage divider before reaching the ADC."""
    return adc_voltage * divider_ratio * calibration_factor


def update_from_adc_reading(patient_id, adc_voltage, charging=False):
    battery = get_battery(patient_id)
    if not battery:
        return {"error": "No battery configuration found for this patient."}, 404

    actual_voltage = _actual_voltage_from_adc(
        adc_voltage, battery["voltage_divider_ratio"], battery["calibration_factor"]
    )
    return _apply_reading(patient_id, actual_voltage, charging)


def update_direct(patient_id, voltage, charging=False):
    """For simulation/testing: set voltage directly (bypassing the ADC formula)."""
    return _apply_reading(patient_id, voltage, charging)


def _apply_reading(patient_id, voltage, charging):
    battery = get_battery(patient_id)
    percentage = compute_percentage(voltage, battery["full_voltage"], battery["critical_voltage"])
    status = compute_status(percentage)
    now = database_timestamp()

    conn = get_connection()
    conn.execute(
        """UPDATE battery SET voltage = ?, percentage = ?, status = ?, charging = ?, updated_at = ?
           WHERE patient_id = ?""",
        (round(voltage, 2), percentage, status, 1 if charging else 0, now, patient_id),
    )
    conn.commit()
    conn.close()

    safety_result = _run_safety_checks(patient_id, percentage, voltage, status)
    return {
        "voltage": round(voltage, 2), "percentage": percentage, "status": status,
        "charging": bool(charging), "safety": safety_result,
    }, 200


def _run_safety_checks(patient_id, percentage, voltage, status):
    """Battery safety overrides movement: below 20% forces Fixed Mode and stops motors."""
    conn = get_connection()
    patient = conn.execute("SELECT * FROM users WHERE id = ?", (patient_id,)).fetchone()
    battery = conn.execute("SELECT * FROM battery WHERE patient_id = ?", (patient_id,)).fetchone()
    patient = dict(patient)
    battery = dict(battery)
    conn.close()  # close before any notification call, which opens its own connection

    actions = []

    if percentage < 20:
        if patient["operating_mode"] == "move":
            conn = get_connection()
            conn.execute("UPDATE users SET operating_mode = 'fixed' WHERE id = ?", (patient_id,))
            conn.commit()
            conn.close()
            actions.append("MOVE_MODE_DISABLED")

        if not battery["critical_battery_notified"]:
            notification_service.send_notification(
                patient_id, patient["caretaker_phone"],
                f"🚨 MEDBOT Critical Battery\n\nBattery level: {percentage}%\n\nMove Mode/motors should remain disabled according to the existing MEDBOT safety logic.",
                "critical_battery", "sms",
            )
            conn = get_connection()
            conn.execute("UPDATE battery SET critical_battery_notified = 1 WHERE patient_id = ?", (patient_id,))
            conn.commit()
            conn.close()
            actions.append("CARETAKER_NOTIFIED_CRITICAL")

        hardware_service.send_command(patient_id, "STOP_MOTOR")
        hardware_service.send_command(patient_id, "STOP_SEARCH_MODE")
        actions.extend(["STOP_MOTOR", "STOP_SEARCH_MODE"])
        return {"level": "CRITICAL", "actions": actions}

    if percentage < 30:
        if not battery["low_battery_notified"]:
            notification_service.send_notification(
                patient_id, patient["caretaker_phone"],
                f"🔋 MEDBOT Battery Warning\n\nBattery level: {percentage}%\n\nPlease charge the device soon.",
                "low_battery", "sms",
            )
            conn = get_connection()
            conn.execute("UPDATE battery SET low_battery_notified = 1 WHERE patient_id = ?", (patient_id,))
            conn.commit()
            conn.close()
            actions.append("CARETAKER_NOTIFIED_LOW")
        return {"level": "LOW", "actions": actions}

    # Healthy battery — reset notification flags so future dips alert again
    if battery["low_battery_notified"] or battery["critical_battery_notified"]:
        conn = get_connection()
        conn.execute(
            "UPDATE battery SET low_battery_notified = 0, critical_battery_notified = 0 WHERE patient_id = ?",
            (patient_id,),
        )
        conn.commit()
        conn.close()
        actions.append("ALERT_FLAGS_RESET")
    return {"level": "OK", "actions": actions}


def can_enter_move_mode(patient_id):
    battery = get_battery(patient_id)
    if not battery:
        return True  # no battery data yet — don't block
    return battery["percentage"] >= 20
