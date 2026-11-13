
from datetime import datetime
from .database import get_connection
from .utils import now_iso, log_event, record_bus_event


def get_schedules():
    """Retrieve available bus schedules for commuters."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.*,
                r.route_name,
                r.origin,
                r.destination,
                r.fare_amount
            FROM schedules s
            JOIN routes r ON r.route_id = s.route_id
            ORDER BY s.travel_date, s.departure_time
            """
        ).fetchall()
    return rows


def add_schedule(
    route_id,
    travel_date,
    departure_time,
    arrival_time,
    bus_stops,
    bus_id=None,
):
    """Create a new bus schedule."""
    if not all([
        route_id, travel_date, departure_time,
        arrival_time, bus_stops
    ]):
        raise ValueError("All schedule fields are required.")

    try:
        datetime.strptime(str(travel_date), "%Y-%m-%d")
        datetime.strptime(str(departure_time), "%H:%M")
        datetime.strptime(str(arrival_time), "%H:%M")
    except ValueError:
        raise ValueError(
            "Enter the date as YYYY-MM-DD and times as HH:MM."
        )

    route_id = str(route_id).strip()
    bus_stops = str(bus_stops).strip()

    if not bus_stops:
        raise ValueError("At least one bus stop must be provided.")

    with get_connection() as conn:
        route = conn.execute(
            "SELECT route_id FROM routes WHERE route_id = ?",
            (route_id,)
        ).fetchone()

        if not route:
            raise ValueError("The selected route does not exist.")

        cursor = conn.execute(
            """
            INSERT INTO schedules (
                route_id, bus_id, travel_date, departure_time,
                arrival_time, bus_stops
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                route_id,
                str(bus_id).strip() if bus_id else None,
                travel_date,
                departure_time,
                arrival_time,
                bus_stops
            )
        )

        schedule_id = cursor.lastrowid

        log_event(
            conn,
            "SCHEDULE CREATED",
            f"Schedule {schedule_id} created for route {route_id}."
        )

    return "Bus schedule added successfully."


def update_schedule(
    schedule_id,
    route_id,
    travel_date,
    departure_time,
    arrival_time,
    bus_stops,
    bus_id=None,
):
    """Update an existing bus schedule."""
    if not all([
        schedule_id, route_id, travel_date,
        departure_time, arrival_time, bus_stops
    ]):
        raise ValueError("All schedule fields are required.")

    try:
        datetime.strptime(str(travel_date), "%Y-%m-%d")
        datetime.strptime(str(departure_time), "%H:%M")
        datetime.strptime(str(arrival_time), "%H:%M")
        schedule_id = int(schedule_id)
    except (TypeError, ValueError):
        raise ValueError("Invalid schedule ID, date or time format.")

    route_id = str(route_id).strip()
    bus_stops = str(bus_stops).strip()

    if not bus_stops:
        raise ValueError("At least one bus stop must be provided.")

    with get_connection() as conn:
        route = conn.execute(
            "SELECT route_id FROM routes WHERE route_id = ?",
            (route_id,)
        ).fetchone()

        if not route:
            raise ValueError("The selected route does not exist.")

        cursor = conn.execute(
            """
            UPDATE schedules
            SET route_id = ?,
                bus_id = ?,
                travel_date = ?,
                departure_time = ?,
                arrival_time = ?,
                bus_stops = ?
            WHERE schedule_id = ?
            """,
            (
                route_id,
                str(bus_id).strip() if bus_id else None,
                travel_date,
                departure_time,
                arrival_time,
                bus_stops,
                schedule_id
            )
        )

        if cursor.rowcount == 0:
            raise ValueError("Schedule does not exist.")

        log_event(
            conn,
            "SCHEDULE UPDATED",
            f"Schedule {schedule_id} was updated."
        )

    return "Bus schedule updated successfully."


def delete_schedule(schedule_id):
    """Delete an existing bus schedule."""
    try:
        schedule_id = int(schedule_id)
    except (TypeError, ValueError):
        raise ValueError("Invalid schedule ID.")

    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM schedules WHERE schedule_id = ?",
            (schedule_id,)
        )

        if cursor.rowcount == 0:
            raise ValueError("Schedule does not exist.")

        log_event(
            conn,
            "SCHEDULE DELETED",
            f"Schedule {schedule_id} was deleted."
        )

    return "Bus schedule deleted successfully."


def get_bus_locations():
    """Retrieve the latest recorded location for each bus."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                l.location_id,
                l.bus_id,
                b.current_route_id,
                l.latitude,
                l.longitude,
                l.speed,
                l.status,
                l.recorded_at
            FROM bus_locations l
            JOIN buses b ON b.bus_id = l.bus_id
            WHERE l.location_id = (
                SELECT MAX(l2.location_id)
                FROM bus_locations l2
                WHERE l2.bus_id = l.bus_id
            )
            """
        ).fetchall()
    return rows


def validate_assignment(bus_id, route_id, driver_id):
    if not bus_id or not route_id or not driver_id:
        return False

    bus_id = str(bus_id).strip()
    route_id = str(route_id).strip()
    driver_id = str(driver_id).strip()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT a.assignment_id
            FROM assignments a
            JOIN buses b ON b.bus_id = a.bus_id
            JOIN routes r ON r.route_id = a.route_id
            JOIN drivers d ON d.driver_id = a.driver_id
            WHERE a.bus_id = ?
              AND a.route_id = ?
              AND a.driver_id = ?
              AND UPPER(TRIM(a.status)) IN (
                  'ASSIGNED', 'ACTIVE', 'IN_SERVICE'
              )
              AND UPPER(TRIM(r.status)) = 'ACTIVE'
              AND d.active = 1
            """,
            (bus_id, route_id, driver_id)
        ).fetchone()

    return row is not None


