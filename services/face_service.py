import base64
import json
import traceback

import numpy as np

from database.db import get_connection
from services.time_service import database_timestamp

try:
    import cv2
    import face_recognition
    FACE_DEPENDENCIES_AVAILABLE = True
    FACE_DEPENDENCIES_ERROR = None
except Exception as e:
    # Catches ImportError (package not installed) AND any error raised while
    # face_recognition loads its models file (e.g. a failed/incomplete download
    # of face_recognition_models). Either way, we degrade gracefully instead
    # of crashing the whole app.
    FACE_DEPENDENCIES_AVAILABLE = False
    FACE_DEPENDENCIES_ERROR = f"{type(e).__name__}: {e}"
    print("FACE_DEPENDENCIES import failed:", FACE_DEPENDENCIES_ERROR)
    traceback.print_exc()

MATCH_TOLERANCE = 0.5  # lower = stricter. face_recognition default is 0.6
VALID_ANGLES = {"front", "left", "right", "up", "down"}


def dependency_error():
    return {
        "error": "Face recognition is unavailable on this machine because the required packages "
                 "are not installed. Run: python -m pip install -r requirements.txt",
        "code": "DEPENDENCIES_MISSING",
        "detail": FACE_DEPENDENCIES_ERROR,
    }


def _decode_base64_image(image_b64):
    """Accepts a data URL (data:image/jpeg;base64,...) or raw base64 string."""
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    binary = base64.b64decode(image_b64)
    arr = np.frombuffer(binary, dtype=np.uint8)
    image_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image_bgr is None:
        return None
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)


def extract_encoding(image_rgb):
    """Returns (encoding_as_list, error_code). error_code is None on success."""
    face_locations = face_recognition.face_locations(image_rgb)
    if len(face_locations) == 0:
        return None, "NO_FACE_DETECTED"
    if len(face_locations) > 1:
        return None, "MULTIPLE_FACES_DETECTED"

    encodings = face_recognition.face_encodings(image_rgb, known_face_locations=face_locations)
    if not encodings:
        return None, "NO_FACE_DETECTED"
    return encodings[0].tolist(), None


def register_face_sample(patient_id, image_b64, angle):
    if not FACE_DEPENDENCIES_AVAILABLE:
        return dependency_error(), 503

    if angle not in VALID_ANGLES:
        return {"error": f"Invalid angle. Must be one of {sorted(VALID_ANGLES)}."}, 400

    image_rgb = _decode_base64_image(image_b64)
    if image_rgb is None:
        return {"error": "Could not decode image."}, 400

    encoding, err = extract_encoding(image_rgb)
    if err:
        return {"error": err.replace("_", " ").title()}, 422

    conn = get_connection()
    conn.execute(
        """INSERT INTO face_encodings (patient_id, angle_label, encoding_json, created_at)
           VALUES (?, ?, ?, ?)""",
        (patient_id, angle, json.dumps(encoding), database_timestamp()),
    )
    conn.execute(
        "UPDATE users SET face_consent = 1 WHERE id = ?", (patient_id,)
    )
    conn.commit()

    count = conn.execute(
        "SELECT COUNT(*) as c FROM face_encodings WHERE patient_id = ?", (patient_id,)
    ).fetchone()["c"]
    conn.execute("UPDATE users SET face_data = ? WHERE id = ?", (f"{count} sample(s) registered", patient_id))
    conn.commit()
    conn.close()

    return {"message": f"{angle} sample registered.", "total_samples": count}, 201


def get_registration_status(patient_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT angle_label FROM face_encodings WHERE patient_id = ?", (patient_id,)
    ).fetchall()
    consent = conn.execute("SELECT face_consent FROM users WHERE id = ?", (patient_id,)).fetchone()
    conn.close()
    angles_captured = sorted({r["angle_label"] for r in rows})
    return {
        "total_samples": len(rows),
        "angles_captured": angles_captured,
        "angles_remaining": sorted(VALID_ANGLES - set(angles_captured)),
        "consent_given": bool(consent["face_consent"]) if consent else False,
    }


def delete_face_data(patient_id):
    conn = get_connection()
    conn.execute("DELETE FROM face_encodings WHERE patient_id = ?", (patient_id,))
    conn.execute("UPDATE users SET face_data = NULL, face_consent = 0 WHERE id = ?", (patient_id,))
    conn.commit()
    conn.close()
    return {"message": "Face data deleted."}


def _all_patients_encodings(exclude_patient_id=None):
    """Returns list of (patient_id, patient_name, np.array(encoding))."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT f.patient_id, u.name as patient_name, f.encoding_json
           FROM face_encodings f JOIN users u ON u.id = f.patient_id"""
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append((r["patient_id"], r["patient_name"], np.array(json.loads(r["encoding_json"]))))
    return result


def recognize(image_b64, scheduled_patient_id):
    """Compares a live frame against ALL registered patients' encodings.
    Returns one of: PATIENT_RECOGNIZED, WRONG_PATIENT_DETECTED, UNKNOWN_FACE, NO_FACE_DETECTED."""
    if not FACE_DEPENDENCIES_AVAILABLE:
        return dependency_error(), 503

    image_rgb = _decode_base64_image(image_b64)
    if image_rgb is None:
        return {"error": "Could not decode image."}, 400

    live_encoding, err = extract_encoding(image_rgb)
    if err == "NO_FACE_DETECTED":
        return {"status": "NO_FACE_DETECTED"}, 200
    if err == "MULTIPLE_FACES_DETECTED":
        return {"status": "MULTIPLE_FACES_DETECTED"}, 200

    return match_encoding(np.array(live_encoding), scheduled_patient_id)


def match_encoding(live_encoding, scheduled_patient_id):
    """Pure matching logic, separated so it can be tested without real image decoding."""
    all_encodings = _all_patients_encodings()
    if not all_encodings:
        return {"status": "UNKNOWN_FACE"}, 200

    best_patient_id, best_name, best_distance = None, None, None
    for patient_id, patient_name, known_encoding in all_encodings:
        distance = float(np.linalg.norm(known_encoding - live_encoding))
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_patient_id = patient_id
            best_name = patient_name

    if best_distance is None or best_distance > MATCH_TOLERANCE:
        return {"status": "UNKNOWN_FACE", "closest_distance": best_distance}, 200

    if best_patient_id == scheduled_patient_id:
        return {"status": "PATIENT_RECOGNIZED", "patient_id": best_patient_id,
                "patient_name": best_name, "distance": best_distance}, 200

    return {"status": "WRONG_PATIENT_DETECTED", "patient_id": best_patient_id,
            "patient_name": best_name, "distance": best_distance}, 200
