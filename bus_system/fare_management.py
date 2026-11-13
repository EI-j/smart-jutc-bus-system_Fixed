
import re
from datetime import datetime
from uuid import uuid4

from .database import get_connection
from .utils import now_iso, today_iso, parse_money, log_event

MIN_VIRTUAL_BALANCE = 100.0
PAYMENT_METHODS = {"Credit Card", "Debit Card"}


def validate_card_details(cardholder, card_number, expiry, cvc):
    """Validate demo card details and return only non-sensitive data.

    The full card number and CVC are checked here and then discarded. They
    are never stored or logged; only the last four digits are returned.
    """
    cardholder = str(cardholder or "").strip()
    digits = re.sub(r"[\s-]", "", str(card_number or ""))
    expiry = str(expiry or "").strip()
    cvc = str(cvc or "").strip()

    if not cardholder:
        raise ValueError("Enter the name on the card.")
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        raise ValueError("Enter a valid card number (13 to 19 digits).")

    checksum = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        checksum += value
    if checksum % 10 != 0:
        raise ValueError("That card number is not valid. Please check it.")

    match = re.fullmatch(r"(\d{2})\s*/\s*(\d{2})", expiry)
    if not match:
        raise ValueError("Enter the expiry date as MM/YY.")
    month, year = int(match.group(1)), 2000 + int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError("The expiry month must be between 01 and 12.")
    today = datetime.now()
    if (year, month) < (today.year, today.month):
        raise ValueError("This card has expired.")

    if not re.fullmatch(r"\d{3,4}", cvc):
        raise ValueError("Enter the 3 or 4 digit CVC.")

    return {"last4": digits[-4:]}


