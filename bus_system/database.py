
import sqlite3
from datetime import date, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "jutc_system.db"


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS routes (
    route_id TEXT PRIMARY KEY,
    route_name TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    distance_km REAL NOT NULL CHECK(distance_km > 0),
    duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0),
    status TEXT NOT NULL DEFAULT 'Active',
    fare_amount REAL NOT NULL DEFAULT 0.0 CHECK(fare_amount >= 0)
);

CREATE TABLE IF NOT EXISTS buses (
    bus_id TEXT PRIMARY KEY,
    bus_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'AVAILABLE',
    current_route_id TEXT,
    FOREIGN KEY(current_route_id) REFERENCES routes(route_id)
);

CREATE TABLE IF NOT EXISTS drivers (
    driver_id TEXT PRIMARY KEY,
    driver_name TEXT NOT NULL,
    licence_expiry TEXT NOT NULL,
    licensed_bus_type TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS assignments (
    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id TEXT NOT NULL,
    driver_id TEXT NOT NULL,
    bus_id TEXT NOT NULL,
    service_date TEXT NOT NULL,
    shift_start TEXT NOT NULL,
    shift_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Active',
    FOREIGN KEY(route_id) REFERENCES routes(route_id),
    FOREIGN KEY(driver_id) REFERENCES drivers(driver_id),
    FOREIGN KEY(bus_id) REFERENCES buses(bus_id)
);

CREATE TABLE IF NOT EXISTS logbook (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT NOT NULL,
    performed_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bus_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bus_id TEXT NOT NULL,
    event_time TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bus_locations (
    location_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bus_id TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    speed REAL NOT NULL,
    status TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delay_reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bus_id TEXT NOT NULL,
    reported_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    delay_minutes INTEGER NOT NULL,
    latitude REAL,
    longitude REAL
);

CREATE TABLE IF NOT EXISTS schedules (
    schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id TEXT NOT NULL,
    bus_id TEXT,
    travel_date TEXT NOT NULL,
    departure_time TEXT NOT NULL,
    arrival_time TEXT NOT NULL,
    bus_stops TEXT NOT NULL,
    FOREIGN KEY(route_id) REFERENCES routes(route_id)
);

CREATE TABLE IF NOT EXISTS bus_cards (
    card_id TEXT PRIMARY KEY,
    balance REAL NOT NULL CHECK(balance >= 0),
    main_balance REAL NOT NULL DEFAULT 0 CHECK(main_balance >= 0),
    active INTEGER NOT NULL DEFAULT 1,
    commuter_id INTEGER REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS fare_transactions (
    transaction_id TEXT PRIMARY KEY,
    transaction_date TEXT NOT NULL,
    transaction_time TEXT NOT NULL,
    route_id TEXT NOT NULL,
    fare_amount REAL NOT NULL,
    payment_method TEXT NOT NULL,
    payment_status TEXT NOT NULL,
    change_amount REAL NOT NULL DEFAULT 0,
    card_balance REAL,
    receipt_number TEXT NOT NULL,
    commuter_id INTEGER,
    terminal_reference TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'COMMUTER'
        CHECK(role IN ('MAIN_ADMIN', 'ADMIN', 'COMMUTER')),
    created_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS login_attempts (
    username_key TEXT PRIMARY KEY,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT
);

CREATE TABLE IF NOT EXISTS card_topups (
    topup_id TEXT PRIMARY KEY,
    commuter_id INTEGER NOT NULL,
    amount REAL NOT NULL CHECK(amount > 0),
    payment_method TEXT NOT NULL,
    payment_status TEXT NOT NULL,
    main_balance REAL NOT NULL,
    created_at TEXT NOT NULL,
    receipt_number TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS role_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_user_id INTEGER NOT NULL,
    old_role TEXT NOT NULL,
    new_role TEXT NOT NULL,
    changed_by INTEGER NOT NULL,
    changed_at TEXT NOT NULL,
    FOREIGN KEY(target_user_id) REFERENCES users(user_id),
    FOREIGN KEY(changed_by) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS receipts (
    receipt_number TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    receipt_text TEXT NOT NULL,
    FOREIGN KEY(transaction_id)
        REFERENCES fare_transactions(transaction_id)
);

CREATE TABLE IF NOT EXISTS daily_collections (
    collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_date TEXT NOT NULL UNIQUE,
    submitted_amount REAL NOT NULL,
    submitted_by TEXT NOT NULL,
    submitted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revenue_ledger (
    ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    amount REAL NOT NULL,
    description TEXT NOT NULL,
    reference TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reconciliation (
    reconciliation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    reconciliation_date TEXT NOT NULL UNIQUE,
    recorded_total REAL NOT NULL,
    submitted_total REAL NOT NULL,
    variance REAL NOT NULL,
    result TEXT NOT NULL,
    reconciled_at TEXT NOT NULL
);
"""

DEMO_ROUTES = [
    ("701", "Kingston", "Yallahs", "Kingston", 29.0, 75, "Active", 250.0),
    ("702", "Spanish Town", "Spanish Town", "Downtown Kingston", 25.0, 65, "Active", 180.0),
    ("703", "Portmore", "Portmore", "Downtown Kingston", 18.0, 50, "Active", 150.0),
    ("704", "Papine", "Papine", "Downtown Kingston", 11.0, 40, "Active", 120.0),
    ("705", "Half Way Tree", "Half Way Tree", "Portmore", 17.0, 55, "Active", 160.0),
    ("706", "Bull Bay", "Bull Bay", "Downtown Kingston", 16.0, 48, "Active", 140.0),
]

DEMO_BUSES = [
    ("JUTC-701-01", "Standard", "IN_SERVICE", "701"),
    ("JUTC-702-01", "Standard", "IN_SERVICE", "702"),
    ("JUTC-703-01", "Standard", "IN_SERVICE", "703"),
    ("JUTC-704-01", "Standard", "IN_SERVICE", "704"),
    ("JUTC-705-01", "Standard", "IN_SERVICE", "705"),
    ("JUTC-706-01", "Standard", "IN_SERVICE", "706"),
]

DEMO_SCHEDULES = {
    "701": ("06:30", "07:45", "Yallahs, Bull Bay, Harbour View, Downtown"),
    "702": ("06:45", "07:50", "Spanish Town, Angels, Six Miles, Downtown"),
    "703": ("07:00", "07:50", "Portmore, Bridgeport, Downtown"),
    "704": ("07:15", "07:55", "Papine, Half Way Tree, Downtown"),
    "705": ("07:30", "08:25", "Half Way Tree, Cross Roads, Portmore"),
    "706": ("07:45", "08:33", "Bull Bay, Harbour View, Downtown"),
}


def get_connection():
    DATA_DIR.mkdir(exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def initialize_database():
    with get_connection() as conn:
        conn.executescript(SCHEMA)

        route_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(routes)")
        }

        if "fare_amount" not in route_columns:
            conn.execute(
                """
                ALTER TABLE routes
                ADD COLUMN fare_amount REAL NOT NULL DEFAULT 0.0
                CHECK(fare_amount >= 0)
                """
            )

        if "frequency_minutes" in route_columns:
            if sqlite3.sqlite_version_info < (3, 35, 0):
                raise RuntimeError(
                    "Your SQLite version does not support dropping columns. "
                    "Upgrade SQLite before running this database migration."
                )

            conn.execute(
                "ALTER TABLE routes DROP COLUMN frequency_minutes"
            )

        transaction_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(fare_transactions)"
            )
        }

        if "commuter_id" not in transaction_columns:
            conn.execute(
                """
                ALTER TABLE fare_transactions
                ADD COLUMN commuter_id INTEGER
                """
            )

        if "terminal_reference" not in transaction_columns:
            conn.execute(
                """
                ALTER TABLE fare_transactions
                ADD COLUMN terminal_reference TEXT
                """
            )

        card_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(bus_cards)"
            )
        }

        if "main_balance" not in card_columns:
            conn.execute(
                """
                ALTER TABLE bus_cards
                ADD COLUMN main_balance REAL NOT NULL DEFAULT 0
                CHECK(main_balance >= 0)
                """
            )
            conn.execute(
                "UPDATE bus_cards SET main_balance = balance"
            )

        if "commuter_id" not in card_columns:
            conn.execute(
                """
                ALTER TABLE bus_cards
                ADD COLUMN commuter_id INTEGER
                REFERENCES users(user_id)
                """
            )

        schedule_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(schedules)")
        }
        if "bus_id" not in schedule_columns:
            conn.execute("ALTER TABLE schedules ADD COLUMN bus_id TEXT")

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_bus_cards_commuter
            ON bus_cards(commuter_id)
            WHERE commuter_id IS NOT NULL
            """
        )

        _seed_demo_service_data(conn)


def _seed_demo_service_data(conn):
    """Add clearly marked starter routes, buses and schedules to a blank app."""
    route_count = conn.execute(
        "SELECT COUNT(*) FROM routes"
    ).fetchone()[0]

    if route_count:
        return

    conn.executemany(
        """
        INSERT INTO routes (
            route_id, route_name, origin, destination, distance_km,
            duration_minutes, status, fare_amount
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        DEMO_ROUTES,
    )
    conn.executemany(
        """
        INSERT INTO buses (bus_id, bus_type, status, current_route_id)
        VALUES (?, ?, ?, ?)
        """,
        DEMO_BUSES,
    )

    first_day = date.today()
    for day_offset in range(7):
        travel_date = (first_day + timedelta(days=day_offset)).isoformat()
        for route_id, (departure, arrival, stops) in DEMO_SCHEDULES.items():
            conn.execute(
                """
                INSERT INTO schedules (
                    route_id, bus_id, travel_date, departure_time,
                    arrival_time, bus_stops
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    route_id,
                    f"JUTC-{route_id}-01",
                    travel_date,
                    departure,
                    arrival,
                    stops,
                ),
            )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fare_terminal_reference
            ON fare_transactions(terminal_reference)
            WHERE terminal_reference IS NOT NULL
            """
        )
