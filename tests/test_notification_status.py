import os
import uuid
from unittest.mock import patch

import config
import app as app_module
import pytest
from database.db import get_connection, init_db
from models import create_user
from services import notification_service, reminder_service
from services import telegram_service


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "medbot-test.db"))
    init_db()


def _restore_env(original):
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_missing_telegram_credentials_return_not_configured():
    original = {
        "TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": config.TELEGRAM_CHAT_ID,
        "NOTIFY_MODE": config.NOTIFY_MODE,
    }
    try:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)
        config.TELEGRAM_BOT_TOKEN = ""
        config.TELEGRAM_CHAT_ID = ""
        config.NOTIFY_MODE = "telegram"

        status, error, _, _ = notification_service._deliver("chat123", "MEDBOT telegram test", "telegram")
        assert status == "Not Configured"
        assert "telegram" in (error or "").lower()
    finally:
        _restore_env(original)
        config.TELEGRAM_BOT_TOKEN = original["TELEGRAM_BOT_TOKEN"]
        config.TELEGRAM_CHAT_ID = original["TELEGRAM_CHAT_ID"]
        config.NOTIFY_MODE = original["NOTIFY_MODE"]


def test_telegram_api_errors_are_handled_cleanly():
    original = {
        "TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": config.TELEGRAM_CHAT_ID,
        "NOTIFY_MODE": config.NOTIFY_MODE,
    }
    try:
        config.TELEGRAM_BOT_TOKEN = "token-abc"
        config.TELEGRAM_CHAT_ID = "chat-123"
        config.NOTIFY_MODE = "telegram"

        with patch("services.telegram_service.send_telegram_message", return_value={"ok": False, "error": "bad request"}):
            status, error, _, _ = notification_service._deliver("chat-123", "MEDBOT test", "telegram")

        assert status == "Failed"
        assert "telegram" in (error or "").lower()
    finally:
        _restore_env(original)
        config.TELEGRAM_BOT_TOKEN = original["TELEGRAM_BOT_TOKEN"]
        config.TELEGRAM_CHAT_ID = original["TELEGRAM_CHAT_ID"]
        config.NOTIFY_MODE = original["NOTIFY_MODE"]


def test_telegram_configuration_status_does_not_expose_secrets():
    original = {
        "TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": config.TELEGRAM_CHAT_ID,
        "NOTIFY_MODE": config.NOTIFY_MODE,
    }
    try:
        config.TELEGRAM_BOT_TOKEN = "secret-token-value"
        config.TELEGRAM_CHAT_ID = "private-chat-id"
        config.NOTIFY_MODE = "telegram"
        status = telegram_service.get_status()

        assert status["status"] == "Connected"
        assert "secret-token-value" not in str(status)
        assert "private-chat-id" not in str(status)
    finally:
        _restore_env(original)
        config.TELEGRAM_BOT_TOKEN = original["TELEGRAM_BOT_TOKEN"]
        config.TELEGRAM_CHAT_ID = original["TELEGRAM_CHAT_ID"]
        config.NOTIFY_MODE = original["NOTIFY_MODE"]


def test_telegram_status_distinguishes_simulation_and_missing_credentials():
    original = {
        "TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": config.TELEGRAM_CHAT_ID,
        "NOTIFY_MODE": config.NOTIFY_MODE,
    }
    try:
        config.TELEGRAM_BOT_TOKEN = ""
        config.TELEGRAM_CHAT_ID = ""
        config.NOTIFY_MODE = "simulate"
        assert telegram_service.get_status()["status"] == "Simulation Mode"

        config.NOTIFY_MODE = "telegram"
        status = telegram_service.get_status()
        assert status["status"] == "Not Configured"
        assert "TELEGRAM_BOT_TOKEN" in status["message"]
        assert "TELEGRAM_CHAT_ID" in status["message"]
    finally:
        _restore_env(original)
        config.TELEGRAM_BOT_TOKEN = original["TELEGRAM_BOT_TOKEN"]
        config.TELEGRAM_CHAT_ID = original["TELEGRAM_CHAT_ID"]
        config.NOTIFY_MODE = original["NOTIFY_MODE"]


def test_simulation_mode_never_calls_telegram():
    original = config.NOTIFY_MODE
    try:
        config.NOTIFY_MODE = "simulate"
        with patch("services.telegram_service.requests.post") as post_mock:
            status, error, _, _ = notification_service._deliver("unused", "MEDBOT simulated", "sms")

        assert status == "Simulated"
        assert error is None
        post_mock.assert_not_called()
    finally:
        config.NOTIFY_MODE = original


