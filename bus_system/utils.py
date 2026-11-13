
from datetime import datetime, date
from decimal import Decimal, InvalidOperation


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def today_iso():
    return date.today().isoformat()


def parse_money(value, field_name="Amount"):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be numeric.")

    if not amount.is_finite():
        raise ValueError(f"{field_name} must be a valid number.")

    return amount.quantize(Decimal("0.01"))


def valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def log_event(conn, action, details, performed_by="SYSTEM"):
    conn.execute(
        "INSERT INTO logbook (created_at, action, details, performed_by) VALUES (?, ?, ?, ?)",
        (now_iso(), action, details, performed_by)
    )


def record_bus_event(conn, bus_id, event_type, details):
    conn.execute(
        "INSERT INTO bus_events (bus_id, event_time, event_type, details) VALUES (?, ?, ?, ?)",
        (bus_id, now_iso(), event_type, details)
    )
