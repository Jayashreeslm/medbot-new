from datetime import timedelta
import logging
import re

import config
from database.db import get_connection
from services import telegram_service
from services.time_service import database_timestamp, formatDateTime, now_kolkata

logger = logging.getLogger("medbot.notifications")


def _telegram_configured():
    return telegram_service.is_configured()


def get_telegram_service_status():
    return telegram_service.get_status()


def _effective_channel(channel):
    if channel in {"sms", "whatsapp", "telegram"}:
        return "telegram"
    return channel


def normalizePhone(number):
    """Normalize Indian mobile numbers to E.164 while preserving other E.164 numbers."""
    cleaned = re.sub(r"[\s()-]", "", str(number or ""))
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("0091") and len(cleaned) == 14:
        return "+" + cleaned[2:]
    if cleaned.startswith("91") and len(cleaned) == 12 and cleaned.isdigit():
        return "+" + cleaned
    if cleaned.startswith("0") and len(cleaned) == 11 and cleaned[1:].isdigit():
        cleaned = cleaned[1:]
    if len(cleaned) == 10 and cleaned.isdigit():
        return "+91" + cleaned
    return cleaned


def _format_phone(number):
    return normalizePhone(number)


def _deliver(recipient, message, channel):
    channel = _effective_channel(channel)

    if channel == "telegram":
        if config.NOTIFY_MODE == "simulate":
            logger.info("SIMULATED telegram notification; message_length=%d", len(message))
            return "Simulated", None, None, None
        if not _telegram_configured():
            logger.warning("Telegram is not configured; notification was not sent.")
            return "Not Configured", "Telegram is not configured. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to the .env file.", None, None
        result = telegram_service.send_telegram_message(message)
        if result.get("ok"):
            return "Sent", None, None, None
        api_error = result.get("error") or "Telegram API request failed."
        return "Failed", f"Telegram API error: {api_error}", None, None

    if config.NOTIFY_MODE == "simulate":
        logger.info("SIMULATED notification channel=%s; message_length=%d", channel, len(message))
        return "Simulated", None, None, None

    if channel == "email":
        if not all((config.SMTP_HOST, config.SMTP_USER, config.SMTP_PASSWORD)):
            return "Failed", "SMTP delivery is not configured; set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD.", None, None
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(message)
            msg["Subject"] = "MEDBOT Notification"
            msg["From"] = config.SMTP_USER
            msg["To"] = recipient
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
                server.starttls()
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.send_message(msg)
            return "Sent", None, None, None
        except Exception as exc:
            error_code = getattr(exc, "smtp_code", None)
            if config.NOTIFY_DEBUG:
                logger.exception("SMTP notification failed; code=%s error=%s", error_code, exc)
            return "Failed", str(exc), str(error_code) if error_code is not None else None, None

    return "Failed", f"Unsupported notification channel: {channel}", None, None


