from datetime import datetime
import config
from database.db import get_connection


def _twilio_configured():
    return bool(config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN)


def _log_notification(patient_id, medicine_id, recipient_number, message, notification_type, channel, status):
    conn = get_connection()
    conn.execute(
        """INSERT INTO notifications
           (patient_id, medicine_id, recipient_number, message, notification_type, channel, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (patient_id, medicine_id, recipient_number, message, notification_type, channel, status,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def send_notification(patient_id, recipient_number, message, notification_type, channel, medicine_id=None):
    """Sends via Twilio (SMS/WhatsApp) if configured, else logs a SIMULATED NOTIFICATION.
    Returns the status string that was recorded."""
    status = "Simulated"

    if channel in ("sms", "whatsapp") and _twilio_configured():
        try:
            from twilio.rest import Client
            client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
            from_number = config.TWILIO_WHATSAPP_FROM if channel == "whatsapp" else config.TWILIO_SMS_FROM
            to_number = f"whatsapp:{recipient_number}" if channel == "whatsapp" else recipient_number
            from_formatted = f"whatsapp:{from_number}" if channel == "whatsapp" else from_number
            client.messages.create(body=message, from_=from_formatted, to=to_number)
            status = "Sent"
        except Exception as e:
            status = "Failed"
            print(f"[MEDBOT notification] Twilio send failed: {e}")
    elif channel == "email" and config.SMTP_HOST and config.SMTP_USER:
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(message)
            msg["Subject"] = "MEDBOT Notification"
            msg["From"] = config.SMTP_USER
            msg["To"] = recipient_number
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
                server.starttls()
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.send_message(msg)
            status = "Sent"
        except Exception as e:
            status = "Failed"
            print(f"[MEDBOT notification] Email send failed: {e}")
    else:
        status = "Simulated"
        print(f"[MEDBOT] SIMULATED NOTIFICATION SENT -> {recipient_number} ({channel}): {message}")

    _log_notification(patient_id, medicine_id, recipient_number, message, notification_type, channel, status)
    return status


# ---------- Message templates (exact wording per spec) ----------

def msg_reminder(patient_name, medicine_name, dosage, compartment, scheduled_time):
    return (f"MEDBOT Reminder: Hello {patient_name}, it is time for {medicine_name}. "
            f"Dosage: {dosage}. Compartment: {compartment}. Scheduled Time: {scheduled_time}.")


def msg_dispensed(medicine_name, patient_name, dosage, compartment):
    return (f"MEDBOT: {medicine_name} for {patient_name} has been dispensed successfully. "
            f"Dosage: {dosage}. Compartment: {compartment}.")


def msg_not_collected(patient_name, medicine_name):
    return f"MEDBOT Alert: {patient_name} has not collected the scheduled medicine {medicine_name}. Please check the patient."


def msg_low_stock(medicine_name, compartment, quantity):
    return (f"MEDBOT Stock Alert: Medicine {medicine_name} in compartment {compartment} is running low. "
            f"Remaining quantity: {quantity}. Please refill the compartment.")


def msg_empty(medicine_name, compartment):
    return f"MEDBOT Alert: Medicine {medicine_name} in compartment {compartment} is empty. Please refill the compartment."


def msg_insufficient_stock(medicine_name, compartment, available, required):
    return (f"MEDBOT Alert: Medicine {medicine_name} in compartment {compartment} has insufficient stock. "
            f"Available: {available}, Required: {required}.")
