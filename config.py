import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "database", "medbot.db")

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# Twilio (optional — falls back to simulation mode if unset)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_SMS_FROM = os.environ.get("TWILIO_SMS_FROM", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")

# Email (optional)
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# ESP32 defaults
DEFAULT_ESP32_IP = os.environ.get("DEFAULT_ESP32_IP", "192.168.1.50")
DEFAULT_ESP32_PORT = int(os.environ.get("DEFAULT_ESP32_PORT", "80"))

DEBUG = os.environ.get("FLASK_DEBUG", "True") == "True"