def check_bus_schedule(route_id, travel_date):
    try:
        datetime.strptime(travel_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError("Invalid travel date. Use YYYY-MM-DD.")

    if travel_date < today_iso():
        raise ValueError("Travel date cannot be in the past.")

    with get_connection() as conn:
        route = conn.execute(
            """
            SELECT *
            FROM routes
            WHERE route_id = ? AND status = 'Active'
            """,
            (route_id,)
        ).fetchone()

        if not route:
            raise ValueError("Invalid bus route. Please enter a valid route.")

        rows = conn.execute(
            """
            SELECT
                s.schedule_id,
                COALESCE(
                    s.bus_id,
                    (
                        SELECT a.bus_id
                        FROM assignments a
                        WHERE a.route_id = s.route_id
                          AND a.service_date = s.travel_date
                          AND a.status = 'Active'
                        ORDER BY a.assignment_id DESC
                        LIMIT 1
                    )
                ) AS bus_number,
                s.route_id,
                s.travel_date,
                s.departure_time,
                s.arrival_time,
                s.bus_stops,
                r.route_name,
                r.origin,
                r.destination,
                r.fare_amount
            FROM schedules s
            JOIN routes r ON r.route_id = s.route_id
            WHERE s.route_id = ? AND s.travel_date = ?
            ORDER BY s.departure_time
            """,
            (route_id, travel_date)
        ).fetchall()

    return rows


def link_bus_card(commuter_id, card_id, starting_balance=0.0):
    """Create or link a virtual bus card for a commuter."""

    card_id = str(card_id or "").strip()

    if not card_id:
        raise ValueError("Enter your bus card number or nickname.")

    balance = parse_money(starting_balance, "Starting card balance")

    if balance < MIN_VIRTUAL_BALANCE:
        raise ValueError(
            "The starting balance must be at least JMD $100.00."
        )

    with get_connection() as conn:

        existing = conn.execute(
            """
            SELECT card_id
            FROM bus_cards
            WHERE commuter_id = ?
            """,
            (commuter_id,)
        ).fetchone()

        if existing:
            raise ValueError("You already have a linked bus card.")

        card = conn.execute(
            """
            SELECT card_id, commuter_id, active
            FROM bus_cards
            WHERE card_id = ?
            """,
            (card_id,)
        ).fetchone()

        if card:

            if card["commuter_id"] is not None:
                raise ValueError(
                    "This card number is already linked to another account."
                )

            conn.execute(
                """
                UPDATE bus_cards
                SET commuter_id = ?,
                    balance = ?,
                    main_balance = ?,
                    active = 1
                WHERE card_id = ?
                """,
                (
                    commuter_id,
                    MIN_VIRTUAL_BALANCE,
                    round(float(balance) - MIN_VIRTUAL_BALANCE, 2),
                    card_id,
                )
            )

        else:

            conn.execute(
                """
                INSERT INTO bus_cards
                (card_id, balance, main_balance, active, commuter_id)
                VALUES (?, ?, ?, 1, ?)
                """,
                (
                    card_id,
                    MIN_VIRTUAL_BALANCE,
                    round(float(balance) - MIN_VIRTUAL_BALANCE, 2),
                    commuter_id,
                )
            )

        log_event(
            conn,
            "VIRTUAL BUS CARD LINKED",
            f"Virtual card {card_id} linked to commuter {commuter_id}."
        )

    return "Your virtual bus card has been linked successfully."


def get_linked_bus_card(commuter_id):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT card_id, balance, main_balance, active
            FROM bus_cards
            WHERE commuter_id = ? AND active = 1
            """,
            (commuter_id,)
        ).fetchone()


def update_card_balance(commuter_id, new_balance):
    """Compatibility wrapper for updating the commuter's virtual balance."""
    return update_virtual_balance(commuter_id, new_balance)


def update_virtual_balance(commuter_id, new_balance):
    """Set the virtual balance, moving the difference to/from main balance.

    Raising the virtual balance deducts the same amount from the main
    balance; lowering it returns the difference to the main balance. The
    virtual balance can never fall below JMD $100.00.
    """
    balance = parse_money(new_balance, "Virtual balance")
    if balance < MIN_VIRTUAL_BALANCE:
        raise ValueError(
            "Virtual balance cannot be less than JMD $100.00."
        )

    with get_connection() as conn:
        card = conn.execute(
            """
            SELECT card_id, balance, main_balance
            FROM bus_cards
            WHERE commuter_id = ? AND active = 1
            """,
            (commuter_id,),
        ).fetchone()
        if not card:
            raise ValueError("No linked active bus card was found.")

        current_virtual = float(
            parse_money(card["balance"], "Virtual balance")
        )
        main_balance = float(
            parse_money(card["main_balance"], "Main balance")
        )
        change = round(float(balance) - current_virtual, 2)

        if change > main_balance:
            raise ValueError(
                "Your main balance is too low. You can add at most "
                f"JMD ${main_balance:,.2f} to your virtual balance."
            )

        new_main = round(main_balance - change, 2)
        conn.execute(
            """
            UPDATE bus_cards
            SET balance = ?, main_balance = ?
            WHERE card_id = ? AND commuter_id = ? AND active = 1
            """,
            (float(balance), new_main, card["card_id"], commuter_id),
        )

        log_event(
            conn,
            "VIRTUAL CARD BALANCE UPDATED",
            (
                f"Commuter {commuter_id} moved JMD ${abs(change):.2f} "
                f"{'from' if change > 0 else 'to'} the main balance."
            ),
        )

    return {
        "virtual_balance": float(balance),
        "main_balance": new_main,
        "change": change,
    }


def top_up_main_balance(commuter_id, amount, payment_method, card_last4=None):
    """Add funds to the main balance (demo; no real payment is processed).

    Only the card type and, optionally, the last four digits are recorded.
    """
    amount = parse_money(amount, "Top-up amount")
    payment_method = str(payment_method or "").strip()

    if amount <= 0:
        raise ValueError("Top-up amount must be greater than zero.")
    if payment_method not in PAYMENT_METHODS:
        raise ValueError("Select Credit Card or Debit Card.")
    method_label = payment_method
    if card_last4:
        method_label = f"{payment_method} ending {str(card_last4)[-4:]}"

    with get_connection() as conn:
        card = conn.execute(
            """
            SELECT card_id, balance, main_balance
            FROM bus_cards
            WHERE commuter_id = ? AND active = 1
            """,
            (commuter_id,),
        ).fetchone()
        if not card:
            raise ValueError("No linked active bus card was found.")

        new_main_balance = round(
            float(card["main_balance"]) + float(amount),
            2,
        )
        topup_id = "TOP-" + uuid4().hex[:10].upper()
        receipt_number = "RCT-" + uuid4().hex[:8].upper()
        created_at = now_iso()

        conn.execute(
            """
            UPDATE bus_cards
            SET main_balance = ?
            WHERE card_id = ? AND commuter_id = ?
            """,
            (new_main_balance, card["card_id"], commuter_id),
        )
        conn.execute(
            """
            INSERT INTO card_topups (
                topup_id, commuter_id, amount, payment_method,
                payment_status, main_balance, created_at, receipt_number
            )
            VALUES (?, ?, ?, ?, 'Successful', ?, ?, ?)
            """,
            (
                topup_id,
                commuter_id,
                float(amount),
                method_label,
                new_main_balance,
                created_at,
                receipt_number,
            ),
        )
        log_event(
            conn,
            "DEMO MAIN BALANCE TOP-UP",
            (
                f"Commuter {commuter_id} added JMD ${amount:.2f} "
                f"using {method_label}; full card details were not stored."
            ),
        )

    return {
        "topup_id": topup_id,
        "amount": float(amount),
        "payment_method": method_label,
        "main_balance": new_main_balance,
        "receipt_number": receipt_number,
    }


def list_card_topups(commuter_id):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                topup_id,
                amount,
                payment_method,
                payment_status,
                main_balance,
                created_at,
                receipt_number
            FROM card_topups
            WHERE commuter_id = ?
            ORDER BY created_at DESC
            """,
            (commuter_id,),
        ).fetchall()


def pay_route_fare(commuter_id, route_id):
    """Deduct the selected route fare and record the virtual card payment."""

    now = datetime.now()

    transaction_id = "TX-" + uuid4().hex[:10].upper()
    receipt_number = "RCT-" + uuid4().hex[:8].upper()

    with get_connection() as conn:

        route = conn.execute(
            """
            SELECT route_id, route_name, fare_amount
            FROM routes
            WHERE route_id = ? AND status = 'Active'
            """,
            (route_id,)
        ).fetchone()

        if not route:
            raise ValueError("Please select a valid active route.")

        fare = parse_money(route["fare_amount"], "Route fare")

        if fare <= 0:
            raise ValueError(
                "A fare has not been configured for this route yet."
            )

        card = conn.execute(
            """
            SELECT card_id, balance
            FROM bus_cards
            WHERE commuter_id = ? AND active = 1
            """,
            (commuter_id,)
        ).fetchone()

        if not card:
            raise ValueError("You do not have a linked virtual bus card.")

        balance = parse_money(card["balance"], "Card balance")

        if balance < fare:
            raise ValueError(
                f"Insufficient balance. Your balance is ${balance:.2f}, "
                f"but the fare is ${fare:.2f}."
            )

        remaining = round(float(balance) - float(fare), 2)
        if remaining < MIN_VIRTUAL_BALANCE:
            raise ValueError(
                "A fare must leave at least JMD $100.00 in your virtual "
                "balance. Top up or adjust the virtual balance first."
            )

        conn.execute(
            """
            UPDATE bus_cards
            SET balance = ?
            WHERE card_id = ? AND commuter_id = ?
            """,
            (remaining, card["card_id"], commuter_id)
        )

        conn.execute(
            """
            INSERT INTO fare_transactions
            (
                transaction_id,
                transaction_date,
                transaction_time,
                route_id,
                fare_amount,
                payment_method,
                payment_status,
                change_amount,
                card_balance,
                receipt_number,
                commuter_id
            )
            VALUES (?, ?, ?, ?, ?, 'Virtual Bus Card',
                    'Successful', 0, ?, ?, ?)
            """,
            (
                transaction_id,
                now.date().isoformat(),
                now.strftime("%H:%M:%S"),
                route_id,
                float(fare),
                remaining,
                receipt_number,
                commuter_id
            )
        )

        receipt_text = "\n".join([
            "----- PAYMENT RECEIPT -----",
            f"Receipt Number: {receipt_number}",
            f"Date: {now.date().isoformat()}",
            f"Time: {now.strftime('%H:%M:%S')}",
            f"Route: {route['route_name']}",
            f"Fare Paid: ${float(fare):.2f}",
            "Payment Method: Virtual Bus Card",
            f"Remaining Balance: ${remaining:.2f}",
            "Payment Status: Successful",
            "Thank you for travelling."
        ])

        conn.execute(
            """
            INSERT INTO receipts
            (receipt_number, transaction_id, issued_at, receipt_text)
            VALUES (?, ?, ?, ?)
            """,
            (
                receipt_number,
                transaction_id,
                now_iso(),
                receipt_text
            )
        )

        log_event(
            conn,
            "VIRTUAL CARD FARE PAYMENT",
            (
                f"Commuter {commuter_id} paid ${float(fare):.2f} "
                f"for route {route_id}. Remaining balance: ${remaining:.2f}."
            )
        )

    return {
        "transaction_id": transaction_id,
        "receipt_number": receipt_number,
        "receipt_number": receipt_number,
        "route": route["route_name"],
        "fare": float(fare),
        "fare_amount": float(fare),
        "card_balance": remaining,
        "new_balance": remaining,
        "balance": remaining,
        "receipt": receipt_text,
        "receipt_text": receipt_text
    }


def record_card_terminal_payment(
    card_id,
    fare_amount,
    route_id,
    terminal_reference
):
    """Record a payment confirmed by an external terminal."""

    fare = parse_money(fare_amount, "Fare amount")
    terminal_reference = str(terminal_reference or "").strip()

    if fare <= 0:
        raise ValueError("Fare amount must be greater than zero.")

    if not terminal_reference:
        raise ValueError(
            "A confirmed terminal transaction reference is required."
        )

    now = datetime.now()
    transaction_id = "TX-" + uuid4().hex[:10].upper()
    receipt_number = "RCT-" + uuid4().hex[:8].upper()

    with get_connection() as conn:

        route = conn.execute(
            """
            SELECT route_id
            FROM routes
            WHERE route_id = ? AND status = 'Active'
            """,
            (route_id,)
        ).fetchone()

        if not route:
            raise ValueError("Invalid or inactive route.")

        card = conn.execute(
            """
            SELECT card_id, balance, commuter_id, active
            FROM bus_cards
            WHERE card_id = ?
            """,
            (str(card_id).strip(),)
        ).fetchone()

        if not card or not card["active"] or card["commuter_id"] is None:
            raise ValueError(
                "This card is not active or is not linked to a commuter account."
            )

        duplicate = conn.execute(
            """
            SELECT 1
            FROM fare_transactions
            WHERE terminal_reference = ?
            """,
            (terminal_reference,)
        ).fetchone()

        if duplicate:
            raise ValueError(
                "This terminal transaction has already been recorded."
            )

        balance = parse_money(card["balance"], "Card balance")

        if balance < fare:
            raise ValueError("Insufficient bus card balance.")

        remaining = round(float(balance) - float(fare), 2)
        if remaining < MIN_VIRTUAL_BALANCE:
            raise ValueError(
                "A fare must leave at least JMD $100.00 in the virtual "
                "balance."
            )

        conn.execute(
            """
            UPDATE bus_cards
            SET balance = ?
            WHERE card_id = ?
            """,
            (remaining, card["card_id"])
        )

        conn.execute(
            """
            INSERT INTO fare_transactions
            (
                transaction_id,
                transaction_date,
                transaction_time,
                route_id,
                fare_amount,
                payment_method,
                payment_status,
                change_amount,
                card_balance,
                receipt_number,
                commuter_id,
                terminal_reference
            )
            VALUES (?, ?, ?, ?, ?, 'Bus Card', 'Successful',
                    0, ?, ?, ?, ?)
            """,
            (
                transaction_id,
                now.date().isoformat(),
                now.strftime("%H:%M:%S"),
                route_id,
                float(fare),
                remaining,
                receipt_number,
                card["commuter_id"],
                terminal_reference
            )
        )

        receipt_text = "\n".join([
            "----- PAYMENT RECEIPT -----",
            f"Receipt Number: {receipt_number}",
            f"Date: {now.date().isoformat()}",
            f"Time: {now.strftime('%H:%M:%S')}",
            f"Route: {route_id}",
            f"Fare Paid: ${float(fare):.2f}",
            "Payment Method: Bus Card",
            f"Remaining Balance: ${remaining:.2f}",
            "Payment Status: Successful",
            "Thank you for travelling."
        ])

        conn.execute(
            """
            INSERT INTO receipts
            (receipt_number, transaction_id, issued_at, receipt_text)
            VALUES (?, ?, ?, ?)
            """,
            (
                receipt_number,
                transaction_id,
                now_iso(),
                receipt_text
            )
        )

        log_event(
            conn,
            "CARD FARE TRANSACTION",
            (
                f"{transaction_id}: ${float(fare):.2f}; "
                f"terminal reference {terminal_reference}"
            )
        )

    return {
        "transaction_id": transaction_id,
        "receipt_number": receipt_number,
        "date": now.date().isoformat(),
        "time": now.strftime("%H:%M:%S"),
        "fare": float(fare),
        "card_balance": remaining,
        "receipt": receipt_text
    }


def list_transactions(
    start_date=None,
    end_date=None,
    commuter_id=None,
    user_id=None
):
    """Return successful transactions, optionally for one commuter."""

    if commuter_id is not None and user_id is not None:
        if commuter_id != user_id:
            raise ValueError("Conflicting commuter account IDs were supplied.")

    if commuter_id is None:
        commuter_id = user_id

    query = """
        SELECT *
        FROM fare_transactions
        WHERE payment_status = 'Successful'
    """

    params = []

    if commuter_id is not None:
        query += " AND commuter_id = ?"
        params.append(commuter_id)

    if start_date:
        query += " AND transaction_date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND transaction_date <= ?"
        params.append(end_date)

    query += """
        ORDER BY transaction_date DESC, transaction_time DESC
    """

    with get_connection() as conn:
        return conn.execute(query, params).fetchall()
