
from datetime import date

from .database import get_connection
from .utils import now_iso, log_event
from .fare_management import list_transactions


CARD_PAYMENT_METHODS = (
    "Bus Card",
    "Virtual Bus Card"
)


def _validate_date(value, field_name):
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{field_name} must use YYYY-MM-DD format."
        )


def submit_daily_collection(
    collection_date,
    submitted_amount,
    submitted_by
):
    _validate_date(collection_date, "Collection date")

    try:
        amount = round(float(submitted_amount), 2)
    except (TypeError, ValueError):
        raise ValueError("Submitted collection must be numeric.")

    if amount < 0:
        raise ValueError("Submitted collection cannot be negative.")

    if not submitted_by or not str(submitted_by).strip():
        raise ValueError("The submitter is required.")

    submitted_by = str(submitted_by).strip()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO daily_collections
            (
                collection_date,
                submitted_amount,
                submitted_by,
                submitted_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(collection_date) DO UPDATE SET
                submitted_amount = excluded.submitted_amount,
                submitted_by = excluded.submitted_by,
                submitted_at = excluded.submitted_at
            """,
            (
                collection_date,
                amount,
                submitted_by,
                now_iso()
            )
        )

        conn.execute(
            """
            DELETE FROM revenue_ledger
            WHERE entry_date = ?
              AND entry_type = 'COLLECTION_SUBMITTED'
            """,
            (collection_date,)
        )

        conn.execute(
            """
            INSERT INTO revenue_ledger
            (
                entry_date,
                entry_type,
                amount,
                description,
                reference
            )
            VALUES (
                ?,
                'COLLECTION_SUBMITTED',
                ?,
                'Daily bus-card settlement submitted',
                ?
            )
            """,
            (
                collection_date,
                amount,
                submitted_by
            )
        )

        log_event(
            conn,
            "DAILY CARD SETTLEMENT SUBMITTED",
            f"{collection_date}: JMD ${amount:.2f}",
            submitted_by
        )


def reconcile_revenue(collection_date):
    _validate_date(collection_date, "Reconciliation date")

    transactions = list_transactions(
        collection_date,
        collection_date
    )

    recorded_total = round(
        sum(
            float(row["fare_amount"])
            for row in transactions
            if row["payment_method"] in CARD_PAYMENT_METHODS
        ),
        2
    )

    with get_connection() as conn:
        submitted = conn.execute(
            """
            SELECT *
            FROM daily_collections
            WHERE collection_date = ?
            """,
            (collection_date,)
        ).fetchone()

        if not submitted:
            raise ValueError(
                "No daily card settlement has been submitted for this date."
            )

        submitted_total = round(
            float(submitted["submitted_amount"]),
            2
        )

        variance = round(
            submitted_total - recorded_total,
            2
        )

        result = (
            "RECONCILED"
            if variance == 0
            else "VARIANCE FOUND"
        )

        conn.execute(
            """
            INSERT INTO reconciliation
            (
                reconciliation_date,
                recorded_total,
                submitted_total,
                variance,
                result,
                reconciled_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(reconciliation_date) DO UPDATE SET
                recorded_total = excluded.recorded_total,
                submitted_total = excluded.submitted_total,
                variance = excluded.variance,
                result = excluded.result,
                reconciled_at = excluded.reconciled_at
            """,
            (
                collection_date,
                recorded_total,
                submitted_total,
                variance,
                result,
                now_iso()
            )
        )

        conn.execute(
            """
            DELETE FROM revenue_ledger
            WHERE entry_date = ?
              AND entry_type = 'RECONCILIATION'
            """,
            (collection_date,)
        )

        conn.execute(
            """
            INSERT INTO revenue_ledger
            (
                entry_date,
                entry_type,
                amount,
                description,
                reference
            )
            VALUES (?, 'RECONCILIATION', ?, ?, ?)
            """,
            (
                collection_date,
                variance,
                f"Card revenue reconciliation: {result}",
                collection_date
            )
        )

        log_event(
            conn,
            "REVENUE RECONCILED",
            (
                f"{collection_date}: recorded JMD ${recorded_total:.2f}, "
                f"submitted JMD ${submitted_total:.2f}, "
                f"variance JMD ${variance:.2f}"
            )
        )

    return {
        "date": collection_date,
        "recorded_total": recorded_total,
        "submitted_total": submitted_total,
        "variance": variance,
        "result": result
    }


def revenue_report(start_date, end_date):
    _validate_date(start_date, "Start date")
    _validate_date(end_date, "End date")

    if start_date > end_date:
        raise ValueError(
            "Start date cannot be later than end date."
        )

    with get_connection() as conn:
        transactions = conn.execute(
            """
            SELECT
                transaction_date,
                payment_method,
                COUNT(*) AS transaction_count,
                SUM(fare_amount) AS total
            FROM fare_transactions
            WHERE payment_status = 'Successful'
              AND payment_method IN (
                  'Bus Card',
                  'Virtual Bus Card'
              )
              AND transaction_date BETWEEN ? AND ?
            GROUP BY transaction_date, payment_method
            ORDER BY transaction_date, payment_method
            """,
            (start_date, end_date)
        ).fetchall()

        reconciliations = conn.execute(
            """
            SELECT *
            FROM reconciliation
            WHERE reconciliation_date BETWEEN ? AND ?
            ORDER BY reconciliation_date
            """,
            (start_date, end_date)
        ).fetchall()

        ledger = conn.execute(
            """
            SELECT *
            FROM revenue_ledger
            WHERE entry_date BETWEEN ? AND ?
            ORDER BY entry_date, ledger_id
            """,
            (start_date, end_date)
        ).fetchall()

    return transactions, reconciliations, ledger
