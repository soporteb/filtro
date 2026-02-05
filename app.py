from __future__ import annotations

import os
import secrets
import sqlite3
import hashlib
import csv
import io
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import datetime, timezone, timedelta
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "support.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key"


DEFAULT_TECHNICIANS = [
    {"name": "Laura Gomez", "email": "laura.gomez@miempresa.com", "specialty": "Redes"},
    {"name": "Carlos Perez", "email": "carlos.perez@miempresa.com", "specialty": "Software"},
    {"name": "Ana Rojas", "email": "ana.rojas@miempresa.com", "specialty": "Hardware"},
]


def _get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


try:
    LIMA_TZ = ZoneInfo("America/Lima")
except ZoneInfoNotFoundError:
    LIMA_TZ = timezone(timedelta(hours=-5))


def _now_lima() -> str:
    return datetime.now(LIMA_TZ).isoformat()


def init_db() -> None:
    with _get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                identifier TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                last_login TEXT
            );
            CREATE TABLE IF NOT EXISTS technicians (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                specialty TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_from TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                assigned_to TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                closed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                event TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES tickets(id)
            );
            """
        )
        existing = connection.execute("SELECT COUNT(*) FROM technicians").fetchone()[0]
        if existing == 0:
            connection.executemany(
                """
                INSERT INTO technicians (name, email, specialty, is_active)
                VALUES (?, ?, ?, 1)
                """,
                [
                    (tech["name"], tech["email"], tech["specialty"])
                    for tech in DEFAULT_TECHNICIANS
                ],
            )
        users_existing = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if users_existing == 0:
            admin_identifier = "admin@miempresa.com"
            salt = secrets.token_hex(8)
            password_hash = _hash_password("admin123", salt)
            connection.execute(
                """
                INSERT INTO users (role, identifier, password_hash, salt)
                VALUES (?, ?, ?, ?)
                """,
                ("admin", admin_identifier, password_hash, salt),
            )
        _ensure_user_columns(connection)


def _ensure_user_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "last_login" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN last_login TEXT")


def _get_technicians(active_only: bool = False) -> list[sqlite3.Row]:
    query = "SELECT * FROM technicians"
    params: tuple[Any, ...] = ()
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY name"
    with _get_connection() as connection:
        return connection.execute(query, params).fetchall()


def _create_ticket(email_from: str, subject: str, body: str) -> int:
    created_at = _now_lima()
    with _get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tickets (email_from, subject, body, assigned_to, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (email_from, subject, body, "Sin asignar", "Pendiente", created_at),
        )
        ticket_id = cursor.lastrowid
        connection.execute(
            "INSERT INTO timeline (ticket_id, event, created_at) VALUES (?, ?, ?)",
            (ticket_id, "Ticket creado", created_at),
        )
    return int(ticket_id)


@app.before_request
def enforce_login() -> Any:
    if request.endpoint in {
        "login_home",
        "login_admin",
        "login_dispatcher",
        "login_technician",
        "intake_email",
        "static",
    }:
        return None
    user = _get_user_context()
    if user["role"] == "guest":
        return redirect(url_for("login_home"))
    return None


@app.route("/")
def index() -> str:
    user = _get_user_context()
    technicians = _get_technicians(active_only=True)
    with _get_connection() as connection:
        if user["role"] == "technician" and user["technician_email"]:
            tickets = connection.execute(
                "SELECT * FROM tickets WHERE assigned_to = ? ORDER BY created_at DESC",
                (user["technician_email"],),
            ).fetchall()
        else:
            tickets = connection.execute(
                "SELECT * FROM tickets ORDER BY created_at DESC"
            ).fetchall()
    return render_template(
        "index.html", tickets=tickets, technicians=technicians, user=user
    )


@app.route("/login")
def login_home() -> str:
    return render_template("login_home.html", user=_get_user_context())


@app.route("/login/admin", methods=["GET", "POST"])
def login_admin() -> Any:
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        if _authenticate_user("admin", identifier, password):
            _record_login(identifier)
            session["role"] = "admin"
            session["technician_email"] = ""
            session["user_identifier"] = identifier
            return redirect(url_for("index"))
        return render_template(
            "login_admin.html",
            user=_get_user_context(),
            error="Credenciales inválidas.",
        )
    return render_template("login_admin.html", user=_get_user_context())


@app.route("/login/dispatcher", methods=["GET", "POST"])
def login_dispatcher() -> Any:
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        if _authenticate_user("dispatcher", identifier, password):
            _record_login(identifier)
            session["role"] = "dispatcher"
            session["technician_email"] = ""
            session["user_identifier"] = identifier
            return redirect(url_for("index"))
        return render_template(
            "login_dispatcher.html",
            user=_get_user_context(),
            error="Credenciales inválidas.",
        )
    return render_template("login_dispatcher.html", user=_get_user_context())


@app.route("/login/technician", methods=["GET", "POST"])
def login_technician() -> Any:
    if request.method == "POST":
        technician_email = request.form.get("technician_email", "")
        password = request.form.get("password", "")
        if _authenticate_user("technician", technician_email, password):
            _record_login(technician_email)
            session["role"] = "technician"
            session["technician_email"] = technician_email
            session["user_identifier"] = technician_email
            return redirect(url_for("index"))
        return render_template(
            "login_technician.html",
            technicians=_get_technicians(active_only=True),
            user=_get_user_context(),
            error="Credenciales inválidas.",
        )
    return render_template(
        "login_technician.html",
        technicians=_get_technicians(active_only=True),
        user=_get_user_context(),
    )


@app.route("/logout", methods=["POST"])
def logout() -> Any:
    session.clear()
    return redirect(url_for("login_home"))


@app.route("/tickets", methods=["POST"])
def create_ticket() -> Any:
    email_from = request.form.get("email_from") or "cliente@dominio.com"
    subject = request.form.get("subject") or "Sin asunto"
    body = request.form.get("body") or "Sin detalle"
    ticket_id = _create_ticket(email_from, subject, body)
    return redirect(url_for("ticket_detail", ticket_id=ticket_id))


@app.route("/tickets/<int:ticket_id>")
def ticket_detail(ticket_id: int) -> str:
    with _get_connection() as connection:
        ticket = connection.execute(
            "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        timeline = connection.execute(
            "SELECT * FROM timeline WHERE ticket_id = ? ORDER BY created_at",
            (ticket_id,),
        ).fetchall()
    if not ticket:
        return (
            render_template(
                "ticket_not_found.html",
                ticket_id=ticket_id,
                user=_get_user_context(),
            ),
            404,
        )
    technicians = _get_technicians(active_only=True)
    return render_template(
        "ticket_detail.html",
        ticket=ticket,
        timeline=timeline,
        technicians=technicians,
        user=_get_user_context(),
    )


@app.route("/tickets/<int:ticket_id>/close", methods=["POST"])
def close_ticket(ticket_id: int) -> Any:
    user = _get_user_context()
    if user["role"] not in {"admin", "technician"}:
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))
    closed_at = _now_lima()
    with _get_connection() as connection:
        connection.execute(
            "UPDATE tickets SET status = ?, closed_at = ? WHERE id = ?",
            ("Cerrado", closed_at, ticket_id),
        )
        connection.execute(
            "INSERT INTO timeline (ticket_id, event, created_at) VALUES (?, ?, ?)",
            (ticket_id, "Ticket cerrado", closed_at),
        )
    return redirect(url_for("ticket_detail", ticket_id=ticket_id))


@app.route("/tickets/<int:ticket_id>/comment", methods=["POST"])
def comment_ticket(ticket_id: int) -> Any:
    user = _get_user_context()
    if user["role"] != "technician":
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))
    comment = request.form.get("comment", "").strip()
    if not comment:
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))
    created_at = _now_lima()
    with _get_connection() as connection:
        connection.execute(
            "INSERT INTO timeline (ticket_id, event, created_at) VALUES (?, ?, ?)",
            (ticket_id, f"Comentario técnico: {comment}", created_at),
        )
    return redirect(url_for("ticket_detail", ticket_id=ticket_id))


@app.route("/tickets/<int:ticket_id>/reassign", methods=["POST"])
def reassign_ticket(ticket_id: int) -> Any:
    user = _get_user_context()
    if user["role"] != "technician":
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))
    technician_email = request.form.get("technician_email", "")
    note = request.form.get("note", "").strip()
    if not technician_email:
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))
    assigned_at = _now_lima()
    if technician_email == "dispatcher":
        with _get_connection() as connection:
            connection.execute(
                "UPDATE tickets SET assigned_to = ?, status = ? WHERE id = ?",
                ("Sin asignar", "Pendiente", ticket_id),
            )
            event = "Devuelto al derivador"
            if note:
                event = f"{event}: {note}"
            connection.execute(
                "INSERT INTO timeline (ticket_id, event, created_at) VALUES (?, ?, ?)",
                (ticket_id, event, assigned_at),
            )
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))
    technician = _get_technician_by_email(technician_email)
    if not technician:
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))
    with _get_connection() as connection:
        connection.execute(
            "UPDATE tickets SET assigned_to = ?, status = ? WHERE id = ?",
            (technician_email, "En progreso", ticket_id),
        )
        actor = user.get("identifier") or "Técnico"
        event = (
            f"Reasignado por {actor} a {technician['name']} ({technician['email']})"
        )
        if note:
            event = f"{event}: {note}"
        connection.execute(
            "INSERT INTO timeline (ticket_id, event, created_at) VALUES (?, ?, ?)",
            (ticket_id, event, assigned_at),
        )
    return redirect(url_for("ticket_detail", ticket_id=ticket_id))


@app.route("/admin/technicians", methods=["GET", "POST"])
def admin_technicians() -> Any:
    user = _get_user_context()
    if user["role"] != "admin":
        return redirect(url_for("index"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        specialty = request.form.get("specialty", "").strip()
        if name and email and specialty:
            with _get_connection() as connection:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO technicians (name, email, specialty, is_active)
                    VALUES (?, ?, ?, 1)
                    """,
                    (name, email, specialty),
                )
        return redirect(url_for("admin_technicians"))
    return render_template(
        "admin_technicians.html",
        technicians=_get_technicians(),
        user=user,
    )


