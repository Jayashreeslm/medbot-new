import logging

import requests

import config

logger = logging.getLogger("medbot.telegram")


def is_configured():
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def get_status():
    if config.NOTIFY_MODE == "simulate":
        return {
            "status": "Simulation Mode",
            "message": "Telegram notifications are simulated because NOTIFY_MODE=simulate.",
        }
    if not is_configured():
        return {
            "status": "Not Configured",
            "message": "Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to the .env file.",
        }
    return {
        "status": "Connected",
        "message": "Telegram Notification\nStatus: Connected",
    }


def send_telegram_message(message):
    """Send a Telegram message without exposing the bot token or chat ID in app output."""
    if config.NOTIFY_MODE == "simulate":
        logger.info("Telegram notification simulated. Message preview: %s", message[:160])
        return {"ok": True, "simulated": True, "message_id": None}

    if not is_configured():
        return {
            "ok": False,
            "error": "Telegram is not configured. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to the .env file.",
            "simulated": False,
        }

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.ok and payload.get("ok"):
            return {
                "ok": True,
                "simulated": False,
                "message_id": payload.get("result", {}).get("message_id"),
            }
        logger.warning("Telegram API returned an unsuccessful response (HTTP %s).", response.status_code)
        return {"ok": False, "error": "Telegram API returned an error.", "simulated": False}
    except requests.exceptions.Timeout:
        logger.warning("Telegram send timed out.")
        return {"ok": False, "error": "Telegram request timed out.", "simulated": False}
    except requests.RequestException as exc:
        logger.warning("Telegram send failed due to a network error (%s).", type(exc).__name__)
        return {"ok": False, "error": "Telegram request failed.", "simulated": False}
