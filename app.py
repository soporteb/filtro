from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "support.db")

app = Flask(__name__)


TECHNICIANS = [
    {"name": "Laura Gomez", "email": "laura.gomez@miempresa.com", "specialty": "Redes"},
    {"name": "Carlos Perez", "email": "carlos.perez@miempresa.com", "specialty": "Software"},
    {"name": "Ana Rojas", "email": "ana.rojas@miempresa.com", "specialty": "Hardware"},
]


def _get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with _get_connection() as connection:
        connection.executescript(
            """
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


def _assign_technician(subject: str, body: str) -> dict[str, str]:
    content = f"{subject} {body}".lower()
    if "red" in content or "network" in content:
        return TECHNICIANS[0]
    if "hardware" in content or "impresora" in content:
        return TECHNICIANS[2]
    return TECHNICIANS[1]


def _create_ticket(email_from: str, subject: str, body: str) -> int:
    technician = _assign_technician(subject, body)
    created_at = _utc_now()
    with _get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tickets (email_from, subject, body, assigned_to, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (email_from, subject, body, technician["email"], "Abierto", created_at),
        )
        ticket_id = cursor.lastrowid
        connection.execute(
            "INSERT INTO timeline (ticket_id, event, created_at) VALUES (?, ?, ?)",
            (ticket_id, f"Asignado a {technician['name']} ({technician['email']})", created_at),
        )
    return int(ticket_id)


@app.route("/")
def index() -> str:
    with _get_connection() as connection:
        tickets = connection.execute(
            "SELECT * FROM tickets ORDER BY created_at DESC"
        ).fetchall()
    return render_template("index.html", tickets=tickets, technicians=TECHNICIANS)


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
        return render_template("ticket_not_found.html", ticket_id=ticket_id), 404
    return render_template("ticket_detail.html", ticket=ticket, timeline=timeline)


@app.route("/tickets/<int:ticket_id>/close", methods=["POST"])
def close_ticket(ticket_id: int) -> Any:
    closed_at = _utc_now()
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
    with _get_connection() as connection:
        tickets = connection.execute(
            "SELECT * FROM tickets ORDER BY created_at DESC"
        ).fetchall()
    metrics = _calculate_metrics(tickets)
    ticket_views = [_build_ticket_view(ticket) for ticket in tickets]
    return render_template("dashboard.html", tickets=ticket_views, metrics=metrics)


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


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
