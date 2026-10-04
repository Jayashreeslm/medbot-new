import config
from services.telegram_service import send_telegram_message


def main():
    if config.NOTIFY_MODE == "simulate":
        print("Telegram test simulated successfully.")
        return 0

    result = send_telegram_message(
        "🤖 MEDBOT Test Notification\n\nTelegram notifications are working successfully."
    )
    if result.get("ok"):
        print("Telegram test notification sent successfully.")
        return 0

    print(result.get("error", "Telegram test notification failed."))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
