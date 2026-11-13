
"""Streamlit interface for the Smart JUTC Bus Tracking & Digital Fare System."""

from datetime import date, datetime, time
from pathlib import Path
import random
import pandas as pd
import streamlit as st

from bus_system.database import initialize_database, get_connection
from bus_system.authentication import (
    create_account,
    authenticate,
    bootstrap_main_admin,
    login_lockout_seconds,
)
from bus_system.permissions import require_admin, require_main_admin
from bus_system import bus_operations, revenue, user_management
import bus_system.route_scheduling as route_scheduling
import bus_system.fare_management as fare_management


# --------------------------------------------------
# APPLICATION SETUP
# --------------------------------------------------

st.set_page_config(
    page_title="Smart JUTC",
    page_icon="🚌",
    layout="wide",
)

APP_DIR = Path(__file__).resolve().parent


def apply_app_theme():
    st.markdown(
        """
        <style>
        :root {
            --jutc-green: #157a4b;
            --jutc-deep-green: #0c5534;
            --jutc-gold: #e9bd3f;
            --jutc-ink: #17251f;
        }
        .stApp {
            background:
                radial-gradient(circle at 85% 0%, rgba(233, 189, 63, .13), transparent 26rem),
                linear-gradient(145deg, #f1f7f3 0%, #f7f8f3 52%, #edf4ee 100%);
            color: var(--jutc-ink);
        }
        [data-testid="stHeader"] { background: transparent; }
        .block-container { padding-top: 1.35rem; padding-bottom: 2rem; }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #103f2b 0%, #0c5534 100%);
        }
        [data-testid="stSidebar"] * { color: #f7fbf8; }
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: rgba(21, 122, 75, .18);
            border-radius: 18px;
            box-shadow: 0 16px 36px rgba(18, 58, 39, .08);
        }
        div.stButton > button,
        div[data-testid="stFormSubmitButton"] > button {
            border-radius: 10px;
            border: 1px solid var(--jutc-green);
            background: var(--jutc-green);
            color: white;
            font-weight: 650;
            transition: transform .16s ease, background .16s ease, box-shadow .16s ease;
        }
        div.stButton > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover {
            background: var(--jutc-deep-green);
            border-color: var(--jutc-deep-green);
            color: white;
            box-shadow: 0 7px 16px rgba(12, 85, 52, .18);
            transform: translateY(-1px);
        }
        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, .72);
            border: 1px solid rgba(21, 122, 75, .12);
            border-radius: 14px;
            padding: .9rem 1rem;
        }
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: var(--jutc-deep-green);
            border-bottom-color: var(--jutc-green);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


apply_app_theme()
initialize_database()

try:
    bootstrap_main_admin()
except Exception as exc:
    st.error(f"Main Administrator bootstrap could not complete: {exc}")

if "user" not in st.session_state:
    st.session_state.user = None


# --------------------------------------------------
# GENERAL FUNCTIONS
# --------------------------------------------------

def rows_as_dicts(rows):
    return [dict(row) for row in rows]


def friendly_frame(rows):
    frame = pd.DataFrame(rows_as_dicts(rows))
    if not frame.empty:
        frame.columns = [
            str(column).replace("_", " ").title()
            for column in frame.columns
        ]
    return frame


def logout():
    st.session_state.user = None
    st.rerun()


# --------------------------------------------------
# LOGIN AND REGISTRATION
# --------------------------------------------------

def login_screen():
    brand_column, account_column = st.columns([0.9, 1.1], gap="large")

    with brand_column:
        st.image(str(APP_DIR / "assets" / "jutc-logo.svg"), width=210)
        st.title("Smart JUTC")
        st.markdown(
            "Plan a trip, check route schedules, and manage your "
            "digital bus-card balance in one place."
        )

    with account_column:
        with st.container(border=True):
            st.subheader("Welcome")
            login_tab, register_tab = st.tabs(["Sign in", "Register"])

            with login_tab:
                with st.form("login_form"):
                    username = st.text_input("Username")
                    password = st.text_input("Password", type="password")
                    submitted = st.form_submit_button(
                        "Sign in",
                        use_container_width=True,
                    )

                if submitted:
                    remaining = login_lockout_seconds(username)
                    if remaining:
                        st.error(
                            "Sign-in is temporarily locked after three "
                            "failed attempts. Try again in 15 minutes."
                        )
                    else:
                        user = authenticate(username, password)
                        if user:
                            st.session_state.user = user
                            st.rerun()
                        else:
                            if login_lockout_seconds(username):
                                st.error(
                                    "Three sign-in attempts failed. "
                                    "Try again in 15 minutes."
                                )
                            else:
                                st.error(
                                    "The username or password is incorrect."
                                )

            with register_tab:
                with st.form("register_form"):
                    username = st.text_input(
                        "Create a username",
                        key="reg_username",
                    )
                    email = st.text_input("Create email address")
                    password = st.text_input(
                        "Create password",
                        type="password",
                        key="reg_password",
                    )
                    confirm = st.text_input(
                        "Confirm password",
                        type="password",
                    )
                    submitted = st.form_submit_button(
                        "Register",
                        use_container_width=True,
                    )

                if submitted:
                    if password != confirm:
                        st.error("The passwords do not match.")
                    else:
                        try:
                            create_account(username, email, password)
                            user = authenticate(username, password)
                            if not user:
                                raise ValueError(
                                    "Your account was created, but sign-in "
                                    "could not be completed. Please sign in."
                                )
                            st.session_state.user = user
                            st.session_state.account_created_notice = True
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))

    st.caption(
        "Commuter services and authorised operations management"
    )


# --------------------------------------------------
# SCHEDULE DISPLAY
# --------------------------------------------------

def show_schedules():
    st.subheader("Route schedules")

    with get_connection() as conn:
        routes = conn.execute(
            """
            SELECT route_id, route_name, origin, destination
            FROM routes
            WHERE status = 'Active'
            ORDER BY route_name
            """
        ).fetchall()

    if not routes:
        st.info("No active routes are available.")
        return

    route_map = {
        (
            f"{route['route_name']} "
            f"({route['origin']} to {route['destination']})"
        ): route["route_id"]
        for route in routes
    }

    selected_route = st.selectbox(
        "Select route",
        list(route_map.keys()),
    )
    travel_date = st.date_input(
        "Travel date",
        min_value=date.today(),
    )

    if st.button("Find schedules"):
        try:
            result = fare_management.check_bus_schedule(
                route_map[selected_route],
                travel_date.isoformat(),
            )

            if result:
                schedule_frame = friendly_frame(result)
                if "Fare Amount" in schedule_frame.columns:
                    schedule_frame["Fare Amount"] = schedule_frame[
                        "Fare Amount"
                    ].map(lambda fare: f"JMD ${float(fare):,.2f}")
                st.dataframe(
                    schedule_frame,
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info(
                    "No scheduled buses were found for this route and date."
                )
        except Exception as exc:
            st.error(str(exc))


def show_routes_catalog():
    st.subheader("Available Routes")
    st.caption(
        "Starter route names and fares are sample data for this demonstration."
    )
    with get_connection() as conn:
        routes = conn.execute(
            """
            SELECT route_id, route_name, origin, destination, fare_amount
            FROM routes
            WHERE status = 'Active'
            ORDER BY route_id
            """
        ).fetchall()
    if not routes:
        st.info("No active routes are available.")
        return
    frame = friendly_frame(routes)
    frame["Fare Amount"] = frame["Fare Amount"].map(
        lambda fare: f"JMD ${float(fare):,.2f}"
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)


ROUTE_TRACKING_PATHS = {
    "701": [(17.878, -76.556), (17.929, -76.668), (17.971, -76.793)],
    "702": [(17.992, -76.956), (18.006, -76.878), (17.971, -76.793)],
    "703": [(17.950, -76.876), (17.938, -76.828), (17.971, -76.793)],
    "704": [(18.020, -76.740), (18.012, -76.777), (17.971, -76.793)],
    "705": [(18.010, -76.796), (17.990, -76.839), (17.950, -76.876)],
    "706": [(17.942, -76.670), (17.950, -76.724), (17.971, -76.793)],
}


def route_demo_position(route_id, generator):
    path = ROUTE_TRACKING_PATHS.get(
        str(route_id),
        [(17.990, -76.850), (17.971, -76.793)],
    )
    segment = generator.randrange(max(1, len(path) - 1))
    start = path[segment]
    end = path[segment + 1]
    progress = generator.random()
    latitude = start[0] + (end[0] - start[0]) * progress
    longitude = start[1] + (end[1] - start[1]) * progress
    return round(latitude, 6), round(longitude, 6)


def build_tracking_rows(user_id):
    with get_connection() as conn:
        routes = conn.execute(
            """
            SELECT route_id, route_name, origin, destination
            FROM routes
            WHERE status = 'Active'
            ORDER BY route_id
            """
        ).fetchall()
        buses = conn.execute(
            """
            SELECT bus_id, current_route_id
            FROM buses
            ORDER BY bus_id
            """
        ).fetchall()

    generator = random.Random(
        f"{user_id}:{date.today().isoformat()}:jutc-tracking"
    )
    tracking_statuses = ["On time", "Late", "Delayed", "In traffic"]
    output = []

    for route in routes:
        assigned_buses = [
            bus for bus in buses
            if bus["current_route_id"] == route["route_id"]
        ]
        if not assigned_buses:
            output.append(
                {
                    "Bus Number": "No bus assigned",
                    "Route ID": route["route_id"],
                    "Route": (
                        f"{route['origin']} to {route['destination']}"
                    ),
                    "Bus Status": "Out of service",
                    "Tracking Status": "N/A",
                    "Latitude": None,
                    "Longitude": None,
                }
            )
            continue

        for bus in assigned_buses:
            in_service = generator.random() >= 0.28
            latitude = longitude = None
            if in_service:
                latitude, longitude = route_demo_position(
                    route["route_id"],
                    generator,
                )
            output.append(
                {
                    "Bus Number": bus["bus_id"],
                    "Route ID": route["route_id"],
                    "Route": (
                        f"{route['origin']} to {route['destination']}"
                    ),
                    "Bus Status": (
                        "In service" if in_service else "Out of service"
                    ),
                    "Tracking Status": (
                        generator.choice(tracking_statuses)
                        if in_service
                        else "N/A"
                    ),
                    "Latitude": latitude,
                    "Longitude": longitude,
                }
            )

    assigned_rows = [
        row for row in output if row["Bus Number"] != "No bus assigned"
    ]
    if len(assigned_rows) > 1:
        statuses = {row["Bus Status"] for row in assigned_rows}
        if statuses == {"In service"}:
            forced_bus = assigned_rows[-1]
            forced_bus["Bus Status"] = "Out of service"
            forced_bus["Tracking Status"] = "N/A"
            forced_bus["Latitude"] = None
            forced_bus["Longitude"] = None
        elif statuses == {"Out of service"}:
            forced_bus = assigned_rows[0]
            forced_bus["Bus Status"] = "In service"
            forced_bus["Tracking Status"] = generator.choice(
                tracking_statuses
            )
            forced_bus["Latitude"], forced_bus["Longitude"] = (
                route_demo_position(forced_bus["Route ID"], generator)
            )
    return output


# --------------------------------------------------
# COMMUTER DASHBOARD
# --------------------------------------------------

def commuter_dashboard(user):
    st.title("Commuter Dashboard")
    if st.session_state.pop("account_created_notice", False):
        st.success("Your account is ready. You are now signed in.")

    (
        schedules_tab,
        routes_tab,
        tracking_tab,
        card_tab,
        transactions_tab,
        delete_account_tab,
    ) = st.tabs(
        [
            "Schedules",
            "Routes",
            "Bus Tracking",
            "My Bus Card",
            "My Transactions",
            "Delete Account",
        ]
    )

    with schedules_tab:
        show_schedules()

    with routes_tab:
        show_routes_catalog()

    # ----------------------------------------------
    # BUS TRACKING
    # ----------------------------------------------

    with tracking_tab:
        st.subheader("Bus Tracking")

        try:
            tracking_rows = build_tracking_rows(user["user_id"])
            if tracking_rows:
                tracking_frame = pd.DataFrame(tracking_rows)
                tracking_event = st.dataframe(
                    tracking_frame.drop(
                        columns=["Latitude", "Longitude"],
                    ),
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="commuter_tracking_table",
                )

                selected_rows = getattr(
                    getattr(tracking_event, "selection", None),
                    "rows",
                    [],
                )
                if selected_rows:
                    selected = tracking_rows[selected_rows[0]]
                    st.subheader(
                        f"Selected bus: {selected['Bus Number']}"
                    )
                    st.caption(
                        f"Route {selected['Route ID']} · "
                        f"{selected['Route']} · "
                        f"{selected['Tracking Status']}"
                    )
                    if (
                        selected["Bus Status"] == "In service"
                        and selected["Latitude"] is not None
                        and selected["Longitude"] is not None
                    ):
                        st.map(
                            pd.DataFrame(
                                [
                                    {
                                        "lat": selected["Latitude"],
                                        "lon": selected["Longitude"],
                                    }
                                ]
                            ),
                            zoom=11,
                        )
                    else:
                        st.info(
                            "This bus is out of service and has no "
                            "trackable location."
                        )
                else:
                    st.info(
                        "Select a bus row to show its position on the map."
                    )
            else:
                st.info("No active routes are available to track.")

        except Exception as exc:
            st.error(
                f"Unable to retrieve bus tracking information: {exc}"
            )

        st.caption(
            "JUTC Bus Tracking Status: buses are shown on the map along "
            "their assigned route. Tracking Status shows whether a bus is "
            "On time, Late, Delayed or In traffic, and buses that are out "
            "of service are not shown on the map. Status is indicative and "
            "may change, so please confirm arrival times with JUTC."
        )

    # ----------------------------------------------
    # MY BUS CARD
    # ----------------------------------------------

    with card_tab:
        st.subheader("My Bus Card")

        try:
            card = fare_management.get_linked_bus_card(user["user_id"])
        except Exception as exc:
            card = None
            st.error(f"Unable to retrieve your bus card: {exc}")

        if card:
            st.success("Your physical bus card is linked.")
            st.write(f"**Card ID:** {card['card_id']}")

            main_balance = float(card["main_balance"])
            virtual_balance = float(card["balance"])
            main_column, virtual_column = st.columns(2)
            main_column.metric(
                "Main Balance",
                f"JMD ${main_balance:,.2f}",
            )
            virtual_column.metric(
                "Virtual Balance",
                f"JMD ${virtual_balance:,.2f}",
            )
            st.caption(
                "Your virtual balance pays route fares. Money you add to it "
                "is taken from your main balance, and the virtual balance "
                "must stay at or above JMD $100.00."
            )

            st.divider()
            st.subheader("Pay a Route Fare")

            try:
                with get_connection() as conn:
                    payable_routes = conn.execute(
                        """
                        SELECT
                            route_id,
                            route_name,
                            origin,
                            destination,
                            fare_amount
                        FROM routes
                        WHERE status = 'Active'
                          AND fare_amount > 0
                        ORDER BY route_name
                        """
                    ).fetchall()

                if payable_routes:
                    route_options = {
                        (
                            f"{route['route_name']} "
                            f"({route['origin']} to {route['destination']}) "
                            f"— JMD ${float(route['fare_amount']):,.2f}"
                        ): route["route_id"]
                        for route in payable_routes
                    }

                    selected_fare_route = st.selectbox(
                        "Select the route you are travelling on",
                        list(route_options.keys()),
                        key="commuter_fare_route",
                    )
                    selected_route_id = route_options[selected_fare_route]

                    selected_route = next(
                        route for route in payable_routes
                        if route["route_id"] == selected_route_id
                    )
                    selected_fare = float(selected_route["fare_amount"])

                    st.write(f"**Fare:** JMD ${selected_fare:,.2f}")

                    can_pay = virtual_balance - selected_fare >= 100.0
                    if not can_pay:
                        shortfall = max(
                            selected_fare + 100.0 - virtual_balance, 0.0
                        )
                        st.warning(
                            "Your virtual balance must cover the fare and "
                            "leave at least JMD $100.00 afterward. Add at "
                            f"least JMD ${shortfall:,.2f} to your virtual "
                            "balance below (taken from your main balance)."
                        )
                    if st.button(
                        "Pay Fare",
                        type="primary",
                        use_container_width=True,
                        key="pay_route_fare_button",
                        disabled=not can_pay,
                    ):
                        st.session_state["pending_fare_payment"] = {
                            "route_id": selected_route_id,
                            "route_name": selected_route["route_name"],
                            "fare": selected_fare,
                        }
                        st.rerun()

                    pending_fare = st.session_state.get(
                        "pending_fare_payment"
                    )
                    if pending_fare:
                        if pending_fare["route_id"] != selected_route_id:
                            st.session_state.pop(
                                "pending_fare_payment",
                                None,
                            )
                            pending_fare = None
                    if pending_fare:
                        st.info(
                            f"Confirm JMD ${pending_fare['fare']:,.2f} "
                            f"for route {pending_fare['route_id']} "
                            f"({pending_fare['route_name']})? It will be "
                            "deducted from your virtual balance only."
                        )
                        confirm_column, cancel_column = st.columns(2)
                        if confirm_column.button(
                            "Confirm Fare Payment",
                            type="primary",
                            use_container_width=True,
                            key="confirm_route_fare_payment",
                        ):
                            try:
                                payment_result = (
                                    fare_management.pay_route_fare(
                                        user["user_id"],
                                        selected_route_id,
                                    )
                                )
                                st.session_state[
                                    "last_payment_receipt"
                                ] = payment_result
                                st.session_state.pop(
                                    "pending_fare_payment",
                                    None,
                                )
                                st.rerun()
                            except Exception as exc:
                                st.error(
                                    f"Payment could not be completed: {exc}"
                                )
                        if cancel_column.button(
                            "Cancel",
                            use_container_width=True,
                            key="cancel_route_fare_payment",
                        ):
                            st.session_state.pop(
                                "pending_fare_payment",
                                None,
                            )
                            st.rerun()
                else:
                    st.info(
                        "No active routes have a fare configured yet. "
                        "An administrator must set the route fares first."
                    )
            except Exception as exc:
                st.error(f"Unable to load route fares: {exc}")

            last_payment = st.session_state.get("last_payment_receipt")

            if last_payment:
                st.divider()
                st.subheader("Latest Payment Receipt")

                if last_payment.get("receipt_number"):
                    st.write(
                        f"**Receipt number:** "
                        f"{last_payment['receipt_number']}"
                    )

                if last_payment.get("fare_amount") is not None:
                    st.write(
                        f"**Amount paid:** JMD "
                        f"${float(last_payment['fare_amount']):,.2f}"
                    )

                if last_payment.get("new_balance") is not None:
                    st.metric(
                        "Remaining Virtual Balance",
                        f"JMD ${float(last_payment['new_balance']):,.2f}",
                    )

                receipt_text = (
                    last_payment.get("receipt_text")
                    or last_payment.get("receipt")
                )

                if receipt_text:
                    st.code(receipt_text)

                if st.button("Clear Receipt", key="clear_payment_receipt"):
                    del st.session_state["last_payment_receipt"]
                    st.rerun()

            st.divider()
            st.subheader("Add to Main Balance")
            st.caption(
                "Demo only: no real payment is processed. Card details are "
                "checked and then discarded; only the last 4 digits are kept "
                "on your receipt. Use a test number such as "
                "4111 1111 1111 1111, not a real card."
            )
            with st.form("top_up_main_balance_form", clear_on_submit=True):
                topup_amount = st.number_input(
                    "Top-up amount (JMD)",
                    min_value=1.0,
                    value=100.0,
                    step=50.0,
                    format="%.2f",
                )
                payment_method = st.selectbox(
                    "Pay with",
                    ["Credit Card", "Debit Card"],
                )
                cardholder = st.text_input("Name on card")
                card_number = st.text_input(
                    "Card number",
                    max_chars=23,
                    placeholder="1234 5678 9012 3456",
                )
                expiry_column, cvc_column = st.columns(2)
                card_expiry = expiry_column.text_input(
                    "Expiry date (MM/YY)",
                    max_chars=5,
                    placeholder="MM/YY",
                )
                card_cvc = cvc_column.text_input(
                    "CVC",
                    max_chars=4,
                    type="password",
                    placeholder="123",
                )
                confirm_topup = st.form_submit_button(
                    "Confirm Payment",
                    type="primary",
                    use_container_width=True,
                )

            if confirm_topup:
                try:
                    card_info = fare_management.validate_card_details(
                        cardholder,
                        card_number,
                        card_expiry,
                        card_cvc,
                    )
                    result = fare_management.top_up_main_balance(
                        user["user_id"],
                        float(topup_amount),
                        payment_method,
                        card_last4=card_info["last4"],
                    )
                    st.session_state["topup_success"] = (
                        f"Payment confirmed: JMD ${result['amount']:,.2f} "
                        f"added to your main balance using "
                        f"{result['payment_method']}. "
                        f"Receipt {result['receipt_number']}."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

            topup_message = st.session_state.pop("topup_success", None)
            if topup_message:
                st.success(topup_message)

            st.divider()
            st.subheader("Virtual Balance")
            st.caption(
                "Money added to your virtual balance is deducted from your "
                "main balance. Route fares are paid from the virtual balance."
            )
            move_direction = st.radio(
                "Move money",
                ["Main to virtual balance", "Virtual to main balance"],
                horizontal=True,
                key="virtual_move_direction",
            )
            adding = move_direction == "Main to virtual balance"
            max_move = (
                main_balance if adding
                else max(virtual_balance - 100.0, 0.0)
            )

            if max_move < 1.0:
                st.info(
                    "Nothing available to move in this direction right now."
                    if not adding
                    else "Your main balance is empty. Add money to it above "
                         "first."
                )
            else:
                with st.form("update_virtual_balance_form"):
                    move_amount = st.number_input(
                        "Amount (JMD)",
                        min_value=1.0,
                        max_value=float(max_move),
                        value=min(100.0, float(max_move)),
                        step=50.0,
                        format="%.2f",
                    )
                    update_virtual = st.form_submit_button(
                        "Move Money",
                        use_container_width=True,
                    )

                if update_virtual:
                    try:
                        target = (
                            virtual_balance + move_amount if adding
                            else virtual_balance - move_amount
                        )
                        fare_management.update_virtual_balance(
                            user["user_id"],
                            target,
                        )
                        st.session_state["virtual_move_success"] = (
                            f"JMD ${move_amount:,.2f} moved "
                            f"{'to your virtual balance' if adding else 'back to your main balance'}."
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

            virtual_message = st.session_state.pop(
                "virtual_move_success", None
            )
            if virtual_message:
                st.success(virtual_message)
        else:
            st.info("You have not linked a bus card yet.")

            with st.form("link_bus_card_form"):
                card_id = st.text_input("Enter your physical bus card ID or nickname")
                starting_balance = st.number_input(
                    "Starting balance (JMD, minimum 100)",
                    min_value=100.0,
                    value=100.0,
                    step=50.0,
                    format="%.2f",
                )
                st.caption(
                    "JMD $100.00 is placed in your virtual balance (the "
                    "minimum); anything above that goes to your main balance."
                )
                link_card = st.form_submit_button("Link Bus Card")

            if link_card:
                if not card_id.strip():
                    st.error("Please enter your bus card ID.")
                else:
                    try:
                        message = fare_management.link_bus_card(
                            user["user_id"],
                            card_id.strip(),
                            float(starting_balance),
                        )
                        st.success(message)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Unable to link bus card: {exc}")

    # ----------------------------------------------
    # MY TRANSACTIONS
    # ----------------------------------------------

    with transactions_tab:
        st.subheader("My Bus Card Transactions")

        try:
            transactions = fare_management.list_transactions(
                None,
                None,
                user["user_id"],
            )
            topups = fare_management.list_card_topups(user["user_id"])
            transaction_rows = []

            for transaction in transactions:
                transaction = dict(transaction)
                transaction_rows.append(
                    {
                        "Type": "Fare payment",
                        "Transaction ID": transaction["transaction_id"],
                        "Date": transaction["transaction_date"],
                        "Time": transaction["transaction_time"],
                        "Route": transaction["route_id"],
                        "Amount": (
                            f"JMD ${float(transaction['fare_amount']):,.2f}"
                        ),
                        "Payment Method": transaction["payment_method"],
                        "Status": transaction["payment_status"],
                        "Balance After": (
                            f"JMD ${float(transaction['card_balance']):,.2f}"
                            if transaction["card_balance"] is not None
                            else "—"
                        ),
                        "Receipt Number": transaction["receipt_number"],
                    }
                )

            for topup in topups:
                topup = dict(topup)
                created_at = str(topup["created_at"])
                transaction_rows.append(
                    {
                        "Type": "Main balance top-up",
                        "Transaction ID": topup["topup_id"],
                        "Date": created_at[:10],
                        "Time": created_at[11:19],
                        "Route": "Main balance",
                        "Amount": f"JMD ${float(topup['amount']):,.2f}",
                        "Payment Method": topup["payment_method"],
                        "Status": topup["payment_status"],
                        "Balance After": (
                            f"JMD ${float(topup['main_balance']):,.2f}"
                        ),
                        "Receipt Number": topup["receipt_number"],
                    }
                )

            if transaction_rows:
                st.dataframe(
                    pd.DataFrame(transaction_rows),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info(
                    "You have no recorded bus-card transactions yet."
                )
        except Exception as exc:
            st.error(f"Unable to retrieve your transactions: {exc}")

    # ----------------------------------------------
    # DELETE COMMUTER ACCOUNT
    # ----------------------------------------------

    with delete_account_tab:
        st.subheader("Delete My Account")

        st.warning(
            "Deleting your account is permanent. Your linked virtual bus "
            "card, fare transactions, receipts and account information "
            "will also be deleted."
        )
        st.write(
            "This action cannot be undone. Your account cannot be restored "
            "after deletion."
        )

        with st.form("delete_commuter_account_form"):
            delete_confirmation = st.text_input("Type DELETE to confirm")
            confirm_account_deletion = st.checkbox(
                "I understand that my account and associated data "
                "will be permanently deleted."
            )
            delete_account = st.form_submit_button(
                "Permanently Delete My Account",
                type="primary",
            )

        if delete_account:
            if delete_confirmation != "DELETE":
                st.error("You must type DELETE exactly.")
            elif not confirm_account_deletion:
                st.error(
                    "Please confirm that you understand the consequences."
                )
            else:
                try:
                    message = user_management.delete_commuter_account(
                        user["user_id"]
                    )
                    st.session_state.user = None
                    st.session_state.pop("last_payment_receipt", None)
                    st.success(message)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Unable to delete your account: {exc}")


# --------------------------------------------------
# ADMINISTRATOR DASHBOARD
# --------------------------------------------------

def admin_dashboard(user):
    require_admin(user["user_id"])
    st.title("Administrator Dashboard")
    st.caption(
        "Operational tools are restricted to authorised administrators."
    )

    (
        overview_tab,
        operations_tab,
        routes_tab,
        delays_tab,
        revenue_tab,
    ) = st.tabs(
        [
            "Overview",
            "Bus Operations",
            "Routes & Assignments",
            "Delay Reports",
            "Revenue",
        ]
    )

    # ----------------------------------------------
    # OVERVIEW
    # ----------------------------------------------

    with overview_tab:
        with get_connection() as conn:
            counts = {
                "Buses": conn.execute(
                    "SELECT COUNT(*) FROM buses"
                ).fetchone()[0],
                "Active Routes": conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM routes
                    WHERE status = 'Active'
                    """
                ).fetchone()[0],
                "Drivers": conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM drivers
                    WHERE active = 1
                    """
                ).fetchone()[0],
                "Commuters": conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM users
                    WHERE role = 'COMMUTER'
                    """
                ).fetchone()[0],
            }

        columns = st.columns(len(counts))
        for column, (label, value) in zip(columns, counts.items()):
            column.metric(label, value)

        with get_connection() as conn:
            st.markdown("**Buses and current operating status**")
            buses = conn.execute(
                """
                SELECT *
                FROM buses
                ORDER BY bus_id
                """
            ).fetchall()
            st.dataframe(
                rows_as_dicts(buses),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("**Registered commuter accounts**")
            commuters = conn.execute(
                """
                SELECT user_id, username, email, created_at
                FROM users
                WHERE role = 'COMMUTER'
                ORDER BY created_at DESC
                """
            ).fetchall()
            st.dataframe(
                rows_as_dicts(commuters),
                use_container_width=True,
                hide_index=True,
            )

    # ----------------------------------------------
    # BUS OPERATIONS
    # ----------------------------------------------

    with operations_tab:
        st.subheader("Start Bus Operation")

        with st.form("start_bus_form"):
            bus_id = st.text_input("Bus ID")
            route_id = st.text_input("Route ID")
            driver_id = st.text_input("Driver ID")
            start_operation = st.form_submit_button("Start Operation")

        if start_operation:
            try:
                result = bus_operations.operate_bus_on_route(
                    bus_id,
                    route_id,
                    driver_id,
                )
                st.success(result)
            except Exception as exc:
                st.error(str(exc))


        st.divider()
        st.subheader("Record GPS Position and Status")

        with st.form("gps_update_form"):
            gps_bus = st.text_input("Bus ID", key="gps_bus")
            latitude = st.number_input(
                "Latitude",
                min_value=-90.0,
                max_value=90.0,
                value=18.0,
                format="%.6f",
            )
            longitude = st.number_input(
                "Longitude",
                min_value=-180.0,
                max_value=180.0,
                value=-77.0,
                format="%.6f",
            )
            speed = st.number_input(
                "Speed (km/h)",
                min_value=0.0,
                value=0.0,
            )
            service_status = st.selectbox(
                "Service Status",
                ["ON_TIME", "DELAYED", "OFF_ROUTE", "STOPPED"],
            )
            update_location = st.form_submit_button("Save Location")

        if update_location:
            try:
                result = bus_operations.track_bus_location(
                    gps_bus,
                    latitude,
                    longitude,
                    speed,
                    service_status,
                )
                st.success(result)
            except Exception as exc:
                st.error(str(exc))

        st.divider()
        st.subheader("End Bus Service")

        with st.form("stop_bus_form"):
            stop_id = st.text_input("Bus ID", key="stop_bus_id")
            stop_service = st.form_submit_button("End Service")

        if stop_service:
            try:
                bus_operations.stop_bus(stop_id)
                st.success("Bus service ended.")
            except Exception as exc:
                st.error(str(exc))

    # ----------------------------------------------
    # ROUTES, BUSES, DRIVERS AND ASSIGNMENTS
    # ----------------------------------------------

    with routes_tab:
        st.subheader("Active Route List")

        try:
            routes = route_scheduling.list_routes()
            st.dataframe(
                rows_as_dicts(routes),
                use_container_width=True,
                hide_index=True,
            )
        except Exception as exc:
            st.error(str(exc))

        # ------------------------------------------
        # MANAGE BUS SCHEDULES
        # ------------------------------------------

        st.divider()
        st.subheader("Manage Bus Schedules")

        try:
            with get_connection() as conn:
                schedule_routes = conn.execute(
                    """
                    SELECT route_id, route_name, origin, destination
                    FROM routes
                    WHERE status = 'Active'
                    ORDER BY route_name
                    """
                ).fetchall()
                schedule_buses = conn.execute(
                    "SELECT bus_id FROM buses ORDER BY bus_id"
                ).fetchall()

            if not schedule_routes:
                st.info(
                    "Add an active route before creating a bus schedule."
                )
            else:
                schedule_route_options = {
                    (
                        f"{route['route_name']} "
                        f"({route['origin']} to {route['destination']})"
                    ): route["route_id"]
                    for route in schedule_routes
                }
                schedule_bus_options = ["Unassigned"] + [
                    bus["bus_id"] for bus in schedule_buses
                ]

                st.markdown("**Add a Schedule**")

                with st.form("add_bus_schedule_form"):
                    new_schedule_route = st.selectbox(
                        "Select Route",
                        list(schedule_route_options.keys()),
                    )
                    new_schedule_bus = st.selectbox(
                        "Bus Number",
                        schedule_bus_options,
                    )
                    new_schedule_date = st.date_input(
                        "Travel Date",
                        min_value=date.today(),
                        key="new_schedule_date",
                    )
                    new_departure_time = st.time_input(
                        "Departure Time",
                        value=time(8, 0),
                        key="new_departure_time",
                    )
                    new_arrival_time = st.time_input(
                        "Arrival Time",
                        value=time(9, 0),
                        key="new_arrival_time",
                    )
                    new_bus_stops = st.text_area(
                        "Bus Stops",
                        placeholder="Enter stops separated by commas",
                    )
                    save_new_schedule = st.form_submit_button(
                        "Add Schedule"
                    )

                if save_new_schedule:
                    if new_arrival_time <= new_departure_time:
                        st.error(
                            "Arrival time must be later than departure time."
                        )
                    elif not new_bus_stops.strip():
                        st.error("Please enter the bus stops.")
                    else:
                        try:
                            result = bus_operations.add_schedule(
                                schedule_route_options[new_schedule_route],
                                new_schedule_date.isoformat(),
                                new_departure_time.strftime("%H:%M"),
                                new_arrival_time.strftime("%H:%M"),
                                new_bus_stops.strip(),
                                (
                                    None
                                    if new_schedule_bus == "Unassigned"
                                    else new_schedule_bus
                                ),
                            )
                            st.success(result)
                            st.rerun()
                        except Exception as exc:
                            st.error(
                                f"Unable to add schedule: {exc}"
                            )

                st.divider()
                st.markdown("**Existing Schedules**")

                existing_schedules = bus_operations.get_schedules()

                if existing_schedules:
                    schedule_data = rows_as_dicts(existing_schedules)
                    schedule_frame = friendly_frame(existing_schedules)
                    if "Bus Id" in schedule_frame.columns:
                        schedule_frame = schedule_frame.rename(
                            columns={"Bus Id": "Bus Number"}
                        )
                    if "Fare Amount" in schedule_frame.columns:
                        schedule_frame["Fare Amount"] = schedule_frame[
                            "Fare Amount"
                        ].map(lambda fare: f"JMD ${float(fare):,.2f}")
                    st.dataframe(
                        schedule_frame,
                        use_container_width=True,
                        hide_index=True,
                    )

                    schedule_options = {
                        (
                            f"Schedule {schedule['schedule_id']} — "
                            f"{schedule.get('route_name', schedule['route_id'])} "
                            f"— {schedule['travel_date']} "
                            f"({schedule['departure_time']})"
                        ): schedule["schedule_id"]
                        for schedule in schedule_data
                    }

                    selected_schedule_label = st.selectbox(
                        "Select Schedule to Edit or Delete",
                        list(schedule_options.keys()),
                        key="manage_schedule_selection",
                    )
                    selected_schedule_id = schedule_options[
                        selected_schedule_label
                    ]

                    selected_schedule = next(
                        schedule for schedule in schedule_data
                        if schedule["schedule_id"] == selected_schedule_id
                    )

                    st.markdown("**Edit Selected Schedule**")

                    existing_route_labels = list(
                        schedule_route_options.keys()
                    )
                    existing_route_ids = list(
                        schedule_route_options.values()
                    )

                    if selected_schedule["route_id"] in existing_route_ids:
                        current_route_index = existing_route_ids.index(
                            selected_schedule["route_id"]
                        )
                    else:
                        current_route_index = 0

                    edit_bus_options = list(schedule_bus_options)
                    selected_bus = selected_schedule.get("bus_id") or "Unassigned"
                    if selected_bus not in edit_bus_options:
                        edit_bus_options.append(selected_bus)
                    current_bus_index = edit_bus_options.index(selected_bus)

                    try:
                        current_schedule_date = date.fromisoformat(
                            selected_schedule["travel_date"]
                        )
                        current_departure_time = datetime.strptime(
                            selected_schedule["departure_time"],
                            "%H:%M",
                        ).time()
                        current_arrival_time = datetime.strptime(
                            selected_schedule["arrival_time"],
                            "%H:%M",
                        ).time()
                    except (ValueError, TypeError):
                        current_schedule_date = date.today()
                        current_departure_time = time(8, 0)
                        current_arrival_time = time(9, 0)

                    with st.form("edit_bus_schedule_form"):
                        edit_schedule_route = st.selectbox(
                            "Route",
                            existing_route_labels,
                            index=current_route_index,
                            key="edit_schedule_route",
                        )
                        edit_schedule_bus = st.selectbox(
                            "Bus Number",
                            edit_bus_options,
                            index=current_bus_index,
                            key="edit_schedule_bus",
                        )
                        edit_schedule_date = st.date_input(
                            "Travel Date",
                            value=current_schedule_date,
                            key="edit_schedule_date",
                        )
                        edit_departure_time = st.time_input(
                            "Departure Time",
                            value=current_departure_time,
                            key="edit_departure_time",
                        )
                        edit_arrival_time = st.time_input(
                            "Arrival Time",
                            value=current_arrival_time,
                            key="edit_arrival_time",
                        )
                        edit_bus_stops = st.text_area(
                            "Bus Stops",
                            value=selected_schedule["bus_stops"],
                            key="edit_bus_stops",
                        )
                        save_schedule_changes = st.form_submit_button(
                            "Save Schedule Changes"
                        )

                    if save_schedule_changes:
                        if edit_arrival_time <= edit_departure_time:
                            st.error(
                                "Arrival time must be later than departure time."
                            )
                        elif not edit_bus_stops.strip():
                            st.error("Please enter the bus stops.")
                        else:
                            try:
                                result = bus_operations.update_schedule(
                                    selected_schedule_id,
                                    schedule_route_options[
                                        edit_schedule_route
                                    ],
                                    edit_schedule_date.isoformat(),
                                    edit_departure_time.strftime("%H:%M"),
                                    edit_arrival_time.strftime("%H:%M"),
                                    edit_bus_stops.strip(),
                                    (
                                        None
                                        if edit_schedule_bus == "Unassigned"
                                        else edit_schedule_bus
                                    ),
                                )
                                st.success(result)
                                st.rerun()
                            except Exception as exc:
                                st.error(
                                    f"Unable to update schedule: {exc}"
                                )

                    st.divider()
                    st.markdown("**Delete Selected Schedule**")

                    confirm_schedule_delete = st.checkbox(
                        (
                            f"I confirm deletion of schedule "
                            f"{selected_schedule_id}."
                        ),
                        key=f"confirm_schedule_delete_{selected_schedule_id}",
                    )

                    if st.button(
                        "Delete Schedule",
                        key="delete_bus_schedule_button",
                        type="primary",
                    ):
                        if not confirm_schedule_delete:
                            st.error(
                                "Confirm the schedule deletion before proceeding."
                            )
                        else:
                            try:
                                result = bus_operations.delete_schedule(
                                    selected_schedule_id
                                )
                                st.success(result)
                                st.rerun()
                            except Exception as exc:
                                st.error(
                                    f"Unable to delete schedule: {exc}"
                                )
                else:
                    st.info("No bus schedules have been added yet.")

        except Exception as exc:
            st.error(f"Unable to manage bus schedules: {exc}")

        # REGISTER BUS

        st.divider()
        st.subheader("Register a Bus")

        with st.form("register_bus_form"):
            new_bus_id = st.text_input(
                "Bus ID",
                key="register_bus_id",
                placeholder="e.g. BUS103",
            )
            new_bus_type = st.selectbox(
                "Bus Type",
                ["STANDARD", "MINIBUS", "EXPRESS"],
                key="register_bus_type",
            )
            register_bus = st.form_submit_button("Register Bus")

        if register_bus:
            if not new_bus_id.strip():
                st.error("Please enter a Bus ID.")
            else:
                try:
                    with get_connection() as conn:
                        conn.execute(
                            """
                            INSERT INTO buses
                            (bus_id, bus_type, status)
                            VALUES (?, ?, 'AVAILABLE')
                            """,
                            (new_bus_id.strip().upper(), new_bus_type),
                        )
                    st.success(
                        f"Bus {new_bus_id.strip().upper()} registered successfully."
                    )
                    st.rerun()
                except Exception as exc:
                    if "UNIQUE constraint failed" in str(exc):
                        st.error("A bus with this ID already exists.")
                    else:
                        st.error(f"Unable to register bus: {exc}")

        # REGISTER DRIVER

        st.divider()
        st.subheader("Register a Driver")

        with st.form("register_driver_form"):
            new_driver_id = st.text_input(
                "Driver ID",
                key="register_driver_id",
                placeholder="e.g. D57",
            )
            new_driver_name = st.text_input(
                "Driver Name",
                key="register_driver_name",
            )
            licence_expiry = st.date_input(
                "Licence Expiry Date",
                min_value=date.today(),
                key="register_driver_licence_expiry",
            )
            licensed_bus_type = st.selectbox(
                "Licensed Bus Type",
                ["STANDARD", "MINIBUS", "EXPRESS"],
                key="register_driver_bus_type",
            )
            register_driver = st.form_submit_button("Register Driver")

        if register_driver:
            if not new_driver_id.strip() or not new_driver_name.strip():
                st.error("Please enter both the Driver ID and Driver Name.")
            else:
                try:
                    with get_connection() as conn:
                        conn.execute(
                            """
                            INSERT INTO drivers
                            (
                                driver_id,
                                driver_name,
                                licence_expiry,
                                licensed_bus_type,
                                active
                            )
                            VALUES (?, ?, ?, ?, 1)
                            """,
                            (
                                new_driver_id.strip().upper(),
                                new_driver_name.strip(),
                                licence_expiry.isoformat(),
                                licensed_bus_type,
                            ),
                        )
                    st.success(
                        f"Driver {new_driver_name.strip()} registered successfully."
                    )
                    st.rerun()
                except Exception as exc:
                    if "UNIQUE constraint failed" in str(exc):
                        st.error("A driver with this ID already exists.")
                    else:
                        st.error(f"Unable to register driver: {exc}")

        # REGISTERED BUSES AND DRIVERS

        st.divider()
        st.subheader("Registered Buses and Drivers")

        with get_connection() as conn:
            registered_buses = conn.execute(
                """
                SELECT
                    bus_id,
                    bus_type,
                    status,
                    current_route_id
                FROM buses
                ORDER BY bus_id
                """
            ).fetchall()
            registered_drivers = conn.execute(
                """
                SELECT
                    driver_id,
                    driver_name,
                    licence_expiry,
                    licensed_bus_type,
                    active
                FROM drivers
                ORDER BY driver_id
                """
            ).fetchall()

        st.markdown("**Buses**")
        st.dataframe(
            rows_as_dicts(registered_buses),
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("**Drivers**")
        st.dataframe(
            rows_as_dicts(registered_drivers),
            use_container_width=True,
            hide_index=True,
        )

        # CONFIGURE ROUTE FARES

        st.divider()
        st.subheader("Configure Route Fares")

        try:
            with get_connection() as conn:
                fare_routes = conn.execute(
                    """
                    SELECT
                        route_id,
                        route_name,
                        origin,
                        destination,
                        fare_amount
                    FROM routes
                    WHERE status = 'Active'
                    ORDER BY route_name
                    """
                ).fetchall()

            if fare_routes:
                fare_route_options = {
                    (
                        f"{route['route_name']} "
                        f"({route['origin']} to {route['destination']})"
                    ): route["route_id"]
                    for route in fare_routes
                }
                selected_admin_fare_route = st.selectbox(
                    "Select route to configure",
                    list(fare_route_options.keys()),
                    key="admin_fare_route",
                )
                selected_admin_route = next(
                    route for route in fare_routes
                    if route["route_id"]
                    == fare_route_options[selected_admin_fare_route]
                )

                with st.form("configure_route_fare_form"):
                    configured_fare = st.number_input(
                        "Fare amount (JMD)",
                        min_value=0.01,
                        value=max(
                            0.01,
                            float(selected_admin_route["fare_amount"] or 0.0),
                        ),
                        step=10.0,
                        format="%.2f",
                    )
                    save_fare = st.form_submit_button("Save Route Fare")

                if save_fare:
                    with get_connection() as conn:
                        conn.execute(
                            """
                            UPDATE routes
                            SET fare_amount = ?
                            WHERE route_id = ?
                            """,
                            (
                                float(configured_fare),
                                selected_admin_route["route_id"],
                            ),
                        )
                    st.success("Route fare updated.")
                    st.rerun()
            else:
                st.info("There are no active routes to configure.")
        except Exception as exc:
            st.error(f"Unable to configure route fares: {exc}")

        # ASSIGN BUS, ROUTE AND DRIVER

        st.divider()
        st.subheader("Assign a Bus, Route and Driver")

        with st.form("assign_bus_form"):
            assignment_route = st.text_input("Route ID", key="assign_route")
            assignment_driver = st.text_input("Driver ID", key="assign_driver")
            assignment_bus = st.text_input("Bus ID", key="assign_bus_id")
            assignment_date = st.date_input(
                "Service Date",
                min_value=date.today(),
            )
            shift_start = st.text_input("Shift Start (HH:MM)", value="07:00")
            shift_end = st.text_input("Shift End (HH:MM)", value="15:00")
            save_assignment = st.form_submit_button("Save Assignment")

        if save_assignment:
            try:
                result = route_scheduling.assign_route_driver(
                    assignment_route,
                    assignment_driver,
                    assignment_bus,
                    assignment_date.isoformat(),
                    shift_start,
                    shift_end,
                )
                st.success(result)
            except Exception as exc:
                st.error(str(exc))


        # MANAGE EXISTING ASSIGNMENTS

        st.divider()
        st.subheader("Manage Existing Assignments")

        try:
            with get_connection() as conn:
                assignments = conn.execute(
                    """
                    SELECT
                        a.assignment_id,
                        a.route_id,
                        r.route_name,
                        a.driver_id,
                        d.driver_name,
                        a.bus_id,
                        a.service_date,
                        a.shift_start,
                        a.shift_end,
                        a.status
                    FROM assignments a
                    LEFT JOIN routes r
                        ON a.route_id = r.route_id
                    LEFT JOIN drivers d
                        ON a.driver_id = d.driver_id
                    ORDER BY a.service_date DESC,
                             a.assignment_id DESC
                    """
                ).fetchall()

            if assignments:
                assignment_data = rows_as_dicts(assignments)

                st.dataframe(
                    assignment_data,
                    use_container_width=True,
                    hide_index=True,
                )

                active_assignments = [
                    assignment for assignment in assignment_data
                    if assignment["status"].upper()
                    in ("ASSIGNED", "ACTIVE", "IN_SERVICE")
                ]

                if active_assignments:
                    assignment_options = {
                        (
                            f"Assignment {assignment['assignment_id']} — "
                            f"Route {assignment['route_id']} — "
                            f"Driver {assignment['driver_id']} — "
                            f"Bus {assignment['bus_id']} — "
                            f"{assignment['service_date']}"
                        ): assignment["assignment_id"]
                        for assignment in active_assignments
                    }

                    selected_assignment_label = st.selectbox(
                        "Select Assignment to Deactivate",
                        list(assignment_options.keys()),
                        key="deactivate_assignment_selection",
                    )

                    selected_assignment_id = assignment_options[
                        selected_assignment_label
                    ]

                    confirm_deactivation = st.checkbox(
                        (
                            f"I confirm that assignment "
                            f"{selected_assignment_id} should be deactivated."
                        ),
                        key=f"confirm_deactivation_{selected_assignment_id}",
                    )

                    if st.button(
                        "Deactivate Selected Assignment",
                        key="deactivate_assignment_button",
                        type="primary",
                    ):
                        if not confirm_deactivation:
                            st.warning(
                                "Please confirm before deactivating "
                                "the assignment."
                            )
                        else:
                            try:
                                result = (
                                    route_scheduling.deactivate_assignment(
                                        selected_assignment_id,
                                        user["username"],
                                    )
                                )
                                st.success(result)
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                else:
                    st.info("There are no active assignments to deactivate.")

            else:
                st.info("No assignments have been created yet.")

        except Exception as exc:
            st.error(f"Unable to manage assignments: {exc}")

        # ADD ROUTE

        st.divider()
        st.subheader("Add Route")

        with st.form("add_route_form"):
            new_route_id = st.text_input("New Route ID")
            route_name = st.text_input("Route Name")
            origin = st.text_input("Origin")
            destination = st.text_input("Destination")
            distance = st.number_input(
                "Distance (km)",
                min_value=0.1,
                value=1.0,
            )
            duration = st.number_input(
                "Duration (minutes)",
                min_value=1,
                value=30,
            )
            add_route = st.form_submit_button("Add Route")

        if add_route:
            try:
                route_scheduling.add_route(
                    new_route_id,
                    route_name,
                    origin,
                    destination,
                    distance,
                    duration,
                    0.0,
                )
                st.success("Route added.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        # ------------------------------------------
        # DELETE BUSES, DRIVERS AND ROUTES
        # ------------------------------------------

        st.divider()
        st.subheader("Delete System Records")
        st.warning(
            "These actions permanently delete the selected records "
            "and associated operational information."
        )

        # DELETE BUS

        st.markdown("**Delete a Bus**")

        with get_connection() as conn:
            bus_records = conn.execute(
                """
                SELECT bus_id
                FROM buses
                ORDER BY bus_id
                """
            ).fetchall()

        if bus_records:
            bus_ids = [row["bus_id"] for row in bus_records]
            selected_bus_delete = st.selectbox(
                "Select Bus ID to delete",
                bus_ids,
                key="delete_bus_selection",
            )
            confirm_bus_delete = st.checkbox(
                f"I confirm deletion of bus {selected_bus_delete}.",
                key=f"confirm_bus_delete_{selected_bus_delete}",
            )

            if st.button(
                "Delete Selected Bus",
                key="delete_bus_button",
                type="primary",
            ):
                if not confirm_bus_delete:
                    st.error("Confirm the bus deletion before proceeding.")
                else:
                    try:
                        result = route_scheduling.delete_bus(
                            selected_bus_delete,
                            user["username"],
                        )
                        st.success(result)
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
        else:
            st.info("There are no buses to delete.")

        st.divider()

        # DELETE DRIVER

        st.markdown("**Delete a Driver**")

        with get_connection() as conn:
            driver_records = conn.execute(
                """
                SELECT driver_id, driver_name
                FROM drivers
                ORDER BY driver_id
                """
            ).fetchall()

        if driver_records:
            driver_options = {
                f"{row['driver_id']} — {row['driver_name']}":
                row["driver_id"]
                for row in driver_records
            }
            selected_driver_delete = st.selectbox(
                "Select Driver to delete",
                list(driver_options.keys()),
                key="delete_driver_selection",
            )
            selected_driver_id = driver_options[selected_driver_delete]
            confirm_driver_delete = st.checkbox(
                f"I confirm deletion of driver {selected_driver_id}.",
                key=f"confirm_driver_delete_{selected_driver_id}",
            )

            if st.button(
                "Delete Selected Driver",
                key="delete_driver_button",
                type="primary",
            ):
                if not confirm_driver_delete:
                    st.error("Confirm the driver deletion before proceeding.")
                else:
                    try:
                        result = route_scheduling.delete_driver(
                            selected_driver_id,
                            user["username"],
                        )
                        st.success(result)
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
        else:
            st.info("There are no drivers to delete.")

        st.divider()

        # DELETE ROUTE

        st.markdown("**Delete a Route**")

        with get_connection() as conn:
            route_records = conn.execute(
                """
                SELECT route_id, route_name
                FROM routes
                ORDER BY route_id
                """
            ).fetchall()

        if route_records:
            route_delete_options = {
                f"{row['route_id']} — {row['route_name']}":
                row["route_id"]
                for row in route_records
            }
            selected_route_delete = st.selectbox(
                "Select Route to delete",
                list(route_delete_options.keys()),
                key="delete_route_selection",
            )
            selected_route_id = route_delete_options[selected_route_delete]
            confirm_route_delete = st.checkbox(
                f"I confirm deletion of route {selected_route_id}.",
                key=f"confirm_route_delete_{selected_route_id}",
            )

            if st.button(
                "Delete Selected Route",
                key="delete_route_button",
                type="primary",
            ):
                if not confirm_route_delete:
                    st.error("Confirm the route deletion before proceeding.")
                else:
                    try:
                        result = route_scheduling.delete_route(
                            selected_route_id,
                            user["username"],
                        )
                        st.success(result)
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
        else:
            st.info("There are no routes to delete.")

    # ----------------------------------------------
    # DELAY REPORTS
    # ----------------------------------------------

    with delays_tab:
        st.subheader("Report a Delay")

        with st.form("delay_report_form"):
            delay_bus = st.text_input("Bus ID", key="delay_bus")
            delay_reason = st.text_input("Delay Reason")
            delay_minutes = st.number_input(
                "Delay Duration (minutes)",
                min_value=0,
                step=1,
            )
            submit_delay = st.form_submit_button("Submit Delay Report")

        if submit_delay:
            try:
                result = bus_operations.report_delay(
                    delay_bus,
                    delay_reason,
                    delay_minutes,
                )
                st.success(result)
            except Exception as exc:
                st.error(str(exc))

        st.divider()
        st.subheader("Recorded Delay Reports")

        with get_connection() as conn:
            delays = conn.execute(
                """
                SELECT *
                FROM delay_reports
                ORDER BY reported_at DESC
                """
            ).fetchall()

        st.dataframe(
            rows_as_dicts(delays),
            use_container_width=True,
            hide_index=True,
        )

    # ----------------------------------------------
    # REVENUE MANAGEMENT
    # ----------------------------------------------

    with revenue_tab:
        st.subheader("Passenger Bus Card Transactions and Receipts")

        with get_connection() as conn:
            all_transactions = conn.execute(
                """
                SELECT
                    transaction_id,
                    transaction_date,
                    transaction_time,
                    route_id,
                    fare_amount,
                    payment_method,
                    payment_status,
                    receipt_number,
                    commuter_id
                FROM fare_transactions
                WHERE payment_method IN (
                    'Bus Card',
                    'Virtual Bus Card'
                )
                ORDER BY transaction_date DESC,
                         transaction_time DESC
                LIMIT 500
                """
            ).fetchall()

        st.dataframe(
            rows_as_dicts(all_transactions),
            use_container_width=True,
            hide_index=True,
        )

        if all_transactions:
            receipt_options = {
                f"Transaction {row['transaction_id']}":
                row["transaction_id"]
                for row in all_transactions
            }
            selected_receipt = st.selectbox(
                "Select passenger receipt",
                list(receipt_options.keys()),
            )

            with get_connection() as conn:
                receipt_row = conn.execute(
                    """
                    SELECT receipt_text
                    FROM receipts
                    WHERE transaction_id = ?
                    """,
                    (receipt_options[selected_receipt],),
                ).fetchone()

            if receipt_row:
                st.code(receipt_row["receipt_text"])

        st.divider()
        st.subheader("Daily Card Settlement and Reconciliation")

        with st.form("daily_collection_form"):
            collection_date = st.date_input(
                "Settlement Date",
                value=date.today(),
            )
            settlement_amount = st.number_input(
                "Card Settlement Amount (JMD)",
                min_value=0.0,
                step=100.0,
            )
            submit_collection = st.form_submit_button(
                "Submit Card Settlement"
            )

        if submit_collection:
            try:
                revenue.submit_daily_collection(
                    collection_date.isoformat(),
                    settlement_amount,
                    user["username"],
                )
                st.success("Daily card settlement submitted.")
            except Exception as exc:
                st.error(str(exc))

        if st.button("Reconcile Selected Date"):
            try:
                result = revenue.reconcile_revenue(
                    collection_date.isoformat()
                )
                st.json(result)
            except Exception as exc:
                st.error(str(exc))

        st.divider()
        st.subheader("Revenue Report")

        report_start = st.date_input(
            "Report Start Date",
            value=date.today(),
            key="report_start",
        )
        report_end = st.date_input(
            "Report End Date",
            value=date.today(),
            key="report_end",
        )

        if st.button("Generate Revenue Report"):
            if report_start > report_end:
                st.error(
                    "The report start date cannot be after the end date."
                )
            else:
                try:
                    transactions, reconciliations, ledger = (
                        revenue.revenue_report(
                            report_start.isoformat(),
                            report_end.isoformat(),
                        )
                    )
                    st.markdown("**Fare Totals**")
                    st.dataframe(
                        rows_as_dicts(transactions),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.markdown("**Reconciliations**")
                    st.dataframe(
                        rows_as_dicts(reconciliations),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.markdown("**Revenue Ledger**")
                    st.dataframe(
                        rows_as_dicts(ledger),
                        use_container_width=True,
                        hide_index=True,
                    )
                except Exception as exc:
                    st.error(str(exc))


# --------------------------------------------------
# MAIN ADMINISTRATOR DASHBOARD
# --------------------------------------------------

def main_admin_dashboard(user):
    require_main_admin(user["user_id"])
    admin_dashboard(user)

    st.divider()
    st.title("Main Administrator Controls")
    st.caption(
        "Only the Main Administrator can grant or revoke "
        "Administrator privileges."
    )

    try:
        accounts = rows_as_dicts(
            user_management.list_users(user["user_id"])
        )
    except Exception as exc:
        st.error(f"Unable to retrieve user accounts: {exc}")
        return

    st.subheader("User Accounts")
    st.dataframe(
        accounts,
        use_container_width=True,
        hide_index=True,
    )

    eligible_accounts = [
        account
        for account in accounts
        if account["role"] != "MAIN_ADMIN"
    ]

    if eligible_accounts:
        account_options = {
            (
                f"{account['username']} — {account['role']} "
                f"(ID {account['user_id']})"
            ): account["user_id"]
            for account in eligible_accounts
        }
        selected_account = st.selectbox(
            "Select Account",
            list(account_options.keys()),
        )

        with st.form("role_change_form"):
            new_role = st.selectbox(
                "Set Role",
                ["ADMIN", "COMMUTER"],
            )
            confirm_change = st.checkbox(
                "I confirm this account role change."
            )
            save_role = st.form_submit_button("Update Role")

        if save_role:
            if not confirm_change:
                st.warning("Confirm the role change before proceeding.")
            else:
                try:
                    user_management.change_user_role(
                        user["user_id"],
                        account_options[selected_account],
                        new_role,
                    )
                    st.success("Account role updated.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    else:
        st.info("There are no eligible accounts to update.")

    st.divider()
    st.subheader("Role-Change Audit Log")

    try:
        audit_records = user_management.role_audit_log(user["user_id"])
        st.dataframe(
            rows_as_dicts(audit_records),
            use_container_width=True,
            hide_index=True,
        )
    except Exception as exc:
        st.error(f"Unable to retrieve the role-change audit log: {exc}")


# --------------------------------------------------
# APPLICATION ENTRY POINT
# --------------------------------------------------

if st.session_state.user is None:
    login_screen()
else:
    user = st.session_state.user

    with get_connection() as conn:
        current_user_record = conn.execute(
            """
            SELECT
                user_id,
                username,
                email,
                role,
                is_active
            FROM users
            WHERE user_id = ?
            """,
            (user["user_id"],)
        ).fetchone()

    if not current_user_record or not current_user_record["is_active"]:
        st.session_state.user = None
        st.error("This account is unavailable. Please sign in again.")
        st.rerun()

    current_user = dict(current_user_record)
    st.sidebar.image(str(APP_DIR / "assets" / "jutc-logo.svg"), width=180)
    st.sidebar.title("Smart JUTC")
    st.sidebar.write(f"**{current_user['username']}**")
    st.sidebar.caption(current_user["role"].replace("_", " "))

    if st.sidebar.button("Sign Out", use_container_width=True):
        logout()

    if current_user["role"] == "MAIN_ADMIN":
        main_admin_dashboard(current_user)
    elif current_user["role"] == "ADMIN":
        admin_dashboard(current_user)
    else:
        commuter_dashboard(current_user)
