#!/usr/bin/env python3
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import json
import os
import sys
import time
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlencode

import requests


BACKEND_URL = os.getenv("LIWIRO_BACKEND_URL", "http://127.0.0.1:5000").rstrip("/")
VDB_URL = os.getenv("VDB_SERVER_URL", "http://127.0.0.1:1957").rstrip("/")
LAPIS_FILE = os.getenv(
    "LIWIRO_E2E_LAPIS_FILE",
    str(Path(__file__).resolve().parents[2] / "data" / "lapis-examples" / "14-create-service-e2e-noauth.json"),
)
DOCS_KEY = "liwiroservicepass0!"
SUPER_ADMIN_USER = os.getenv("LIWIRO_E2E_SUPER_ADMIN_USER", "e2eadmin")
SUPER_ADMIN_PASS = os.getenv("LIWIRO_E2E_SUPER_ADMIN_PASS", "CHANGE_ME_E2E_SUPER_ADMIN_PASSWORD")
VDB_APP_USER = os.getenv("LIWIRO_E2E_VDB_APP_USER", "ver")
VDB_APP_PASS = os.getenv("LIWIRO_E2E_VDB_APP_PASS", "CHANGE_ME_E2E_VDB_APP_PASSWORD")


def fail(msg: str):
    print(f"[E2E][FAIL] {msg}")
    sys.exit(1)


def ok(msg: str):
    print(f"[E2E][OK] {msg}")


