
from datetime import date, timedelta
from . import route_scheduling as routes
from . import bus_operations as operations
from . import fare_management as fares
from . import revenue


def ask(prompt):
    return input(prompt).strip()


def show_rows(rows):
    if not rows:
        print("No records found.")
        return
    for row in rows:
        print(dict(row))


def route_menu():
    while True:
        print("\n--- 1.0 ROUTE SCHEDULING & DISPATCH ---")
        print("1. Assign route and driver")
        print("2. Log driver assignment")
        print("3. Maintain route and schedule logbook")
        print("0. Back")
        choice = ask("Select: ")
        try:
            if choice == "1":
                assignment_id = routes.assign_route_driver(
                    ask("Route ID: "), ask("Driver ID: "), ask("Bus ID: "),
                    ask("Service date (YYYY-MM-DD): "), ask("Shift start (HH:MM): "),
                    ask("Shift end (HH:MM): "), ask("Performed by: ") or "DISPATCH")
                print(f"Assignment saved. Assignment ID: {assignment_id}")
            elif choice == "2":
                routes.log_driver_assignment(
                    ask("Action: "), ask("Details: "), ask("Performed by: "))
                print("Action logged.")
            elif choice == "3":
                maintain_routes_menu()
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except Exception as exc:
            print(f"Error: {exc}")


def maintain_routes_menu():
    while True:
        print("\n--- ROUTE & SCHEDULE LOGBOOK ---")
        print("1. Add route  2. Update route  3. Deactivate route")
        print("4. View routes  5. Search logbook  0. Back")
        choice = ask("Select: ")
        try:
            if choice == "1":
                routes.add_route(
                    ask("Route ID: "), ask("Route name: "), ask("Origin: "),
                    ask("Destination: "), ask("Distance (km): "),
                    ask("Duration (minutes): "), ask("Frequency (minutes): "))
                print("Route added.")
            elif choice == "2":
                routes.update_route(
                    ask("Route ID: "), ask("Route name: "), ask("Origin: "),
                    ask("Destination: "), ask("Distance (km): "),
                    ask("Duration (minutes): "), ask("Frequency (minutes): "))
                print("Route updated.")
            elif choice == "3":
                route_id = ask("Route ID: ")
                confirmed = ask("Confirm deactivation? (y/n): ").lower() == "y"
                print(
                    "Route deactivated."
                    if routes.deactivate_route(route_id, confirmed)
                    else "No changes made."
                )
            elif choice == "4":
                show_rows(routes.list_routes())
            elif choice == "5":
                show_rows(routes.search_logbook(
                    ask("Start date (YYYY-MM-DD, optional): ") or None,
                    ask("End date (YYYY-MM-DD, optional): ") or None,
                    ask("Route ID (optional): ") or None,
                    ask("Driver ID (optional): ") or None))
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except Exception as exc:
            print(f"Error: {exc}")


def bus_operations_menu():
    while True:
        print("\n--- 2.0 BUS OPERATIONS & STATUS TRACKING ---")
        print("1. Operate bus on route")
        print("2. Report delays via radio")
        print("3. Track bus location and status")
        print("4. Send service status update")
        print("5. End bus service")
        print("0. Back")
        choice = ask("Select: ")
        try:
            if choice == "1":
                print(operations.operate_bus_on_route(
                    ask("Bus ID: "), ask("Route ID: "), ask("Driver ID: ")))
            elif choice == "2":
                print(operations.report_delay(
                    ask("Bus ID: "), ask("Delay reason: "),
                    ask("Delay minutes: "), ask("Latitude (optional): ") or None,
                    ask("Longitude (optional): ") or None))
            elif choice == "3":
                print(operations.track_bus_location(
                    ask("Bus ID: "), ask("Latitude: "),
                    ask("Longitude: "), ask("Speed: "),
                    ask("Status (ON_TIME/DELAYED/OFF_ROUTE/STOPPED): ").upper()))
            elif choice == "4":
                print("Service status update prepared for control centre and passenger app:")
                print(operations.send_service_status_update(ask("Bus ID: ")))
            elif choice == "5":
                operations.stop_bus(ask("Bus ID: "))
                print("Bus service ended.")
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except Exception as exc:
            print(f"Error: {exc}")


