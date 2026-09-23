#!/usr/bin/env python3
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import os
import sys
import time

import requests


BACKEND_URL = os.getenv("LIWIRO_BACKEND_URL", "http://127.0.0.1:5000").rstrip("/")
VDB_URL = os.getenv("VDB_SERVER_URL", "http://127.0.0.1:1957").rstrip("/")
SUPER_ADMIN_USER = os.getenv("LIWIRO_E2E_SUPER_ADMIN_USER", "e2eadmin")
SUPER_ADMIN_PASS = os.getenv("LIWIRO_E2E_SUPER_ADMIN_PASS", "CHANGE_ME_E2E_SUPER_ADMIN_PASSWORD")
VDB_APP_USER = os.getenv("LIWIRO_E2E_VDB_APP_USER", "ver")
VDB_APP_PASS = os.getenv("LIWIRO_E2E_VDB_APP_PASS", "CHANGE_ME_E2E_VDB_APP_PASSWORD")


def fail(msg: str):
    print(f"[E2E-ENDPOINTS][FAIL] {msg}")
    sys.exit(1)


def ok(msg: str):
    print(f"[E2E-ENDPOINTS][OK] {msg}")


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


def request_json(method: str, path: str, expected=(200,), **kwargs):
    url = f"{BACKEND_URL}{path}"
    r = requests.request(method, url, timeout=30, **kwargs)
    try:
        payload = r.json() if r.text else {}
    except Exception:
        payload = {"raw": r.text}
    if r.status_code not in expected:
        fail(f"{method} {path} -> {r.status_code}, payload={payload}")
    return payload, r.status_code


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def signin() -> str:
    signin_payload = {
        "username": SUPER_ADMIN_USER,
        "password": SUPER_ADMIN_PASS,
        "vdb_server_url": VDB_URL,
        "vdb_app_username": VDB_APP_USER,
        "vdb_app_password": VDB_APP_PASS,
        "liwiro_super_admin_username": SUPER_ADMIN_USER,
        "liwiro_super_admin_password": SUPER_ADMIN_PASS,
    }
    resp, _ = request_json("POST", "/auth/signin", expected=(200,), json=signin_payload)
    token = str(resp.get("token") or "").strip()
    if not token:
        fail(f"/auth/signin did not return token: {resp}")
    return token


def main():
    wait_http(f"{BACKEND_URL}/auth/status", timeout=90)
    ok("Backend reachable")

    # Public metadata endpoints
    request_json("GET", "/", expected=(200,))
    request_json("GET", "/health", expected=(200,))
    request_json("GET", "/license", expected=(200,))
    request_json("GET", "/auth/status", expected=(200,))
    ok("Public metadata endpoints verified")

    token = signin()
    ok("Auth signin verified")

    # Auth protected endpoints
    me_payload, _ = request_json("GET", "/auth/me", expected=(200,), headers={"Authorization": f"Bearer {token}"})
    if not bool(me_payload.get("authenticated")):
        fail(f"/auth/me unexpected payload: {me_payload}")
    request_json("GET", "/services", expected=(200,), headers={"Authorization": f"Bearer {token}"})
    request_json("GET", "/platform/settings", expected=(200,), headers={"Authorization": f"Bearer {token}"})
    settings_payload, _ = request_json(
        "PUT",
        "/platform/settings",
        expected=(200,),
        headers=auth_headers(token),
        json={"startServicesOnStartup": False, "autoRefreshServiceStatus": True},
    )
    if "startServicesOnStartup" not in settings_payload or "autoRefreshServiceStatus" not in settings_payload:
        fail(f"/platform/settings PUT unexpected payload: {settings_payload}")
    ok("Settings endpoints verified")

    users_before, _ = request_json("GET", "/platform/users", expected=(200,), headers={"Authorization": f"Bearer {token}"})
    before_count = len(users_before) if isinstance(users_before, list) else 0
    tmp_user = f"e2e_user_{int(time.time())}"
    created_user, _ = request_json(
        "POST",
        "/platform/users",
        expected=(201,),
        headers=auth_headers(token),
        json={
            "username": tmp_user,
            "password": "TmpPass0!",
            "role": "editor",
            "service_access": ["*"],
            "permissions": [],
            "liwiro_rbac": {"services": []},
        },
    )
    if str(created_user.get("username") or "") != tmp_user:
        fail(f"/platform/users POST mismatch: {created_user}")
    request_json(
        "PUT",
        f"/platform/users/{tmp_user}",
        expected=(200,),
        headers=auth_headers(token),
        json={"role": "viewer", "service_access": ["*"]},
    )
    request_json(
        "DELETE",
        f"/platform/users/{tmp_user}",
        expected=(200,),
        headers=auth_headers(token),
        json={},
    )
    users_after, _ = request_json("GET", "/platform/users", expected=(200,), headers={"Authorization": f"Bearer {token}"})
    after_count = len(users_after) if isinstance(users_after, list) else 0
    if after_count != before_count:
        fail(f"User count mismatch after create/update/delete cycle: before={before_count}, after={after_count}")
    ok("Platform user CRUD endpoints verified")

    domains_before_payload, _ = request_json(
        "GET", "/platform/vdb/domains", expected=(200,), headers={"Authorization": f"Bearer {token}"}
    )
    domains_before = domains_before_payload.get("domains") if isinstance(domains_before_payload, dict) else []
    domains_before = domains_before if isinstance(domains_before, list) else []
    tmp_domain = f"e2edomain{int(time.time())}"
    create_domain_payload, _ = request_json(
        "POST",
        "/platform/vdb/domains",
        expected=(201,),
        headers=auth_headers(token),
        json={"domain": tmp_domain, "db": "main"},
    )
    if str(create_domain_payload.get("domain") or "") != tmp_domain:
        fail(f"/platform/vdb/domains POST mismatch: {create_domain_payload}")
    domains_after_payload, _ = request_json(
        "GET", "/platform/vdb/domains", expected=(200,), headers={"Authorization": f"Bearer {token}"}
    )
    domains_after = domains_after_payload.get("domains") if isinstance(domains_after_payload, dict) else []
    domains_after = domains_after if isinstance(domains_after, list) else []
    if tmp_domain not in domains_after:
        fail(f"Created domain not present in list: {tmp_domain}")
    if len(domains_after) < len(domains_before):
        fail("Domain list unexpectedly shrank after create")
    ok("Platform VDB domain endpoints verified")

    request_json("POST", "/auth/logout", expected=(200,), headers={"Authorization": f"Bearer {token}"}, json={})
    request_json("GET", "/auth/me", expected=(401,), headers={"Authorization": f"Bearer {token}"})
    ok("Auth logout verified")

    print("[E2E-ENDPOINTS][PASS] Backend endpoint sweep passed.")


if __name__ == "__main__":
    main()