def _create_attempt(patient_id, recipient, message, notification_type, channel, medicine_id):
    now = now_kolkata()
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO notifications
           (patient_id, medicine_id, recipient_number, message, notification_type, channel,
            status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (patient_id, medicine_id, recipient, message, notification_type, channel,
         now.strftime("%Y-%m-%d %H:%M:%S")),
    )
    notification_id = cursor.lastrowid
    conn.commit()
    conn.close()

    delivery_status, error, error_code, provider_message_id = _deliver(recipient, message, channel)
    next_retry = (now + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S") if delivery_status == "Failed" else None
    sent_at = database_timestamp() if delivery_status == "Sent" else None
    conn = get_connection()
    conn.execute(
        """UPDATE notifications SET status = ?, error = ?, error_code = ?, next_retry_at = ?,
              sent_at = ?, provider_message_id = ?
           WHERE id = ?""",
          (delivery_status, error, error_code, next_retry, sent_at, provider_message_id, notification_id),
    )
    conn.commit()
    conn.close()
    return notification_id, delivery_status, delivery_status == "Failed"


def _fallback_target(patient_id, failed_channel):
    conn = get_connection()
    patient = conn.execute("SELECT phone, email FROM users WHERE id = ?", (patient_id,)).fetchone()
    conn.close()
    if not patient:
        return None, None
    if failed_channel in ("sms", "whatsapp") and patient["email"]:
        return patient["email"], "email"
    if failed_channel == "email" and patient["phone"]:
        return patient["phone"], "sms"
    return None, None


def _dispatch(patient_id, recipient, message, notification_type, channel, medicine_id=None,
              allow_fallback=True):
    notification_id, status, failed = _create_attempt(
        patient_id, recipient, message, notification_type, channel, medicine_id
    )
    if failed and allow_fallback:
        fallback_recipient, fallback_channel = _fallback_target(patient_id, channel)
        if fallback_recipient:
            _dispatch(patient_id, fallback_recipient, message, notification_type,
                      fallback_channel, medicine_id, allow_fallback=False)
    return notification_id, status


def send_notification(patient_id, recipient_number, message, notification_type, channel, medicine_id=None):
    """Send and log without allowing provider failures to interrupt application work."""
    try:
        requested_channel = _effective_channel(channel)
        if requested_channel == "telegram":
            recipient_number = "Telegram"
        targets = [(recipient_number, requested_channel)]
        if notification_type != "test" and channel == "sms" and config.NOTIFY_MODE not in {"telegram", "simulate"}:
            conn = get_connection()
            patient = conn.execute(
                "SELECT email, notification_preference FROM users WHERE id = ?", (patient_id,)
            ).fetchone()
            conn.close()
            preference = patient["notification_preference"] if patient else "sms"
            if preference == "email" and patient and patient["email"]:
                targets = [(patient["email"], "email")]
            elif preference == "both" and patient and patient["email"]:
                targets.append((patient["email"], "email"))

        first_status = "failed"
        allow_fallback = len(targets) == 1
        for index, (recipient, target_channel) in enumerate(targets):
            _, status = _dispatch(patient_id, recipient, message, notification_type,
                                  target_channel, medicine_id, allow_fallback=allow_fallback)
            if index == 0:
                first_status = status
        return first_status
    except Exception as exc:
        print(f"[MEDBOT notification] Could not process notification: {exc}")
        return "failed"


def _retry_row(notification):
    delivery_status, error, error_code, provider_message_id = _deliver(
        notification["recipient_number"], notification["message"], notification["channel"]
    )
    retry_count = notification["retry_count"] + 1
    sent_at = database_timestamp() if delivery_status == "Sent" else None
    if delivery_status == "Sent":
        status, next_retry = "Sent", None
    elif delivery_status == "Simulated":
        status, next_retry = "Simulated", None
    elif retry_count >= 3:
        status, next_retry = "Failed", None
    else:
        delay_minutes = {1: 5, 2: 15}[retry_count]
        status = "Failed"
        next_retry = (now_kolkata() + timedelta(minutes=delay_minutes)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    conn.execute(
          """UPDATE notifications SET status = ?, error = ?, error_code = ?, retry_count = ?,
              next_retry_at = ?, sent_at = ?, provider_message_id = ? WHERE id = ?""",
          (status, error, error_code, retry_count, next_retry, sent_at, provider_message_id, notification["id"]),
    )
    conn.commit()
    conn.close()
    return status


def process_due_retries():
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM notifications WHERE lower(status) IN ('pending', 'failed')
           AND next_retry_at IS NOT NULL AND next_retry_at <= ?""", (database_timestamp(),)
    ).fetchall()
    conn.close()
    for row in rows:
        try:
            _retry_row(dict(row))
        except Exception as exc:
            print(f"[MEDBOT notification] Retry failed for notification {row['id']}: {exc}")
    return len(rows)


def resend_notification(notification_id, patient_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM notifications WHERE id = ? AND patient_id = ?",
        (notification_id, patient_id),
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        return _dispatch(patient_id, row["recipient_number"], row["message"],
                         row["notification_type"], row["channel"], row["medicine_id"],
                         allow_fallback=True)[1]
    except Exception as exc:
        print(f"[MEDBOT notification] Manual resend failed: {exc}")
        return "Failed"


def msg_reminder(patient_name, medicine_name, dosage, compartment, scheduled_time):
    return (
        f"💊 MEDBOT Medicine Reminder\n\n"
        f"Medicine: {medicine_name}\n"
        f"Dosage: {dosage}\n"
        f"Quantity: 1\n"
        f"Compartment: {compartment}\n\n"
        f"Please take your medicine now."
    )


def msg_dispensed(medicine_name, patient_name, dosage, compartment, quantity=1, dispensed_at=None):
    time_text = formatDateTime(dispensed_at) if dispensed_at else "today"
    return (
        f"✅ MEDBOT Dispense Confirmed\n\n"
        f"Medicine: {medicine_name}\n"
        f"Patient: {patient_name}\n"
        f"Quantity: {quantity}\n"
        f"Dosage: {dosage}\n"
        f"Compartment: {compartment}\n"
        f"Time: {time_text}"
    )


def msg_not_collected(patient_name, medicine_name):
    return f"⚠️ MEDBOT Missed Reminder\n\n{patient_name} has not collected {medicine_name}. Please check the patient."


def msg_low_stock(medicine_name, compartment, quantity, threshold=None):
    threshold_text = f"\nRefill Threshold: {threshold}" if threshold is not None else ""
    return (
        f"⚠️ MEDBOT Refill Alert\n\n"
        f"Medicine: {medicine_name}\n"
        f"Current Quantity: {quantity}\n"
        f"Compartment: {compartment}{threshold_text}\n\n"
        f"Please refill this medicine."
    )


def msg_empty(medicine_name, compartment, threshold=None):
    threshold_text = f"\nRefill Threshold: {threshold}" if threshold is not None else ""
    return (
        f"⚠️ MEDBOT Refill Alert\n\n"
        f"Medicine: {medicine_name}\n"
        f"Current Quantity: 0\n"
        f"Compartment: {compartment}{threshold_text}\n\n"
        f"Please refill this medicine."
    )


def msg_insufficient_stock(medicine_name, compartment, available, required):
    return (
        f"⚠️ MEDBOT Stock Alert\n\n"
        f"Medicine: {medicine_name}\n"
        f"Compartment: {compartment}\n"
        f"Available: {available}\n"
        f"Required: {required}\n\n"
        f"Please refill this medicine."
    )