def passenger_fare_menu():
    while True:
        print("\n--- 3.0 PASSENGER FARE COLLECTION ---")
        print("1. Check bus schedule")
        print("2. Record bus card transaction")
        print("0. Back")
        choice = ask("Select: ")
        try:
            if choice == "1":
                route_id = ask("Route ID: ")
                travel_date = ask("Travel date (YYYY-MM-DD): ")
                rows = fares.check_bus_schedule(route_id, travel_date)
                if not rows:
                    print("No buses are available for this route and date.")
                else:
                    print("BUS SCHEDULE")
                    for row in rows:
                        print(
                            f"{row['route_name']} | "
                            f"{row['departure_time']} - "
                            f"{row['arrival_time']} | "
                            f"Stops: {row['bus_stops']}"
                        )

            elif choice == "2":
                route_id = ask("Route ID: ")
                fare_amount = ask("Required fare (JMD): ")
                card_id = ask("Bus card ID: ")

                payment = fares.pay_fare(
                    fare_amount,
                    card_id=card_id
                )

                transaction = fares.complete_fare_transaction(
                    route_id, payment
                )

                receipt = fares.issue_payment_receipt(
                    transaction, payment, route_id
                )

                print(receipt)
                print(f"Transaction ID: {transaction['transaction_id']}")

            elif choice == "0":
                return
            else:
                print("Invalid choice.")

        except Exception as exc:
            print(f"Error: {exc}")


def revenue_menu():
    while True:
        print("\n--- 4.0 REVENUE RECONCILIATION & REPORTING ---")
        print("1. Submit daily fare collection")
        print("2. Reconcile revenue")
        print("3. View revenue ledger")
        print("4. Generate revenue and service report")
        print("0. Back")
        choice = ask("Select: ")
        try:
            if choice == "1":
                revenue.submit_daily_collection(
                    ask("Collection date (YYYY-MM-DD): "),
                    ask("Submitted amount (JMD): "),
                    ask("Submitted by: "))
                print("Daily fare collection submitted.")
            elif choice == "2":
                result = revenue.reconcile_revenue(
                    ask("Reconciliation date (YYYY-MM-DD): "))
                print(result)
            elif choice == "3":
                start = ask("Start date (YYYY-MM-DD): ")
                end = ask("End date (YYYY-MM-DD): ")
                _, _, ledger = revenue.revenue_report(start, end)
                show_rows(ledger)
            elif choice == "4":
                start = ask("Start date (YYYY-MM-DD): ")
                end = ask("End date (YYYY-MM-DD): ")
                transactions, reconciliations, ledger = revenue.revenue_report(
                    start, end
                )
                print("\nFare totals by date and payment method:")
                show_rows(transactions)
                print("\nReconciliation results:")
                show_rows(reconciliations)
                print("\nRevenue ledger:")
                show_rows(ledger)
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except Exception as exc:
            print(f"Error: {exc}")


def run_application():
    print("=" * 58)
    print(" SMART JUTC BUS TRACKING & DIGITAL FARE MANAGEMENT SYSTEM")
    print("=" * 58)

    while True:
        print("\nMAIN MENU")
        print("1.0 Route Scheduling & Dispatch")
        print("2.0 Bus Operations & Status Tracking")
        print("3.0 Passenger Fare Collection")
        print("4.0 Revenue Reconciliation & Reporting")
        print("0. Exit")

        choice = ask("Select a module: ")

        if choice == "1":
            route_menu()
        elif choice == "2":
            bus_operations_menu()
        elif choice == "3":
            passenger_fare_menu()
        elif choice == "4":
            revenue_menu()
        elif choice == "0":
            print("Thank you for using the Smart JUTC System.")
            break
        else:
            print("Invalid choice. Select 0-4.")