@app.route("/admin/credentials", methods=["GET", "POST"])
def admin_credentials() -> Any:
    user = _get_user_context()
    if user["role"] != "admin":
        return redirect(url_for("index"))
    if request.method == "POST":
        action = request.form.get("action", "upsert")
        role = request.form.get("role", "").strip()
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        if action == "update_admin":
            admin_identifier = user.get("identifier")
            if admin_identifier and password:
                _upsert_user("admin", admin_identifier, password)
        elif role in {"dispatcher", "technician"} and identifier and password:
            _upsert_user(role, identifier, password)
        return redirect(url_for("admin_credentials"))
    with _get_connection() as connection:
        users = connection.execute(
            "SELECT * FROM users WHERE role != 'admin' ORDER BY role, identifier"
        ).fetchall()
    return render_template(
        "admin_credentials.html",
        users=users,
        technicians=_get_technicians(),
        user=user,
    )


@app.route("/admin/technicians/<int:tech_id>/update", methods=["POST"])
def update_technician(tech_id: int) -> Any:
    user = _get_user_context()
    if user["role"] != "admin":
        return redirect(url_for("index"))
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    specialty = request.form.get("specialty", "").strip()
    is_active = 1 if request.form.get("is_active") == "on" else 0
    if name and email and specialty:
        with _get_connection() as connection:
            connection.execute(
                """
                UPDATE technicians
                SET name = ?, email = ?, specialty = ?, is_active = ?
                WHERE id = ?
                """,
                (name, email, specialty, is_active, tech_id),
            )
    return redirect(url_for("admin_technicians"))


