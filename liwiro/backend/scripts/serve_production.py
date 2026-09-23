#!/usr/bin/env python3
"""Run the Liwiro backend with a production WSGI server."""

from __future__ import annotations

import os

from waitress import serve

from app.main import create_app


def _int_env(name: str, default: int, *, minimum: int, maximum: int | None = None) -> int:
    raw = str(os.getenv(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    value = max(minimum, value)
    return min(value, maximum) if maximum is not None else value


def main() -> None:
    host = str(os.getenv("FLASK_HOST") or "127.0.0.1").strip()
    port = _int_env("FLASK_PORT", 5000, minimum=1, maximum=65535)
    threads = _int_env("LIWIRO_WAITRESS_THREADS", 8, minimum=1, maximum=256)
    serve(create_app(), host=host, port=port, threads=threads)


if __name__ == "__main__":
    main()
