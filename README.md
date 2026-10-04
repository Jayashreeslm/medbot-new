# MEDBOT — Intelligent Pill Dispenser and Patient Assistance System

## Setup

1. Create a virtual environment (recommended):
   python -m venv venv
   venv\Scripts\activate   (Windows)  OR  source venv/bin/activate (Mac/Linux)

2. Install dependencies:
   pip install -r requirements.txt

3. Copy `.env.example` to `.env`. Keep `NOTIFY_MODE=simulate` while testing without sending messages. For actual Telegram delivery set `NOTIFY_MODE=telegram` and configure the required bot values below.

4. Set `SECRET_KEY` to a long random value before deploying.

5. Run the app: `python app.py`

6. Open http://localhost:5000 in your browser.

## Inventory and notifications

MEDBOT uses Flask and SQLite. Existing databases are migrated automatically at startup. Medicine records include batch number, quantity, minimum stock threshold, expiry date, price, and refill due date. The dashboard summarizes total, low, empty, expiring, and dispensed-today counts. Dispensing remains tied to a scheduled device dose and decrements one unit per event.

Telegram mode requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. If either is missing, MEDBOT stays in safe simulation mode and never crashes. The Notifications page shows the current Telegram state and a test button for verifying the bot connection.

Telegram delivery uses the Telegram Bot API and logs only the success/failure result without exposing the bot token. Email remains available via the existing SMTP settings, and the notification system keeps its retry and fallback flow. Configure a patient's notification preference in Profile. The Notifications page supports filtering, pagination, and manual resend.

### Telegram setup checklist

- Create a Telegram bot with BotFather and copy the bot token.
- Start a chat with the bot or add it to a group, then copy the chat ID.
- Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the project root `.env` file.
- Keep credentials private. Do not commit `.env`; use `.env.example` as the template.

Use the app's Telegram test button in the Notifications page to send a live test message after the bot is configured.

An inventory scan runs daily at 8:00 AM Asia/Kolkata and after inventory changes. It alerts for expiring/expired stock and due refills. All displayed and outbound event timestamps use 12-hour Asia/Kolkata time.
