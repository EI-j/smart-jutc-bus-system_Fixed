
from datetime import datetime

from .database import get_connection
from .utils import now_iso, today_iso, log_event, valid_date


def assign_route_driver(route_id, driver_id, bus_id, service_date,
                        shift_start, shift_end):
    if not valid_date(service_date):
        raise ValueError("Invalid service date.")

    if shift_start >= shift_end:
        raise ValueError("Shift end must be later than shift start.")

    with get_connection() as conn:
        route = conn.execute(
            "SELECT route_id FROM routes WHERE route_id = ?",
            (route_id,)
        ).fetchone()

        driver = conn.execute(
            "SELECT driver_id FROM drivers WHERE driver_id = ? AND active = 1",
            (driver_id,)
        ).fetchone()

        bus = conn.execute(
            "SELECT bus_id FROM buses WHERE bus_id = ?",
            (bus_id,)
        ).fetchone()

        if not route:
            raise ValueError("Route does not exist.")

        if not driver:
            raise ValueError("Driver does not exist or is inactive.")

        if not bus:
            raise ValueError("Bus does not exist.")

        conn.execute(
            """
            INSERT INTO assignments (
                route_id,
                driver_id,
                bus_id,
                service_date,
                shift_start,
                shift_end,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'ASSIGNED')
            """,
            (
                route_id,
                driver_id,
                bus_id,
                service_date,
                shift_start,
                shift_end
            )
        )

        log_event(
            conn,
            "ROUTE_ASSIGNMENT",
            f"Driver {driver_id} and bus {bus_id} assigned to route {route_id}",
        )

    return "Route, driver, and bus assignment saved successfully."


def deactivate_assignment(assignment_id, performed_by=None):
    with get_connection() as conn:
        assignment = conn.execute(
            """
            SELECT assignment_id, status
            FROM assignments
            WHERE assignment_id = ?
            """,
            (assignment_id,)
        ).fetchone()

        if not assignment:
            raise ValueError("Assignment not found.")

        if str(assignment["status"]).upper() == "INACTIVE":
            raise ValueError("Assignment is already inactive.")

        conn.execute(
            """
            UPDATE assignments
            SET status = 'INACTIVE'
            WHERE assignment_id = ?
            """,
            (assignment_id,)
        )

        log_event(
            conn,
            "ASSIGNMENT_DEACTIVATED",
            f"Assignment {assignment_id} deactivated.",
            performed_by
        )

    return "Assignment deactivated successfully."


