#!/usr/bin/env python3
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
from multiprocessing.connection import Listener
from threading import Event, Thread
from urllib.parse import urljoin

import requests


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bridge Windows named-pipe VDB traffic to the local VDB HTTP server.")
    parser.add_argument("--pipe", required=True, help=r"Named pipe path, for example \\.\pipe\verun_vdb")
    parser.add_argument("--server-url", required=True, help="Target VDB HTTP base URL, for example http://127.0.0.1:1957")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP request timeout in seconds")
    return parser.parse_args()


def _json_body(response: requests.Response):
    if not response.text:
        return {}
    try:
        return response.json()
    except ValueError:
        return response.text


def _forward_request(server_url: str, envelope: dict, timeout: float) -> dict:
    method = str(envelope.get("method") or "GET").strip().upper() or "GET"
    path = "/" + str(envelope.get("path") or "/").lstrip("/")
    headers = dict(envelope.get("headers") or {})
    headers.pop("Host", None)
    body = envelope.get("body")
    request_kwargs = {
        "headers": headers,
        "timeout": timeout,
        "allow_redirects": False,
    }
    if isinstance(body, (dict, list)):
        request_kwargs["json"] = body
    elif body not in (None, ""):
        request_kwargs["data"] = body

    response = requests.request(method, urljoin(server_url.rstrip("/") + "/", path.lstrip("/")), **request_kwargs)
    return {
        "statusCode": int(response.status_code),
        "contentType": str(response.headers.get("Content-Type") or "application/json; charset=UTF-8"),
        "body": _json_body(response),
    }


def _handle_client(conn, server_url: str, timeout: float, log: logging.Logger) -> None:
    try:
        while True:
            try:
                raw_request = conn.recv_bytes()
            except EOFError:
                return
            try:
                envelope = json.loads(raw_request.decode("utf-8"))
                if not isinstance(envelope, dict):
                    raise ValueError("Request envelope must be a JSON object")
                payload = _forward_request(server_url, envelope, timeout)
            except Exception as exc:
                log.warning("Named-pipe bridge request failed: %s", exc)
                payload = {
                    "statusCode": 502,
                    "contentType": "application/json; charset=UTF-8",
                    "body": {"error": str(exc) or "Bridge request failed"},
                }
            conn.send_bytes(json.dumps(payload).encode("utf-8"))
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main() -> int:
    args = _parse_args()
    logger = logging.getLogger("namedpipe_bridge")
    logging.basicConfig(level=logging.INFO, format="[namedpipe-bridge] %(message)s")

    if sys.platform != "win32":
        logger.error("Named-pipe bridge can only run on Windows.")
        return 1

    stop_event = Event()

    def _stop(*_args):
        stop_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    logger.info("listening on %s -> %s", args.pipe, args.server_url)
    while not stop_event.is_set():
        listener = None
        try:
            listener = Listener(args.pipe, family="AF_PIPE")
            while not stop_event.is_set():
                try:
                    conn = listener.accept()
                except (OSError, EOFError):
                    if stop_event.is_set():
                        break
                    raise
                Thread(
                    target=_handle_client,
                    args=(conn, args.server_url, args.timeout, logger),
                    name="vdb-namedpipe-client",
                    daemon=True,
                ).start()
        except Exception as exc:
            logger.error("Named-pipe listener failed: %s", exc)
            return 1
        finally:
            if listener is not None:
                try:
                    listener.close()
                except Exception:
                    pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
