#!/usr/bin/env python3
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"""Generate every LAPIS example, call every declared endpoint, and clean up."""

from __future__ import annotations

import argparse
import hashlib
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
EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "lapis-examples"
SUPER_ADMIN_USER = os.getenv("LIWIRO_E2E_SUPER_ADMIN_USER", "e2eadmin")
SUPER_ADMIN_PASS = os.getenv("LIWIRO_E2E_SUPER_ADMIN_PASS", "CHANGE_ME_E2E_SUPER_ADMIN_PASSWORD")
VDB_APP_USER = os.getenv("LIWIRO_E2E_VDB_APP_USER", "ver")
VDB_APP_PASS = os.getenv("LIWIRO_E2E_VDB_APP_PASS", "CHANGE_ME_E2E_VDB_APP_PASSWORD")
RUN_SUFFIX = str(int(time.time() * 1000))


def first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return default


def env_bool(*names: str, default: bool) -> bool:
    raw = first_env(*names)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def external_settings() -> dict[str, object]:
    return {
        "smtp_host": first_env("LIWIRO_E2E_SMTP_HOST", "VERUN_DEMO_EMAIL_SMTP_HOST", default="smtp.gmail.com"),
        "smtp_port": int(first_env("LIWIRO_E2E_SMTP_PORT", "VERUN_DEMO_EMAIL_SMTP_PORT", default="587")),
        "smtp_starttls": env_bool("LIWIRO_E2E_SMTP_STARTTLS", "VERUN_DEMO_EMAIL_SMTP_STARTTLS", default=True),
        "smtp_ssl": env_bool("LIWIRO_E2E_SMTP_SSL", "VERUN_DEMO_EMAIL_SMTP_SSL", default=False),
        "smtp_auth": env_bool("LIWIRO_E2E_SMTP_AUTH", "VERUN_DEMO_EMAIL_SMTP_AUTH", default=True),
        "smtp_username": first_env("LIWIRO_E2E_SMTP_USERNAME", "VERUN_DEMO_EMAIL_SMTP_USERNAME"),
        "smtp_password": first_env("LIWIRO_E2E_SMTP_PASSWORD", "VERUN_DEMO_EMAIL_SMTP_PASSWORD"),
        "email_from": first_env("LIWIRO_E2E_EMAIL_FROM", "VERUN_DEMO_EMAIL_FROM"),
        "email_to": first_env("LIWIRO_E2E_EMAIL_TO", "VERUN_DEMO_EMAIL_TO"),
        "cloud_name": first_env("LIWIRO_E2E_CLOUDINARY_CLOUD_NAME", "VERUN_DEMO_CLOUDINARY_CLOUD_NAME"),
        "cloudinary_key": first_env("LIWIRO_E2E_CLOUDINARY_API_KEY", "VERUN_DEMO_CLOUDINARY_API_KEY"),
        "cloudinary_secret": first_env("LIWIRO_E2E_CLOUDINARY_API_SECRET", "VERUN_DEMO_CLOUDINARY_API_SECRET"),
        "cloudinary_folder": first_env(
            "LIWIRO_E2E_CLOUDINARY_FOLDER",
            "VERUN_DEMO_CLOUDINARY_FOLDER",
            default="liwiro-e2e",
        ),
    }


def missing_external_settings(settings: dict[str, object]) -> list[str]:
    required = {
        "LIWIRO_E2E_SMTP_USERNAME (or VERUN_DEMO_EMAIL_SMTP_USERNAME)": settings["smtp_username"],
        "LIWIRO_E2E_SMTP_PASSWORD (or VERUN_DEMO_EMAIL_SMTP_PASSWORD)": settings["smtp_password"],
        "LIWIRO_E2E_EMAIL_FROM (or VERUN_DEMO_EMAIL_FROM)": settings["email_from"],
        "LIWIRO_E2E_EMAIL_TO (or VERUN_DEMO_EMAIL_TO)": settings["email_to"],
        "LIWIRO_E2E_CLOUDINARY_CLOUD_NAME (or VERUN_DEMO_CLOUDINARY_CLOUD_NAME)": settings["cloud_name"],
        "LIWIRO_E2E_CLOUDINARY_API_KEY (or VERUN_DEMO_CLOUDINARY_API_KEY)": settings["cloudinary_key"],
        "LIWIRO_E2E_CLOUDINARY_API_SECRET (or VERUN_DEMO_CLOUDINARY_API_SECRET)": settings["cloudinary_secret"],
    }
    return [name for name, value in required.items() if not str(value or "").strip()]