@app.route("/admin/technicians/<int:tech_id>/disable", methods=["POST"])
def disable_technician(tech_id: int) -> Any:
    user = _get_user_context()
    if user["role"] != "admin":
        return redirect(url_for("index"))
    with _get_connection() as connection:
        connection.execute(
            "UPDATE technicians SET is_active = 0 WHERE id = ?", (tech_id,)
        )
    return redirect(url_for("admin_technicians"))


@app.route("/tickets/<int:ticket_id>/assign", methods=["POST"])
def assign_ticket(ticket_id: int) -> Any:
    user = _get_user_context()
    if user["role"] != "dispatcher":
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))
    technician_email = request.form.get("technician_email") or "Sin asignar"
    technician = _get_technician_by_email(technician_email)
    dispatcher = user.get("identifier") or "Derivador"
    assigned_label = (
        f"{technician['name']} ({technician['email']})" if technician else "Sin asignar"
    )
    assigned_at = _now_lima()
    with _get_connection() as connection:
        connection.execute(
            "UPDATE tickets SET assigned_to = ?, status = ? WHERE id = ?",
            (technician_email, "En progreso", ticket_id),
        )
        connection.execute(
            "INSERT INTO timeline (ticket_id, event, created_at) VALUES (?, ?, ?)",
            (ticket_id, f"Derivado por {dispatcher} a {assigned_label}", assigned_at),
        )
    return redirect(url_for("ticket_detail", ticket_id=ticket_id))