def test_telegram_timeout_returns_safe_failure():
    original = {
        "TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": config.TELEGRAM_CHAT_ID,
        "NOTIFY_MODE": config.NOTIFY_MODE,
    }
    try:
        config.TELEGRAM_BOT_TOKEN = "token-abc"
        config.TELEGRAM_CHAT_ID = "chat-123"
        config.NOTIFY_MODE = "telegram"
        with patch("services.telegram_service.requests.post", side_effect=telegram_service.requests.exceptions.Timeout):
            result = telegram_service.send_telegram_message("MEDBOT timeout test")

        assert result["ok"] is False
        assert "timed out" in result["error"].lower()
        assert "token-abc" not in str(result)
    finally:
        _restore_env(original)
        config.TELEGRAM_BOT_TOKEN = original["TELEGRAM_BOT_TOKEN"]
        config.TELEGRAM_CHAT_ID = original["TELEGRAM_CHAT_ID"]
        config.NOTIFY_MODE = original["NOTIFY_MODE"]


def test_reminder_notification_uses_dynamic_database_data(isolated_database):
    original = {
        "TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": config.TELEGRAM_CHAT_ID,
        "NOTIFY_MODE": config.NOTIFY_MODE,
    }
    email = f"alice-{uuid.uuid4().hex[:8]}@example.com"
    try:
        config.TELEGRAM_BOT_TOKEN = "token-abc"
        config.TELEGRAM_CHAT_ID = "chat-123"
        config.NOTIFY_MODE = "telegram"
        user_id = create_user("Alice", email, "9876543210", "Caregiver", "9876543211", "strongpass")
        conn = get_connection()
        medicine_id = conn.execute(
            """INSERT INTO medicines
               (patient_id, medicine_name, dosage, quantity, compartment_number, refill_threshold, active, price, description)
               VALUES (?, ?, ?, ?, ?, ?, 1, 0, 'Test medicine')""",
            (user_id, "Paracetamol", "500 mg", 3, 2, 2),
        ).lastrowid
        conn.commit()
        conn.close()

        with patch("services.telegram_service.send_telegram_message", return_value={"ok": True, "message_id": 42}) as send_mock:
            reminder_service.create_reminder(user_id, medicine_id, "08:15", "fixed")

        message = send_mock.call_args[0][0]
        assert "Paracetamol" in message
        assert "500 mg" in message
        assert "Compartment: 2" in message or "compartment 2" in message.lower()
    finally:
        _restore_env(original)
        config.TELEGRAM_BOT_TOKEN = original["TELEGRAM_BOT_TOKEN"]
        config.TELEGRAM_CHAT_ID = original["TELEGRAM_CHAT_ID"]
        config.NOTIFY_MODE = original["NOTIFY_MODE"]


def test_test_telegram_endpoint_returns_success(isolated_database):
    original = {
        "TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": config.TELEGRAM_CHAT_ID,
        "NOTIFY_MODE": config.NOTIFY_MODE,
    }
    config.TELEGRAM_BOT_TOKEN = "token-abc"
    config.TELEGRAM_CHAT_ID = "chat-123"
    config.NOTIFY_MODE = "telegram"
    email = f"bot-{uuid.uuid4().hex[:8]}@example.com"
    try:
        user_id = create_user("Bot Tester", email, "9898989898", "Caregiver", "9090909090", "pass123")

        with app_module.app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = user_id

            with patch("services.telegram_service.send_telegram_message", return_value={"ok": True, "message_id": 7}) as send_mock:
                response = client.post("/api/notifications/test-telegram", json={})

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert "telegram" in (payload["message"] or "").lower()
        assert send_mock.call_args.args[0] == "🤖 MEDBOT Test Notification\n\nTelegram notifications are working successfully."
    finally:
        _restore_env(original)
        config.TELEGRAM_BOT_TOKEN = original["TELEGRAM_BOT_TOKEN"]
        config.TELEGRAM_CHAT_ID = original["TELEGRAM_CHAT_ID"]
        config.NOTIFY_MODE = original["NOTIFY_MODE"]


def test_authenticated_page_templates_render(isolated_database):
    email = f"pages-{uuid.uuid4().hex[:8]}@example.com"
    user_id = create_user("Page Tester", email, "9898989897", "Caretaker", "9090909091", "pass123")

    with app_module.app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = user_id

        for path in (
            "/dashboard",
            "/medicines",
            "/schedule",
            "/face-recognition",
            "/notifications",
            "/hardware",
            "/history",
            "/profile",
        ):
            response = client.get(path)
            assert response.status_code == 200, path