def operate_bus_on_route(bus_id, route_id, driver_id):
    if not validate_assignment(bus_id, route_id, driver_id):
        raise ValueError("Invalid bus/route/driver assignment.")

    bus_id = str(bus_id).strip()
    route_id = str(route_id).strip()
    driver_id = str(driver_id).strip()

    with get_connection() as conn:
        bus = conn.execute(
            "SELECT bus_id, status FROM buses WHERE bus_id = ?",
            (bus_id,)
        ).fetchone()

        if not bus:
            raise ValueError("Bus does not exist.")

        if bus["status"] == "IN_SERVICE":
            raise ValueError("This bus is already in service.")

        conn.execute(
            """
            UPDATE buses
            SET status = 'IN_SERVICE', current_route_id = ?
            WHERE bus_id = ?
            """,
            (route_id, bus_id)
        )

        record_bus_event(
            conn,
            bus_id,
            "OPERATION STARTED",
            f"Bus {bus_id} started operation on route {route_id}."
        )

        log_event(
            conn,
            "BUS STARTED",
            f"Bus {bus_id} started operation on route {route_id}.",
            driver_id
        )

    return "Bus operation started successfully."


def report_delay(bus_id, reason, delay_minutes, latitude=None, longitude=None):
    if not bus_id or not str(bus_id).strip():
        raise ValueError("Bus ID is required.")

    if not reason or not str(reason).strip():
        raise ValueError("Delay reason is required.")

    try:
        minutes = int(delay_minutes)
    except (TypeError, ValueError):
        raise ValueError("Delay minutes must be a whole number.")

    if str(delay_minutes).strip() != str(minutes):
        raise ValueError("Delay minutes must be a whole number.")

    if minutes < 0:
        raise ValueError("Delay minutes cannot be negative.")

    if (latitude is None) != (longitude is None):
        raise ValueError("Both latitude and longitude must be provided together.")

    if latitude is not None:
        lat, lon, _ = validate_gps(latitude, longitude, 0)
    else:
        lat, lon = None, None

    bus_id = str(bus_id).strip()
    reason = str(reason).strip()

    with get_connection() as conn:
        bus = conn.execute(
            "SELECT bus_id FROM buses WHERE bus_id = ?",
            (bus_id,)
        ).fetchone()

        if not bus:
            raise ValueError("Bus does not exist.")

        conn.execute(
            """
            INSERT INTO delay_reports
            (bus_id, reported_at, reason, delay_minutes, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (bus_id, now_iso(), reason, minutes, lat, lon)
        )

        record_bus_event(
            conn,
            bus_id,
            "DELAY REPORTED",
            f"{reason} - {minutes} minutes."
        )

        log_event(
            conn,
            "DELAY REPORTED",
            f"Delay reported for {bus_id}: {reason}, {minutes} minutes."
        )

    notification = (
        f"Passenger notification required: expected delay of {minutes} minutes."
        if minutes > 15
        else "No passenger notification required."
    )

    return (
        "Delay report recorded for the control centre. "
        f"{notification} "
        "This application does not currently send live passenger notifications."
    )


def validate_gps(latitude, longitude, speed):
    try:
        lat = float(latitude)
        lon = float(longitude)
        velocity = float(speed)
    except (TypeError, ValueError):
        raise ValueError("GPS latitude, longitude and speed must be numeric.")

    if not -90 <= lat <= 90:
        raise ValueError("Latitude must be between -90 and 90.")

    if not -180 <= lon <= 180:
        raise ValueError("Longitude must be between -180 and 180.")

    if velocity < 0:
        raise ValueError("Speed cannot be negative.")

    return lat, lon, velocity


def track_bus_location(bus_id, latitude, longitude, speed, status):
    if not bus_id or not str(bus_id).strip():
        raise ValueError("Bus ID is required.")

    bus_id = str(bus_id).strip()
    lat, lon, velocity = validate_gps(latitude, longitude, speed)

    allowed = {"ON_TIME", "DELAYED", "OFF_ROUTE", "STOPPED"}

    if status not in allowed:
        raise ValueError(
            f"Status must be one of: {', '.join(sorted(allowed))}."
        )

    with get_connection() as conn:
        bus = conn.execute(
            "SELECT status FROM buses WHERE bus_id = ?",
            (bus_id,)
        ).fetchone()

        if not bus:
            raise ValueError("Bus does not exist.")

        if bus["status"] != "IN_SERVICE":
            raise ValueError("Location can only be recorded for a bus in service.")

        conn.execute(
            """
            INSERT INTO bus_locations
            (bus_id, latitude, longitude, speed, status, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (bus_id, lat, lon, velocity, status, now_iso())
        )

        log_event(
            conn,
            "LOCATION UPDATED",
            f"{bus_id}: {lat}, {lon}, speed {velocity}, status {status}."
        )

    return "Bus location and status saved successfully."


def send_service_status_update(bus_id):
    if not bus_id or not str(bus_id).strip():
        raise ValueError("Bus ID is required.")

    bus_id = str(bus_id).strip()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                b.bus_id,
                b.current_route_id,
                l.latitude,
                l.longitude,
                l.speed,
                l.status,
                l.recorded_at
            FROM buses b
            LEFT JOIN bus_locations l
                ON l.location_id = (
                    SELECT MAX(location_id)
                    FROM bus_locations
                    WHERE bus_id = b.bus_id
                )
            WHERE b.bus_id = ?
            """,
            (bus_id,)
        ).fetchone()

        if not row:
            raise ValueError("Bus does not exist.")

        if row["recorded_at"] is None:
            raise ValueError("No location/status data is available for this bus.")

        message = dict(row)

        log_event(
            conn,
            "STATUS UPDATE PREPARED",
            f"Status update prepared for {bus_id} for the control centre and passenger app."
        )

    return message


def stop_bus(bus_id):
    if not bus_id or not str(bus_id).strip():
        raise ValueError("Bus ID is required.")

    bus_id = str(bus_id).strip()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE buses
            SET status = 'AVAILABLE', current_route_id = NULL
            WHERE bus_id = ?
            """,
            (bus_id,)
        )

        if cursor.rowcount == 0:
            raise ValueError("Bus does not exist.")

        record_bus_event(
            conn,
            bus_id,
            "SERVICE ENDED",
            "Bus taken out of service."
        )

        log_event(
            conn,
            "SERVICE ENDED",
            f"Bus {bus_id} taken out of service."
        )

    return "Bus service ended successfully."
