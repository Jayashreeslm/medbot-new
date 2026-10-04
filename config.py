import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ROOT_ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ROOT_ENV_FILE, override=True)
DATABASE_PATH = str(BASE_DIR / "database" / "medbot.db")

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# The root .env selects Telegram or safe simulation mode.
NOTIFY_MODE = os.environ.get("NOTIFY_MODE", "simulate").strip().lower()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
NOTIFY_DEBUG = os.environ.get("NOTIFY_DEBUG", "False").strip().lower() in {"1", "true", "yes"}

# Email (optional)
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# ESP32 defaults
DEFAULT_ESP32_IP = os.environ.get("DEFAULT_ESP32_IP", "192.168.1.50")
DEFAULT_ESP32_PORT = int(os.environ.get("DEFAULT_ESP32_PORT", "80"))

DEBUG = os.environ.get("FLASK_DEBUG", "True") == "True"


def validate_notification_config():
    if NOTIFY_MODE not in {"telegram", "simulate"}:
        print("[MEDBOT] Invalid NOTIFY_MODE; set it to 'telegram' or 'simulate'.")
        return
    if NOTIFY_MODE == "simulate":
        return

    missing = [
        name for name, value in (
            ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
            ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
        ) if not value
    ]
    if missing:
        print(
            "[MEDBOT] Telegram not configured; notifications will fail safely until configured. Missing: "
            + ", ".join(missing)
        )
