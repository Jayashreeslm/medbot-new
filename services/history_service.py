from datetime import timedelta
from database.db import get_connection
from services.time_service import now_kolkata


def list_history(patient_id, range_filter="all", medicine_id=None, search=None):
    conn = get_connection()
    query = """
        SELECT h.*, m.medicine_name, m.dosage, m.compartment_number
        FROM medicine_history h
        LEFT JOIN medicines m ON m.id = h.medicine_id
        WHERE h.patient_id = ?
    """
    params = [patient_id]

    now = now_kolkata()
    if range_filter == "today":
        start = now.strftime("%Y-%m-%d 00:00:00")
        query += " AND h.created_at >= ?"
        params.append(start)
    elif range_filter == "week":
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        query += " AND h.created_at >= ?"
        params.append(start)
    elif range_filter == "month":
        start = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        query += " AND h.created_at >= ?"
        params.append(start)

    if medicine_id:
        query += " AND h.medicine_id = ?"
        params.append(medicine_id)

    if search:
        query += " AND m.medicine_name LIKE ?"
        params.append(f"%{search}%")

    query += " ORDER BY h.created_at DESC LIMIT 300"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
