from datetime import datetime
from zoneinfo import ZoneInfo

KOLKATA = ZoneInfo("Asia/Kolkata")


def now_kolkata():
    return datetime.now(KOLKATA)


def formatDateTime(value):
    """Format timestamps consistently in Asia/Kolkata with a 12-hour clock."""
    if not value:
        return "—"
    try:
        text = str(value)
        if len(text) == 5 and text[2] == ":":
            return datetime.strptime(text, "%H:%M").strftime("%I:%M %p")
        if len(text) == 10 and text[4] == "-":
            return datetime.strptime(text, "%Y-%m-%d").strftime("%d %b %Y")
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KOLKATA)
        return parsed.astimezone(KOLKATA).strftime("%d %b %Y, %I:%M %p")
    except (TypeError, ValueError):
        return str(value)


def database_timestamp():
    return now_kolkata().strftime("%Y-%m-%d %H:%M:%S")