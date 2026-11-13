"""Main Administrator account and role management."""

from .database import get_connection
from .permissions import require_main_admin
from .utils import now_iso, log_event


def list_users(actor_id):
    require_main_admin(actor_id)

    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                user_id,
                username,
                email,
                role,
                created_at,
                is_active
            FROM users
            ORDER BY user_id
            """
        ).fetchall()


def change_user_role(actor_id, target_user_id, new_role):
    require_main_admin(actor_id)

    if new_role not in {"ADMIN", "COMMUTER"}:
        raise ValueError(
            "The Main Administrator role cannot be assigned or changed here."
        )

    with get_connection() as conn:

        target = conn.execute(
            """
            SELECT user_id, role, username
            FROM users
            WHERE user_id = ? AND is_active = 1
            """,
            (target_user_id,)
        ).fetchone()

        if not target:
            raise ValueError("Account not found or inactive.")

        if target["role"] == "MAIN_ADMIN":
            raise ValueError(
                "The Main Administrator account cannot be changed here."
            )

        old_role = target["role"]

        if old_role == new_role:
            return

        conn.execute(
            """
            UPDATE users
            SET role = ?
            WHERE user_id = ?
            """,
            (new_role, target_user_id)
        )

        conn.execute(
            """
            INSERT INTO role_audit
            (
                target_user_id,
                old_role,
                new_role,
                changed_by,
                changed_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                target_user_id,
                old_role,
                new_role,
                actor_id,
                now_iso()
            )
        )

        log_event(
            conn,
            "USER ROLE CHANGED",
            f"{target['username']}: {old_role} -> {new_role}",
            str(actor_id)
        )


def role_audit_log(actor_id):
    require_main_admin(actor_id)

    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                a.audit_id,
                u.username AS account,
                a.old_role,
                a.new_role,
                actor.username AS changed_by,
                a.changed_at
            FROM role_audit a
            JOIN users u
                ON u.user_id = a.target_user_id
            JOIN users actor
                ON actor.user_id = a.changed_by
            ORDER BY a.changed_at DESC
            """
        ).fetchall()


def delete_commuter_account(commuter_id):
    """Delete a commuter account and its associated card and payment records."""

    with get_connection() as conn:

        commuter = conn.execute(
            """
            SELECT user_id, username, role
            FROM users
            WHERE user_id = ?
            """,
            (commuter_id,)
        ).fetchone()

        if not commuter:
            raise ValueError("Commuter account was not found.")

        if commuter["role"] != "COMMUTER":
            raise ValueError(
                "Only commuter accounts can be deleted using this function."
            )

        transaction_ids = conn.execute(
            """
            SELECT transaction_id
            FROM fare_transactions
            WHERE commuter_id = ?
            """,
            (commuter_id,)
        ).fetchall()

        for transaction in transaction_ids:
            conn.execute(
                """
                DELETE FROM receipts
                WHERE transaction_id = ?
                """,
                (transaction["transaction_id"],)
            )

        conn.execute(
            """
            DELETE FROM fare_transactions
            WHERE commuter_id = ?
            """,
            (commuter_id,)
        )

        conn.execute(
            """
            DELETE FROM bus_cards
            WHERE commuter_id = ?
            """,
            (commuter_id,)
        )

        conn.execute(
            """
            DELETE FROM role_audit
            WHERE target_user_id = ?
               OR changed_by = ?
            """,
            (commuter_id, commuter_id)
        )

        log_event(
            conn,
            "COMMUTER ACCOUNT DELETED",
            f"Commuter account {commuter['username']} was deleted.",
            str(commuter_id)
        )

        conn.execute(
            """
            DELETE FROM users
            WHERE user_id = ?
            """,
            (commuter_id,)
        )

    return "Your commuter account and associated records have been deleted."