def wait_http(url: str, timeout: float = 60.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code < 500:
                return
        except Exception:
            pass
        time.sleep(1)
    fail(f"Service not reachable in time: {url}")


def request_json(method: str, url: str, expected=(200,), **kwargs):
    r = requests.request(method, url, timeout=30, **kwargs)
    text = r.text
    try:
        payload = r.json() if text else {}
    except Exception:
        payload = {"raw": text}
    if r.status_code not in expected:
        fail(f"{method} {url} -> {r.status_code}, payload={payload}")
    return payload, r.status_code


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_unique_config(base_cfg: dict) -> tuple[dict, str]:
    suffix = str(int(time.time()))
    cfg = deepcopy(base_cfg)
    cfg["metadata"]["apiName"] = f"CreateServiceE2E_{suffix}"
    cfg["metadata"]["basePath"] = f"/api/e2e/{suffix}"
    return cfg, cfg["metadata"]["apiName"]


def call_endpoint(root_url: str, endpoint: dict):
    method = str(endpoint.get("method", "GET")).upper()
    path = str(endpoint.get("path", ""))
    ex = endpoint.get("exampleParams") or {}
    query = ex.get("query") if isinstance(ex.get("query"), dict) else {}
    body = ex.get("body") if isinstance(ex.get("body"), dict) else {}
    headers = ex.get("headers") if isinstance(ex.get("headers"), dict) else {}

    url = f"{root_url}{path}"
    if query:
        url = f"{url}?{urlencode({k: str(v) for k, v in query.items()})}"

    req_headers = {k: str(v) for k, v in headers.items()}
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        req_headers.setdefault("Content-Type", "application/json")

    resp = requests.request(method, url, headers=req_headers, json=body if body else None, timeout=30)
    payload = {}
    try:
        payload = resp.json() if resp.text else {}
    except Exception:
        payload = {"raw": resp.text}

    if not (200 <= resp.status_code < 300):
        fail(f"Endpoint failed: {method} {url} -> {resp.status_code}, payload={payload}")
    ok(f"Endpoint ok: {method} {url} -> {resp.status_code}")
    return payload


def main():
    lapis_path = Path(LAPIS_FILE)
    if not lapis_path.exists():
        fail(f"LAPIS file not found: {lapis_path}")

    wait_http(f"{VDB_URL}/health")
    wait_http(f"{BACKEND_URL}/auth/status")
    ok("VDB and backend are reachable")

    status_payload, _ = request_json("GET", f"{BACKEND_URL}/auth/status", expected=(200,))
    ok(f"Backend auth status: configured={status_payload.get('configured')}")

    signin_payload = {
        "username": SUPER_ADMIN_USER,
        "password": SUPER_ADMIN_PASS,
        "vdb_server_url": VDB_URL,
        "vdb_app_username": VDB_APP_USER,
        "vdb_app_password": VDB_APP_PASS,
        "liwiro_super_admin_username": SUPER_ADMIN_USER,
        "liwiro_super_admin_password": SUPER_ADMIN_PASS,
    }
    signin_res, _ = request_json("POST", f"{BACKEND_URL}/auth/signin", expected=(200,), json=signin_payload)
    token = signin_res.get("token")
    if not token:
        fail(f"Missing token from /auth/signin response: {signin_res}")
    ok("Backend sign-in succeeded")

    raw_cfg = json.loads(lapis_path.read_text(encoding="utf-8"))
    cfg, api_name = create_unique_config(raw_cfg)

    gen_res, _ = request_json(
        "POST",
        f"{BACKEND_URL}/generate",
        expected=(201,),
        headers=auth_headers(token),
        json=cfg,
    )
    process_id = str(gen_res.get("process_id") or "").strip()
    port = str(gen_res.get("port") or "").strip()
    if not process_id or not port:
        fail(f"Generate response missing process_id/port: {gen_res}")
    ok(f"Service generated: api={api_name}, process_id={process_id}, port={port}")

    # Verify backend service listing/details.
    list_res, _ = request_json("GET", f"{BACKEND_URL}/services", expected=(200,), headers={"Authorization": f"Bearer {token}"})
    if not any(str(s.get("apiName", "")) == api_name for s in list_res if isinstance(s, dict)):
        fail(f"Generated service '{api_name}' not visible in /services")
    ok("Generated service present in backend /services")

    detail_res, _ = request_json("GET", f"{BACKEND_URL}/services/{process_id}", expected=(200,), headers={"Authorization": f"Bearer {token}"})
    if str(detail_res.get("apiName", "")) != api_name:
        fail(f"/services/{{id}} returned unexpected service: {detail_res}")
    ok("Generated service detail endpoint works")

    service_root = f"http://127.0.0.1:{port}"
    wait_http(f"{service_root}/liwiro")
    request_json("GET", f"{service_root}/liwiro", expected=(200,))
    ok("Generated service runtime endpoint /liwiro works")

    docs_payload, _ = request_json(
        "GET",
        f"{service_root}/liwiro/docs.json",
        expected=(200,),
        headers={"X-Docs-Key": DOCS_KEY},
    )
    endpoints = docs_payload.get("endpoints") or []
    if not isinstance(endpoints, list) or not endpoints:
        fail("No endpoints returned from docs.json")
    ok(f"Docs endpoint returned {len(endpoints)} endpoints")

    endpoint_index = {str(ep.get("id")): ep for ep in endpoints if isinstance(ep, dict)}
    execution_order = [
        "ep_note_create",
        "ep_note_read",
        "ep_note_update",
        "ep_note_query",
        "ep_note_script",
        "ep_note_delete",
    ]
    for endpoint_id in execution_order:
        ep = endpoint_index.get(endpoint_id)
        if not ep:
            fail(f"Expected endpoint id missing from docs: {endpoint_id}")
        call_endpoint(service_root, ep)

    stop_res, _ = request_json(
        "POST",
        f"{BACKEND_URL}/services/{process_id}/stop",
        expected=(200,),
        headers=auth_headers(token),
        json={},
    )
    ok(f"Service stop ok: {stop_res.get('message')}")

    start_res, _ = request_json(
        "POST",
        f"{BACKEND_URL}/services/{process_id}/start",
        expected=(200,),
        headers=auth_headers(token),
        json={},
    )
    new_pid = str(start_res.get("process_id") or process_id)
    ok(f"Service restart ok: new_pid={new_pid}")

    request_json(
        "DELETE",
        f"{BACKEND_URL}/services/{new_pid}/delete?deleteData=true",
        expected=(200,),
        headers=auth_headers(token),
        json={},
    )
    ok("Service delete endpoint works")

    # Confirm service removed from backend listing.
    services_after, _ = request_json("GET", f"{BACKEND_URL}/services", expected=(200,), headers={"Authorization": f"Bearer {token}"})
    if any(str(s.get("apiName", "")) == api_name for s in services_after if isinstance(s, dict)):
        fail("Service still present after delete")
    ok("Service cleanup verified")

    print("[E2E][PASS] Live create-service flow and all generated endpoints verified.")


if __name__ == "__main__":
    main()
