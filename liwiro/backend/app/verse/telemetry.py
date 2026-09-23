"""Local, shared request telemetry. Never stores bodies, credentials or query strings."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time


class PlatformTelemetry:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / "platform_activity.sqlite3"

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, timestamp TEXT, username TEXT, service TEXT, action TEXT, method TEXT, status INTEGER, durationMs REAL)")
        connection.execute("CREATE INDEX IF NOT EXISTS events_owner ON events(username, id)")
        connection.execute("CREATE INDEX IF NOT EXISTS events_service ON events(service, id)")
        return connection

    def record(self, *, username="", service="", action="", method="", status=200, duration_ms=0):
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO events(timestamp, username, service, action, method, status, durationMs) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (datetime.now(timezone.utc).isoformat(), username, service, action, method, status, round(duration_ms, 2)))
            db.execute("DELETE FROM events WHERE id <= (SELECT MAX(id) - 100000 FROM events)")

    def rows(self, username, services=(), limit=2000):
        # Platform actions belong to the actor; service traffic follows service access.
        names = list(services)
        placeholders = ",".join("?" for _ in names) or "NULL"
        with closing(self.connect()) as db:
            rows = db.execute(f"SELECT timestamp, service, action, method, status, durationMs FROM events WHERE (service = '' AND username = ?) OR service IN ({placeholders}) ORDER BY id DESC LIMIT ?", [username, *names, limit]).fetchall()
        return [{**dict(row), "requests": 1, "errors": int(row["status"] >= 400)} for row in rows]


def install_telemetry(app, data_dir, *, service="", session_loader=None):
    from flask import g, request
    telemetry = PlatformTelemetry(data_dir)

    @app.before_request
    def begin_activity():
        g.ananse_started_at = time.monotonic()

    @app.after_request
    def collect_activity(response):
        if request.method == "OPTIONS" or request.path == "/health":
            return response
        # Do not let dashboard polling become its own dominant data source.
        if request.path.startswith(("/platform/verse/datasets", "/platform/verse/notifications", "/platform/verse/bootstrap")):
            return response
        try:
            session = session_loader() if session_loader else {}
            username = str((session or {}).get("username") or "")
            if service or username:
                telemetry.record(username=username, service=service,
                                 action=str(request.url_rule or "unmatched"), method=request.method,
                                 status=response.status_code,
                                 duration_ms=(time.monotonic() - getattr(g, "ananse_started_at", time.monotonic())) * 1000)
        except Exception:
            app.logger.warning("Could not collect Ananse request metrics", exc_info=True)
        return response
