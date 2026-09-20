from datetime import datetime
import requests

from database.db import get_connection

REQUEST_TIMEOUT = 2.0  # seconds — keep short so the UI never hangs waiting on an offline ESP32

VALID_COMMANDS = {
    "DISPENSE_MEDICINE", "CHECK_PATIENT", "START_SEARCH_MODE", "STOP_SEARCH_MODE",
    "STOP_MOTOR", "MOVE_FORWARD", "MOVE_BACKWARD", "TURN_LEFT", "TURN_RIGHT",
    "MEDICINE_COLLECTED", "ACTIVATE_BUZZER",
}


def get_config(patient_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM hardware WHERE patient_id = ?", (patient_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_config(patient_id, esp32_ip, port):
    conn = get_connection()
    conn.execute(
        "UPDATE hardware SET esp32_ip = ?, port = ? WHERE patient_id = ?",
        (esp32_ip.strip(), port, patient_id),
    )
    conn.commit()
    conn.close()
    return get_config(patient_id)


def _set_connection_status(patient_id, connected):
    conn = get_connection()
    conn.execute(
        "UPDATE hardware SET connection_status = ?, last_seen = ? WHERE patient_id = ?",
        ("connected" if connected else "disconnected",
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"), patient_id),
    )
    conn.commit()
    conn.close()


def test_connection(patient_id):
    """Pings the configured ESP32. Never raises — always falls back to simulation mode."""
    config = get_config(patient_id)
    if not config:
        return {"connected": False, "mode": "HARDWARE_SIMULATION_MODE_ACTIVE", "error": "No hardware config found."}

    url = f"http://{config['esp32_ip']}:{config['port']}/status"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            _set_connection_status(patient_id, True)
            return {"connected": True, "mode": "HARDWARE_CONNECTED"}
        _set_connection_status(patient_id, False)
        return {"connected": False, "mode": "HARDWARE_SIMULATION_MODE_ACTIVE",
                "note": f"ESP32 responded with status {resp.status_code}."}
    except requests.exceptions.RequestException as e:
        _set_connection_status(patient_id, False)
        return {"connected": False, "mode": "HARDWARE_SIMULATION_MODE_ACTIVE", "note": str(e)}


def send_command(patient_id, command, payload=None):
    """Sends a command to the ESP32. Falls back to a simulated result if unreachable —
    never crashes, never blocks the caller for long."""
    if command not in VALID_COMMANDS:
        return {"error": f"Unknown command: {command}"}, 400

    config = get_config(patient_id)
    payload = payload or {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if config:
        url = f"http://{config['esp32_ip']}:{config['port']}/command"
        try:
            resp = requests.post(url, json={"command": command, **payload}, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                _set_connection_status(patient_id, True)
                return {
                    "mode": "HARDWARE_CONNECTED", "command": command, "status": "EXECUTED",
                    "esp32_response": resp.status_code, "timestamp": now,
                }, 200
            _set_connection_status(patient_id, False)
        except requests.exceptions.RequestException:
            _set_connection_status(patient_id, False)

    # Fall back to simulation — this branch is what runs whenever ESP32 is offline/unconfigured
    print(f"[MEDBOT] HARDWARE SIMULATION MODE ACTIVE -> command={command} payload={payload}")
    return {
        "mode": "HARDWARE_SIMULATION_MODE_ACTIVE", "command": command, "status": "SIMULATED",
        "timestamp": now,
    }, 200