def fail(message: str) -> None:
    raise RuntimeError(message)


def ok(message: str) -> None:
    print(f"[LAPIS-E2E][OK] {message}", flush=True)


def wait_http(url: str, timeout: float = 90.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            response = requests.get(url, timeout=3)
            if response.status_code < 500:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    fail(f"Service not reachable in time: {url}")


def request_json(method: str, url: str, expected: tuple[int, ...] = (200,), **kwargs):
    response = requests.request(method, url, timeout=45, **kwargs)
    try:
        payload = response.json() if response.text else {}
    except ValueError:
        payload = {"raw": response.text}
    if response.status_code not in expected:
        fail(f"{method} {url} -> {response.status_code}, payload={payload}")
    return payload, response.status_code


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def load_examples() -> list[tuple[Path, dict]]:
    examples = []
    for path in sorted(EXAMPLES_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            fail(f"LAPIS example is not an object: {path}")
        examples.append((path, payload))
    if len(examples) != 15:
        fail(f"Expected 15 LAPIS examples, found {len(examples)} in {EXAMPLES_DIR}")
    return examples


def replace_scalars(value, replacements: dict[object, object]):
    if isinstance(value, dict):
        return {key: replace_scalars(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_scalars(item, replacements) for item in value]
    return replacements.get(value, value)


def replace_service_names(value, replacements: dict[str, str]):
    if isinstance(value, dict):
        return {key: replace_service_names(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_service_names(item, replacements) for item in value]
    if isinstance(value, str):
        updated = value
        for original, replacement in replacements.items():
            updated = updated.replace(original, replacement)
        return updated
    return value


def make_crud_examples_unique(config: dict) -> None:
    replacements: dict[object, object] = {}
    models = config.get("models") if isinstance(config.get("models"), dict) else {}
    endpoints = config.get("endpoints") if isinstance(config.get("endpoints"), dict) else {}
    models_by_name = {
        str(model.get("name") or ""): model
        for model in models.values()
        if isinstance(model, dict) and str(model.get("name") or "").strip()
    }

    for endpoint in endpoints.values():
        if not isinstance(endpoint, dict) or str(endpoint.get("crudOperation") or "").lower() != "create":
            continue
        model = models_by_name.get(str(endpoint.get("linkedModel") or "")) or {}
        fields = model.get("fields") if isinstance(model.get("fields"), dict) else {}
        body = ((endpoint.get("exampleParams") or {}).get("body") or {})
        if not isinstance(body, dict):
            continue
        unique_names = [
            str(field.get("name") or "")
            for field in fields.values()
            if isinstance(field, dict) and bool(field.get("unique"))
        ]
        for field_name in unique_names:
            original = body.get(field_name)
            if isinstance(original, str) and original:
                replacements[original] = f"{original}-e2e-{RUN_SUFFIX}"

    if replacements:
        config["endpoints"] = replace_scalars(endpoints, replacements)


def configure_external_services(config: dict, settings: dict[str, object]) -> None:
    metadata = config.setdefault("metadata", {})
    env = metadata.setdefault("env", {})
    api_name = str(metadata.get("apiName") or "")
    base_api_name = api_name.split("_E2E_", 1)[0]

    if base_api_name in {"AuthCoreService", "ContactFormEmailService"}:
        env.update(
            {
                "EMAIL_SMTP_HOST": settings["smtp_host"],
                "EMAIL_SMTP_PORT": settings["smtp_port"],
                "EMAIL_SMTP_STARTTLS": settings["smtp_starttls"],
                "EMAIL_SMTP_SSL": settings["smtp_ssl"],
                "EMAIL_SMTP_AUTH": settings["smtp_auth"],
                "EMAIL_SMTP_USERNAME": settings["smtp_username"],
                "EMAIL_SMTP_PASSWORD": settings["smtp_password"],
                "EMAIL_FROM": settings["email_from"],
                "EMAIL_TO": settings["email_to"],
            }
        )

    if base_api_name == "MediaStorageBridgeService":
        env.update(
            {
                "CLOUDINARY_CLOUD_NAME": settings["cloud_name"],
                "CLOUDINARY_API_KEY": settings["cloudinary_key"],
                "CLOUDINARY_API_SECRET": settings["cloudinary_secret"],
                "CLOUDINARY_FOLDER": settings["cloudinary_folder"],
            }
        )
        upload = (config.get("endpoints") or {}).get("ep_upload_cloudinary") or {}
        body = (upload.get("exampleParams") or {}).get("body") or {}
        body["folder"] = settings["cloudinary_folder"]
        body["publicId"] = f"liwiro-e2e-{RUN_SUFFIX}"


def prepare_config(raw_config: dict, settings: dict[str, object], service_names: dict[str, str]) -> dict:
    config = replace_service_names(deepcopy(raw_config), service_names)
    make_crud_examples_unique(config)
    configure_external_services(config, settings)
    return config


def endpoint_url(root_url: str, endpoint: dict) -> str:
    path = str(endpoint.get("path") or "")
    return f"{root_url}{path if path.startswith('/') else '/' + path}"


def endpoint_payload(endpoint: dict) -> tuple[dict, dict, dict]:
    example = endpoint.get("exampleParams") if isinstance(endpoint.get("exampleParams"), dict) else {}
    query = example.get("query") if isinstance(example.get("query"), dict) else {}
    body = example.get("body") if isinstance(example.get("body"), dict) else {}
    headers = example.get("headers") if isinstance(example.get("headers"), dict) else {}
    return deepcopy(query), deepcopy(body), {str(key): str(value) for key, value in headers.items()}


def assert_semantic_success(endpoint_id: str, payload) -> None:
    if not isinstance(payload, dict):
        return
    if payload.get("ok") is False:
        fail(f"Endpoint {endpoint_id} returned ok=false: {payload}")
    for flag in ("authenticated", "created", "updated", "deleted"):
        if payload.get(flag) is False:
            fail(f"Endpoint {endpoint_id} returned {flag}=false: {payload}")
    if str(payload.get("status") or "").lower() in {"error", "failed", "skipped"}:
        fail(f"Endpoint {endpoint_id} returned status={payload.get('status')}: {payload}")


def call_endpoint(root_url: str, endpoint_id: str, endpoint: dict, token: str = "", overrides: dict | None = None):
    method = str(endpoint.get("method") or "GET").upper()
    query, body, headers = endpoint_payload(endpoint)
    overrides = overrides or {}
    if "replace_query" in overrides:
        query = deepcopy(overrides.get("replace_query") or {})
    else:
        query.update(overrides.get("query") or {})
    if "replace_body" in overrides:
        body = deepcopy(overrides.get("replace_body") or {})
    else:
        body.update(overrides.get("body") or {})
    # Endpoint examples often use dryRun=true for documentation probes. The
    # live harness must exercise persistence and external side effects.
    if "dryRun" in body:
        body["dryRun"] = False
    headers.update({str(key): str(value) for key, value in (overrides.get("headers") or {}).items()})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        headers.setdefault("Content-Type", "application/json")

    url = endpoint_url(root_url, endpoint)
    if query:
        url = f"{url}?{urlencode({key: json.dumps(value) if isinstance(value, (dict, list)) else value for key, value in query.items()})}"
    response = requests.request(
        method,
        url,
        headers=headers,
        json=body if method in {"POST", "PUT", "PATCH", "DELETE"} else None,
        timeout=60,
    )
    try:
        payload = response.json() if response.text else {}
    except ValueError:
        payload = {"raw": response.text}
    if not 200 <= response.status_code < 300:
        fail(f"Endpoint failed: {endpoint_id} {method} {url} -> {response.status_code}, payload={payload}")
    assert_semantic_success(endpoint_id, payload)
    ok(f"{endpoint_id}: {method} {endpoint.get('path')} -> {response.status_code}")
    return payload


def find_value(payload, keys: tuple[str, ...]):
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if value is not None and value != "":
                return value
        for value in payload.values():
            found = find_value(value, keys)
            if found is not None and found != "":
                return found
    if isinstance(payload, list):
        for value in payload:
            found = find_value(value, keys)
            if found is not None and found != "":
                return found
    return None


def docs_endpoints(root_url: str, config: dict) -> dict[str, dict]:
    docs_cfg = ((config.get("metadata") or {}).get("documentation") or {})
    docs_key = str(docs_cfg.get("key") or "").strip()
    headers = {"X-Documentation-Key": docs_key, "X-Docs-Key": docs_key}
    payload, _ = request_json("GET", f"{root_url}/liwiro/docs.json", (200,), headers=headers)
    endpoints = payload.get("endpoints") if isinstance(payload, dict) else None
    if not isinstance(endpoints, list):
        fail(f"Generated docs did not return an endpoint list: {payload}")
    by_id = {str(endpoint.get("id") or ""): endpoint for endpoint in endpoints if isinstance(endpoint, dict)}
    expected = set((config.get("endpoints") or {}).keys())
    missing = sorted(expected.difference(by_id))
    if missing:
        fail(f"Generated docs omitted endpoint ids: {missing}")
    return by_id


def setup_headers(config: dict) -> dict[str, str]:
    setup_key = str((config.get("metadata") or {}).get("setupApiKey") or "").strip()
    if not setup_key:
        fail(f"{(config.get('metadata') or {}).get('apiName')}: metadata.setupApiKey is required for E2E setup")
    return {"X-Liwiro-Setup-Key": setup_key, "Content-Type": "application/json"}


def seed_service(root_url: str, config: dict) -> None:
    seed = (config.get("metadata") or {}).get("seedData") or {}
    if not bool(seed.get("enabled")):
        return
    payload, _ = request_json(
        "POST",
        f"{root_url}/liwiro/setup/seed-db",
        (200,),
        headers=setup_headers(config),
        json={},
    )
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    failed_count = int((summary or {}).get("failed") or 0)
    if failed_count:
        fail(f"{config['metadata']['apiName']}: seed setup reported {failed_count} failures: {payload}")
    ok(f"{config['metadata']['apiName']}: seeded {(summary or {}).get('inserted', 0)} records")


def reset_default_super_admin(root_url: str, config: dict) -> dict[str, str]:
    default_admin = (config.get("auth") or {}).get("defaultSuperAdmin") or {}
    if not bool(default_admin.get("enabled")):
        fail(f"{config['metadata']['apiName']}: auth.defaultSuperAdmin must be enabled for E2E auth")
    credentials = {
        "username": str(default_admin.get("username") or "").strip(),
        "password": str(default_admin.get("password") or "").strip(),
    }
    if not credentials["username"] or not credentials["password"]:
        fail(f"{config['metadata']['apiName']}: default super-admin credentials are incomplete")
    payload, _ = request_json(
        "POST",
        f"{root_url}/liwiro/setup/reset-super-admin",
        (200,),
        headers=setup_headers(config),
        json={},
    )
    ok(f"{config['metadata']['apiName']}: default super admin is {payload.get('status', 'ready')}")
    return credentials


def signin_backend() -> str:
    payload = {
        "username": SUPER_ADMIN_USER,
        "password": SUPER_ADMIN_PASS,
        "vdb_transport": "http",
        "vdb_server_url": VDB_URL,
        "vdb_app_username": VDB_APP_USER,
        "vdb_app_password": VDB_APP_PASS,
        "liwiro_super_admin_username": SUPER_ADMIN_USER,
        "liwiro_super_admin_password": SUPER_ADMIN_PASS,
    }
    response, _ = request_json("POST", f"{BACKEND_URL}/auth/signin", (200,), json=payload)
    token = str(response.get("token") or "").strip()
    if not token:
        fail(f"Backend sign-in response had no token: {response}")
    return token


def generate_service(config: dict, platform_token: str) -> dict:
    response, _ = request_json(
        "POST",
        f"{BACKEND_URL}/generate",
        (201,),
        headers=auth_headers(platform_token),
        json=config,
    )
    process_id = str(response.get("process_id") or "").strip()
    port = str(response.get("port") or "").strip()
    if not process_id or not port:
        fail(f"Generate response missing process_id or port: {response}")
    root_url = f"http://127.0.0.1:{port}"
    wait_http(f"{root_url}/liwiro")
    ok(f"generated {config['metadata']['apiName']} on {port}")
    return {"api_name": config["metadata"]["apiName"], "process_id": process_id, "root_url": root_url}


def call_auth_service(
    root_url: str,
    endpoints: dict[str, dict],
    config: dict,
    settings: dict[str, object],
    *,
    external_ready: bool,
) -> tuple[str, tuple[str, dict] | None, list[str]]:
    admin_credentials = reset_default_super_admin(root_url, config)
    auth_config = {
        **admin_credentials,
        "audience": "liwiro",
        "expiresInSeconds": 3600,
    }
    signin = call_endpoint(root_url, "ep_signin", endpoints["ep_signin"], overrides={"body": auth_config})
    admin_token = str(find_value(signin, ("accessToken", "token", "tokenOnly")) or "").strip()
    if not admin_token:
        fail(f"Auth service sign-in returned no bearer token: {signin}")

    test_user = f"lapis.e2e.{RUN_SUFFIX}"
    test_password = "LapisE2E-Start1!"
    signup_body = {
        "username": test_user,
        "email": settings["email_to"],
        "password": test_password,
        "profile": {"fullName": "LAPIS E2E User", "timezone": "Africa/Lusaka"},
    }
    call_endpoint(root_url, "ep_signup", endpoints["ep_signup"], overrides={"body": signup_body})
    call_endpoint(root_url, "ep_me", endpoints["ep_me"], token=admin_token)

    skipped: list[str] = []
    if external_ready:
        forgot = call_endpoint(
            root_url,
            "ep_forgot_password",
            endpoints["ep_forgot_password"],
            overrides={"body": {"username": test_user, "email": settings["email_to"], "expiresInSeconds": 900}},
        )
        reset_link = str(find_value(forgot, ("resetLink",)) or "")
        reset_token = reset_link.split("token=", 1)[1] if "token=" in reset_link else ""
        if not reset_token:
            fail(f"Forgot-password response did not include its generated reset token: {forgot}")
        call_endpoint(
            root_url,
            "ep_reset_password",
            endpoints["ep_reset_password"],
            overrides={"body": {"token": reset_token, "newPassword": "LapisE2E-Reset2!"}},
        )
    else:
        skipped.extend(["ep_forgot_password", "ep_reset_password"])

    call_endpoint(root_url, "ep_users_read", endpoints["ep_users_read"], token=admin_token)
    call_endpoint(
        root_url,
        "ep_users_update",
        endpoints["ep_users_update"],
        token=admin_token,
        overrides={
            "query": {"username": test_user},
            "replace_body": {"profile": {"fullName": "LAPIS E2E User Updated", "timezone": "Africa/Lusaka"}},
        },
    )
    registered_user = f"lapis.admin.{RUN_SUFFIX}"
    call_endpoint(
        root_url,
        "ep_register_admin",
        endpoints["ep_register_admin"],
        token=admin_token,
        overrides={
            "body": {
                "username": registered_user,
                "email": f"{registered_user}@local.test",
                "password": "LapisE2E-Admin3!",
                "role": "ADMIN",
                "profile": {"fullName": "LAPIS E2E Admin"},
            }
        },
    )
    call_endpoint(
        root_url,
        "ep_users_delete",
        endpoints["ep_users_delete"],
        token=admin_token,
        overrides={"query": {"username": test_user}},
    )
    return admin_token, ("ep_signout_all", endpoints["ep_signout_all"]), skipped


def endpoint_priority(endpoint: dict) -> int:
    operation = str(endpoint.get("crudOperation") or "").lower()
    return {"create": 10, "read": 20, "update": 30, "delete": 90}.get(operation, 50)


def call_regular_service(
    root_url: str,
    config: dict,
    docs: dict[str, dict],
    bearer_token: str,
    cloud_public_ids: list[str],
    *,
    external_ready: bool,
) -> list[str]:
    declared = config.get("endpoints") or {}
    ordered_ids = sorted(declared, key=lambda endpoint_id: endpoint_priority(declared[endpoint_id]))
    skipped: list[str] = []
    for endpoint_id in ordered_ids:
        if not external_ready and endpoint_id in {"ep_contact_submit", "ep_upload_cloudinary"}:
            skipped.append(endpoint_id)
            continue
        endpoint = docs[endpoint_id]
        token = bearer_token if bool((declared.get(endpoint_id) or {}).get("requiresAuth")) else ""
        if endpoint_id == "ep_upload_cloudinary":
            body = (((declared.get(endpoint_id) or {}).get("exampleParams") or {}).get("body") or {})
            folder = str(body.get("folder") or "").strip("/")
            public_id = str(body.get("publicId") or "").strip("/")
            if public_id:
                cloud_public_ids.append(f"{folder}/{public_id}" if folder else public_id)
        payload = call_endpoint(root_url, endpoint_id, endpoint, token=token)
        if endpoint_id in {"ep_contact_submit", "ep_upload_cloudinary"}:
            assert_semantic_success(endpoint_id, payload)
    return skipped


def cloudinary_destroy(public_id: str, settings: dict[str, object]) -> None:
    timestamp = int(time.time())
    signature_source = f"public_id={public_id}&timestamp={timestamp}{settings['cloudinary_secret']}"
    signature = hashlib.sha1(signature_source.encode("utf-8")).hexdigest()
    url = f"https://api.cloudinary.com/v1_1/{settings['cloud_name']}/image/destroy"
    response = requests.post(
        url,
        data={
            "public_id": public_id,
            "timestamp": timestamp,
            "api_key": settings["cloudinary_key"],
            "signature": signature,
        },
        timeout=45,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    if response.status_code >= 300 or str(payload.get("result") or "").lower() not in {"ok", "not found"}:
        fail(f"Cloudinary cleanup failed for {public_id}: status={response.status_code}, payload={payload}")
    ok(f"Cloudinary cleanup: {public_id} -> {payload.get('result')}")


def cleanup_services(platform_token: str, expected_names: set[str]) -> list[str]:
    errors: list[str] = []
    try:
        services, _ = request_json(
            "GET",
            f"{BACKEND_URL}/services",
            (200,),
            headers={"Authorization": f"Bearer {platform_token}"},
        )
    except Exception as exc:
        return [f"could not list generated services during cleanup: {exc}"]
    for service in reversed(services if isinstance(services, list) else []):
        if not isinstance(service, dict) or str(service.get("apiName") or "") not in expected_names:
            continue
        process_id = str(service.get("processId") or service.get("process_id") or "").strip()
        if not process_id:
            errors.append(f"{service.get('apiName')}: missing process id")
            continue
        try:
            request_json(
                "DELETE",
                f"{BACKEND_URL}/services/{process_id}/delete?deleteData=true",
                (200,),
                headers=auth_headers(platform_token),
                json={},
            )
            ok(f"cleaned service {service.get('apiName')}")
        except Exception as exc:
            errors.append(f"{service.get('apiName')}: {exc}")
    return errors


def run_live(settings: dict[str, object], *, external_ready: bool) -> None:
    examples = load_examples()
    service_names = {
        str((config.get("metadata") or {}).get("apiName") or ""): (
            f"{str((config.get('metadata') or {}).get('apiName') or '')}_E2E_{RUN_SUFFIX}"
        )
        for _, config in examples
    }
    expected_names = set(service_names.values())
    platform_token = ""
    cloud_public_ids: list[str] = []
    primary_error: Exception | None = None
    auth_root = ""
    pending_signout: tuple[str, dict] | None = None
    service_token = ""
    skipped_endpoints: list[str] = []

    try:
        wait_http(f"{VDB_URL}/health")
        wait_http(f"{BACKEND_URL}/auth/status")
        platform_token = signin_backend()
        ok("backend sign-in succeeded")

        for path, raw_config in examples:
            config = prepare_config(raw_config, settings, service_names)
            service = generate_service(config, platform_token)
            docs = docs_endpoints(service["root_url"], config)
            ok(f"{path.name}: docs expose all {len(config.get('endpoints') or {})} declared endpoints")
            seed_service(service["root_url"], config)

            if bool((config.get("auth") or {}).get("isAuthService")):
                auth_root = service["root_url"]
                service_token, pending_signout, skipped = call_auth_service(
                    auth_root,
                    docs,
                    config,
                    settings,
                    external_ready=external_ready,
                )
                skipped_endpoints.extend(f"{path.name}:{endpoint_id}" for endpoint_id in skipped)
            else:
                if bool((config.get("auth") or {}).get("enabled")) and not service_token:
                    fail(f"{path.name} requires a bearer token before AuthCoreService produced one")
                skipped = call_regular_service(
                    service["root_url"],
                    config,
                    docs,
                    service_token,
                    cloud_public_ids,
                    external_ready=external_ready,
                )
                skipped_endpoints.extend(f"{path.name}:{endpoint_id}" for endpoint_id in skipped)

        if pending_signout and auth_root:
            call_endpoint(auth_root, pending_signout[0], pending_signout[1], token=service_token)
        if skipped_endpoints:
            print(
                f"[LAPIS-E2E][PARTIAL] Generated 15 examples; skipped external endpoints: {', '.join(skipped_endpoints)}",
                flush=True,
            )
        else:
            print("[LAPIS-E2E][PASS] Generated 15 examples and executed every declared endpoint.", flush=True)
    except Exception as exc:
        primary_error = exc
    finally:
        cleanup_errors: list[str] = []
        for public_id in reversed(cloud_public_ids):
            try:
                cloudinary_destroy(public_id, settings)
            except Exception as exc:
                cleanup_errors.append(str(exc))
        if platform_token:
            cleanup_errors.extend(cleanup_services(platform_token, expected_names))
        if cleanup_errors:
            cleanup_message = "; ".join(cleanup_errors)
            if primary_error:
                primary_error = RuntimeError(f"{primary_error}; cleanup errors: {cleanup_message}")
            else:
                primary_error = RuntimeError(f"Cleanup errors: {cleanup_message}")
    if primary_error:
        raise primary_error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true", help="validate files and required external credentials only")
    parser.add_argument(
        "--allow-missing-external",
        action="store_true",
        help="development-only mode: skip credential-gated external endpoints when integrations are unavailable",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = external_settings()
    examples = load_examples()
    missing = missing_external_settings(settings)
    if missing and not args.allow_missing_external:
        print("[LAPIS-E2E][FAIL] Real SMTP and Cloudinary credentials are required:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        return 2
    if args.preflight:
        print(f"[LAPIS-E2E][OK] preflight passed for {len(examples)} examples")
        return 0
    if missing:
        settings["email_to"] = settings["email_to"] or "lapis-e2e@local.test"
        settings["email_from"] = settings["email_from"] or "lapis-e2e@local.test"
    try:
        run_live(settings, external_ready=not missing)
        return 0
    except Exception as exc:
        print(f"[LAPIS-E2E][FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