@app.route("/exports/closed")
def export_closed() -> Any:
    user = _get_user_context()
    query = "SELECT * FROM tickets WHERE status = 'Cerrado'"
    params: tuple[Any, ...] = ()
    if user["role"] == "technician" and user["technician_email"]:
        query += " AND assigned_to = ?"
        params = (user["technician_email"],)
    query += " ORDER BY closed_at DESC"
    with _get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "ID",
            "Solicitante",
            "Asunto",
            "Técnico",
            "Estado",
            "Creado",
            "Cerrado",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["email_from"],
                row["subject"],
                row["assigned_to"],
                row["status"],
                row["created_at"],
                row["closed_at"],
            ]
        )
    output.seek(0)
    filename = "tickets_cerrados.csv"
    return (
        output.getvalue(),
        200,
        {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )


@app.route("/intake/email", methods=["POST"])
def intake_email() -> Any:
    payload = request.get_json(silent=True) or {}
    email_from = payload.get("from", "cliente@dominio.com")
    subject = payload.get("subject", "Sin asunto")
    body = payload.get("body", "Sin detalle")
    ticket_id = _create_ticket(email_from, subject, body)
    return jsonify({"ticket_id": ticket_id, "status": "creado"})


@app.route("/dashboard")
def dashboard() -> str:
    user = _get_user_context()
    if user["role"] == "technician":
        return redirect(url_for("index"))
    with _get_connection() as connection:
        tickets = connection.execute(
            "SELECT * FROM tickets ORDER BY created_at DESC"
        ).fetchall()
    metrics = _calculate_metrics(tickets)
    ticket_views = [_build_ticket_view(ticket) for ticket in tickets]
    return render_template(
        "dashboard.html",
        tickets=ticket_views,
        metrics=metrics,
        user=user,
    )


def _calculate_metrics(tickets: list[sqlite3.Row]) -> dict[str, Any]:
    durations = []
    open_tickets = 0
    for ticket in tickets:
        if ticket["closed_at"]:
            created_at = datetime.fromisoformat(ticket["created_at"])
            closed_at = datetime.fromisoformat(ticket["closed_at"])
            durations.append((closed_at - created_at).total_seconds())
        else:
            open_tickets += 1
    average_seconds = sum(durations) / len(durations) if durations else 0
    return {
        "total": len(tickets),
        "open": open_tickets,
        "closed": len(tickets) - open_tickets,
        "avg_hours": round(average_seconds / 3600, 2),
    }


def _build_ticket_view(ticket: sqlite3.Row) -> dict[str, Any]:
    hours = None
    if ticket["closed_at"]:
        created_at = datetime.fromisoformat(ticket["created_at"])
        closed_at = datetime.fromisoformat(ticket["closed_at"])
        hours = round((closed_at - created_at).total_seconds() / 3600, 2)
    return {**dict(ticket), "hours": hours}


def _get_user_context() -> dict[str, str]:
    role = session.get("role", "guest")
    technician_email = session.get("technician_email", "")
    identifier = session.get("user_identifier", "")
    return {
        "role": role,
        "technician_email": technician_email,
        "identifier": identifier,
    }


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def _authenticate_user(role: str, identifier: str, password: str) -> bool:
    if not identifier or not password:
        return False
    with _get_connection() as connection:
        record = connection.execute(
            "SELECT password_hash, salt FROM users WHERE role = ? AND identifier = ?",
            (role, identifier),
        ).fetchone()
    if not record:
        return False
    return _hash_password(password, record["salt"]) == record["password_hash"]


def _upsert_user(role: str, identifier: str, password: str) -> None:
    salt = secrets.token_hex(8)
    password_hash = _hash_password(password, salt)
    with _get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM users WHERE role = ? AND identifier = ?",
            (role, identifier),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE users SET password_hash = ?, salt = ? WHERE id = ?
                """,
                (password_hash, salt, existing["id"]),
            )
        else:
            connection.execute(
                """
                INSERT INTO users (role, identifier, password_hash, salt)
                VALUES (?, ?, ?, ?)
                """,
                (role, identifier, password_hash, salt),
            )


def _record_login(identifier: str) -> None:
    with _get_connection() as connection:
        connection.execute(
            "UPDATE users SET last_login = ? WHERE identifier = ?",
            (_now_lima(), identifier),
        )


def _get_technician_by_email(email: str) -> sqlite3.Row | None:
    if not email or email == "Sin asignar":
        return None
    with _get_connection() as connection:
        return connection.execute(
            "SELECT * FROM technicians WHERE email = ?", (email,)
        ).fetchone()


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
