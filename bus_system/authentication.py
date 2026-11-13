"""Account registration, login and the single Main Administrator bootstrap."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from .database import get_connection
from .utils import now_iso, log_event

ITERATIONS = 310_000
ROLES = {"MAIN_ADMIN", "ADMIN", "COMMUTER"}
LOGIN_ATTEMPT_LIMIT = 3
LOGIN_LOCKOUT_MINUTES = 15


def _username_key(username):
    return str(username or "").strip().casefold()


def _utc_now():
    return datetime.now(timezone.utc)


def _parse_lockout(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def login_lockout_seconds(username):
    """Return remaining lockout time for a username, or zero if unlocked."""
    key = _username_key(username)
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT locked_until
            FROM login_attempts
            WHERE username_key = ?
            """,
            (key,),
        ).fetchone()

        locked_until = _parse_lockout(row["locked_until"]) if row else None
        if not locked_until:
            return 0

        remaining = (locked_until - _utc_now()).total_seconds()
        if remaining > 0:
            return int(remaining) + 1

        conn.execute(
            "DELETE FROM login_attempts WHERE username_key = ?",
            (key,),
        )
    return 0


def record_login_failure(username):
    """Count a failed sign-in and return lockout seconds when threshold is hit."""
    key = _username_key(username)
    now = _utc_now()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT failed_attempts, locked_until
            FROM login_attempts
            WHERE username_key = ?
            """,
            (key,),
        ).fetchone()

        existing_lock = _parse_lockout(row["locked_until"]) if row else None
        if existing_lock and existing_lock > now:
            return int((existing_lock - now).total_seconds()) + 1

        failed_attempts = (
            int(row["failed_attempts"]) + 1
            if row and not existing_lock
            else 1
        )
        locked_until = None
        if failed_attempts >= LOGIN_ATTEMPT_LIMIT:
            locked_until = (
                now + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
            ).isoformat(timespec="seconds")

        conn.execute(
            """
            INSERT INTO login_attempts (
                username_key, failed_attempts, locked_until
            )
            VALUES (?, ?, ?)
            ON CONFLICT(username_key) DO UPDATE SET
                failed_attempts = excluded.failed_attempts,
                locked_until = excluded.locked_until
            """,
            (key, failed_attempts, locked_until),
        )

        return LOGIN_LOCKOUT_MINUTES * 60 if locked_until else 0


def clear_login_failures(username):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM login_attempts WHERE username_key = ?",
            (_username_key(username),),
        )

def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS).hex()

def create_account(username, email, password):
    username, email = username.strip(), email.strip().lower()
    if len(username) < 3:
        raise ValueError("Username must contain at least 3 characters.")
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise ValueError("Enter a valid email address.")
    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters.")
    salt = secrets.token_bytes(16)
    with get_connection() as conn:
        try:
            cursor = conn.execute("""INSERT INTO users
                (username,email,password_hash,password_salt,role,created_at)
                VALUES (?,?,?,?, 'COMMUTER', ?)""",
                (username, email, _hash_password(password, salt), salt.hex(), now_iso()))
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise ValueError("That username or email is already registered.") from exc
            raise
        log_event(conn, "ACCOUNT REGISTERED", f"Commuter account created: {username}")
        return cursor.lastrowid

def authenticate(username, password):
    if login_lockout_seconds(username):
        return None

    with get_connection() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE AND is_active=1", (username.strip(),)).fetchone()
    if not user:
        record_login_failure(username)
        return None
    salt = bytes.fromhex(user["password_salt"])
    candidate = _hash_password(password, salt)
    if not hmac.compare_digest(candidate, user["password_hash"]):
        record_login_failure(username)
        return None
    clear_login_failures(username)
    return {"user_id": user["user_id"], "username": user["username"], "email": user["email"], "role": user["role"]}


def bootstrap_main_admin():
    """Ensure the predefined Main Administrator account exists."""

    username = "mainadmin"
    email = "admin@example.com"
    password = "JutcDemoAdmin#2026"

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT user_id FROM users WHERE role='MAIN_ADMIN'"
        ).fetchone()

        if existing:
            return False

        salt = secrets.token_bytes(16)
        password_hash = _hash_password(password, salt)

        conn.execute(
            """INSERT INTO users
            (username, email, password_hash, password_salt, role, created_at)
            VALUES (?, ?, ?, ?, 'MAIN_ADMIN', ?)""",
            (
                username,
                email,
                password_hash,
                salt.hex(),
                now_iso()
            )
        )

        log_event(
            conn,
            "MAIN ADMIN BOOTSTRAPPED",
            "Predefined Main Administrator account initialized."
        )

    return True


def current_role(user_id):
    with get_connection() as conn:
        row = conn.execute("SELECT role FROM users WHERE user_id=? AND is_active=1", (user_id,)).fetchone()
    return row["role"] if row else None