def add_route(route_id, route_name, origin, destination,
              distance_km, duration_minutes, fare_amount=0.0):
    if not route_id.strip() or not route_name.strip():
        raise ValueError("Route ID and route name are required.")

    if distance_km <= 0 or duration_minutes <= 0:
        raise ValueError("Route measurements must be greater than zero.")

    if fare_amount < 0:
        raise ValueError("Fare cannot be negative.")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO routes (
                route_id, route_name, origin, destination,
                distance_km, duration_minutes, status, fare_amount
            )
            VALUES (?, ?, ?, ?, ?, ?, 'Active', ?)
            """,
            (
                route_id.strip(), route_name.strip(),
                origin.strip(), destination.strip(),
                distance_km, duration_minutes, fare_amount
            )
        )

        log_event(conn, "ROUTE_ADDED", f"Route {route_id} added.")

    return "Route added successfully."


def update_route(route_id, route_name, origin, destination,
                 distance_km, duration_minutes):
    if distance_km <= 0 or duration_minutes <= 0:
        raise ValueError("Route measurements must be greater than zero.")

    with get_connection() as conn:
        result = conn.execute(
            """
            UPDATE routes
            SET route_name = ?,
                origin = ?,
                destination = ?,
                distance_km = ?,
                duration_minutes = ?
            WHERE route_id = ?
            """,
            (
                route_name.strip(), origin.strip(),
                destination.strip(), distance_km,
                duration_minutes, route_id
            )
        )

        if result.rowcount == 0:
            raise ValueError("Route not found.")

        log_event(conn, "ROUTE_UPDATED", f"Route {route_id} updated.")

    return "Route updated successfully."


def deactivate_route(route_id):
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE routes SET status = 'Inactive' WHERE route_id = ?",
            (route_id,)
        )

        if result.rowcount == 0:
            raise ValueError("Route not found.")

        log_event(conn, "ROUTE_DEACTIVATED", f"Route {route_id} deactivated.")

    return "Route deactivated successfully."


def list_routes():
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM routes ORDER BY route_name"
        ).fetchall()


def search_logbook(search_term=""):
    with get_connection() as conn:
        if search_term.strip():
            term = f"%{search_term.strip()}%"
            return conn.execute(
                """
                SELECT *
                FROM logbook
                WHERE bus_id LIKE ?
                   OR driver_id LIKE ?
                   OR route_id LIKE ?
                   OR description LIKE ?
                ORDER BY log_date DESC
                """,
                (term, term, term, term)
            ).fetchall()

        return conn.execute(
            "SELECT * FROM logbook ORDER BY log_date DESC"
        ).fetchall()


def log_driver_assignment(driver_id, bus_id, route_id, service_date):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO logbook (
                bus_id, driver_id, route_id, log_date, description
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                bus_id, driver_id, route_id,
                service_date,
                f"Driver {driver_id} assigned to route {route_id}"
            )
        )

        log_event(
            conn,
            "DRIVER_ASSIGNMENT_LOGGED",
            f"Driver {driver_id}, bus {bus_id}, route {route_id}",
        )

    return "Driver assignment logged successfully."


def delete_bus(bus_id, performed_by=None):
    with get_connection() as conn:
        bus = conn.execute(
            "SELECT bus_id FROM buses WHERE bus_id = ?",
            (bus_id,)
        ).fetchone()

        if not bus:
            raise ValueError("Bus not found.")

        conn.execute(
            """
            UPDATE assignments
            SET status = 'INACTIVE'
            WHERE bus_id = ?
            """,
            (bus_id,)
        )

        conn.execute(
            "DELETE FROM assignments WHERE bus_id = ?",
            (bus_id,)
        )

        conn.execute(
            "DELETE FROM bus_locations WHERE bus_id = ?",
            (bus_id,)
        )

        conn.execute(
            "DELETE FROM bus_events WHERE bus_id = ?",
            (bus_id,)
        )

        conn.execute(
            "DELETE FROM delay_reports WHERE bus_id = ?",
            (bus_id,)
        )

        conn.execute(
            "DELETE FROM buses WHERE bus_id = ?",
            (bus_id,)
        )

        log_event(
            conn,
            "BUS_DELETED",
            f"Bus {bus_id} deleted.",
            performed_by
        )

    return "Bus deleted successfully."


def delete_driver(driver_id, performed_by=None):
    with get_connection() as conn:
        driver = conn.execute(
            "SELECT driver_id FROM drivers WHERE driver_id = ?",
            (driver_id,)
        ).fetchone()

        if not driver:
            raise ValueError("Driver not found.")

        conn.execute(
            """
            UPDATE assignments
            SET status = 'INACTIVE'
            WHERE driver_id = ?
            """,
            (driver_id,)
        )

        conn.execute(
            "DELETE FROM assignments WHERE driver_id = ?",
            (driver_id,)
        )

        conn.execute(
            "DELETE FROM drivers WHERE driver_id = ?",
            (driver_id,)
        )

        log_event(
            conn,
            "DRIVER_DELETED",
            f"Driver {driver_id} deleted.",
            performed_by
        )

    return "Driver deleted successfully."


def delete_route(route_id, performed_by=None):
    with get_connection() as conn:
        route = conn.execute(
            "SELECT route_id FROM routes WHERE route_id = ?",
            (route_id,)
        ).fetchone()

        if not route:
            raise ValueError("Route not found.")

        conn.execute(
            """
            UPDATE assignments
            SET status = 'INACTIVE'
            WHERE route_id = ?
            """,
            (route_id,)
        )

        conn.execute(
            "DELETE FROM assignments WHERE route_id = ?",
            (route_id,)
        )

        conn.execute(
            "DELETE FROM schedules WHERE route_id = ?",
            (route_id,)
        )

        conn.execute(
            "UPDATE buses SET current_route_id = NULL WHERE current_route_id = ?",
            (route_id,)
        )

        conn.execute(
            "DELETE FROM routes WHERE route_id = ?",
            (route_id,)
        )

        log_event(
            conn,
            "ROUTE_DELETED",
            f"Route {route_id} deleted.",
            performed_by
        )

    return "Route deleted successfully."
