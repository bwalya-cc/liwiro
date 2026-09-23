from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
import json
import os
from typing import Any
from unittest.mock import patch

import requests

from app.validation_sandbox import ValidationSandbox, ValidationSandboxError


@dataclass
class DryRunRecorder:
    startup_events: list[dict[str, Any]] = field(default_factory=list)
    route_events: list[dict[str, Any]] = field(default_factory=list)
    route_errors: list[dict[str, Any]] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    external_mocks: list[dict[str, Any]] = field(default_factory=list)
    vdb_auth: dict[str, Any] = field(default_factory=lambda: {"ok": False, "username": "", "error": ""})
    current_phase: str = "startup"
    current_endpoint_id: str = ""
    sandbox: dict[str, Any] = field(default_factory=dict)

    def current_scope(self) -> str:
        return "route" if self.current_phase == "routes" else "startup"

    def record_event(
        self,
        action: str,
        detail: str,
        *,
        ok: bool | None = None,
        blocked: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "scope": self.current_scope(),
            "action": str(action or "").strip() or "operation",
            "detail": str(detail or "").strip() or str(action or "").strip() or "operation",
            "blocked": bool(blocked),
            "ok": ok,
            "endpointId": self.current_endpoint_id if self.current_scope() == "route" else "",
        }
        if isinstance(metadata, dict) and metadata:
            payload["metadata"] = metadata
        target = self.route_events if self.current_scope() == "route" else self.startup_events
        target.append(payload)

    def record_route_error(self, endpoint_id: str, error: str) -> None:
        self.route_errors.append({"endpointId": str(endpoint_id or "").strip(), "error": str(error or "").strip()})

    def record_external_mock(self, kind: str, target: str, *, operation: str, payload: Any = None) -> None:
        entry = {
            "kind": str(kind or "").strip() or "external",
            "operation": str(operation or "").strip() or "request",
            "target": str(target or "").strip(),
            "scope": self.current_scope(),
            "endpointId": self.current_endpoint_id if self.current_scope() == "route" else "",
        }
        if payload is not None and payload != "":
            entry["payload"] = payload
        self.external_mocks.append(entry)


def _join_route(base_path: Any, sub_path: Any) -> str:
    base = str(base_path or "").strip()
    sub = str(sub_path or "").strip()
    if base and not base.startswith("/"):
        base = f"/{base}"
    if sub and not sub.startswith("/"):
        sub = f"/{sub}"
    route = f"{base.rstrip('/')}{sub}" if sub else base
    return route or "/"


def _normalize_probe_headers(raw_headers: Any) -> dict[str, str]:
    if not isinstance(raw_headers, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw_headers.items():
        name = str(key or "").strip()
        if not name:
            continue
        out[name] = str(value or "").strip()
    return out


def _build_probe_request(endpoint: dict[str, Any]) -> dict[str, Any]:
    example_params = endpoint.get("exampleParams") if isinstance(endpoint.get("exampleParams"), dict) else {}
    body = example_params.get("body")
    if not isinstance(body, dict):
        body = {}
    query = example_params.get("query")
    if not isinstance(query, dict):
        query = {}
    headers = _normalize_probe_headers(example_params.get("headers"))
    return {
        "json": body,
        "query_string": query,
        "headers": headers,
    }


def _contains_dynamic_placeholder(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_dynamic_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_dynamic_placeholder(item) for item in value)
    if not isinstance(value, str):
        return False
    text = value.strip()
    return text.startswith("<") and text.endswith(">") and len(text) > 2


def _route_probe_for_endpoint(endpoint_id: str, endpoint: dict[str, Any], base_path: str) -> dict[str, Any]:
    method = str(endpoint.get("method") or "GET").upper()
    route = _join_route(base_path, endpoint.get("path"))
    if bool(endpoint.get("requiresAuth")):
        return {
            "endpointId": endpoint_id,
            "skip": True,
            "reason": "Skipped because endpoint requires bearer auth.",
            "method": method,
            "route": route,
        }
    request_payload = _build_probe_request(endpoint)
    if _contains_dynamic_placeholder(request_payload):
        return {
            "endpointId": endpoint_id,
            "skip": True,
            "reason": "Skipped because the example requires a value produced by an earlier runtime step.",
            "method": method,
            "route": route,
        }
    return {
        "endpointId": endpoint_id,
        "skip": False,
        "method": method,
        "route": route,
        **request_payload,
    }


def _summarize_vdb_action(query: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(query, dict) or not query:
        return "vql", "empty query"
    if isinstance(query.get("action"), str):
        operation = str(query.get("action") or "").strip().lower()
        collection = str(query.get("collection") or "").strip()
        if operation in {"domain_status", "domain_suspend", "domain_resume"}:
            return operation, str(query.get("domain") or query.get("name") or "").strip()
        if operation in {"create_index", "drop_index"}:
            field = str(query.get("field") or "").strip()
            return operation, ".".join(part for part in [collection, field] if part)
        if operation in {"list_indexes", "rebuild_indexes"}:
            return operation, collection
        flat_detail = collection or str(query.get("resource") or query.get("model") or query.get("name") or "").strip()
        return operation or "vql", flat_detail

    action, payload = next(iter(query.items()))
    action_name = str(action or "").strip()
    if action_name == "define" and isinstance(payload, dict):
        if "domain" in payload:
            return "define_domain", str(payload.get("domain") or "").strip()
        if "db" in payload:
            return "define_database", str(payload.get("db") or "").strip()
    if action_name == "use" and isinstance(payload, dict):
        if "domain" in payload:
            return "use_domain", str(payload.get("domain") or "").strip()
        if "db" in payload:
            return "use_database", str(payload.get("db") or "").strip()
    if action_name == "list":
        target = str(payload or "").strip()
        mapping = {
            "domains": "list_domains",
            "dbs": "list_databases",
            "collections": "list_collections",
        }
        return mapping.get(target, "list"), target or "list"
    if action_name == "create" and isinstance(payload, dict) and payload:
        collection_name, value = next(iter(payload.items()))
        if isinstance(value, dict) and (
            "schema" in value
            or (
                value
                and all(
                    isinstance(child_value, dict) and ("type" in child_value or "required" in child_value)
                    for child_value in value.values()
                )
            )
        ):
            return "create_collection", str(collection_name or "").strip()
        return "create_document", str(collection_name or "").strip()
    if action_name == "read":
        return "read_documents", str(payload or "").strip()
    if action_name == "update" and isinstance(payload, dict) and payload:
        return "update_document", str(next(iter(payload.keys())) or "").strip()
    if action_name == "delete" and isinstance(payload, dict) and payload:
        return "delete_document", str(next(iter(payload.keys())) or "").strip()
    if action_name == "drop" and isinstance(payload, dict):
        if "domain" in payload:
            return "drop_domain", str(payload.get("domain") or "").strip()
        if "db" in payload:
            return "drop_database", str(payload.get("db") or "").strip()
        if "collection" in payload:
            return "drop_collection", str(payload.get("collection") or "").strip()
    if action_name == "createIndex" and isinstance(payload, dict):
        collection = str(payload.get("collection") or "").strip()
        field = str(payload.get("field") or "").strip()
        return "create_index", ".".join(part for part in [collection, field] if part)
    if action_name == "aggregate":
        return "aggregate", str(payload or "").strip()
    if action_name == "script" and isinstance(payload, dict):
        create_payload = payload.get("create") if isinstance(payload.get("create"), dict) else {}
        execute_payload = payload.get("execute") if isinstance(payload.get("execute"), dict) else {}
        if create_payload:
            return "create_script", str(create_payload.get("name") or "").strip()
        if execute_payload:
            return "execute_script", str(execute_payload.get("name") or "").strip()
    return "vql", json.dumps(query, sort_keys=True)[:400]


def _mock_http_response(method: str, url: str, payload: Any) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response.url = str(url or "").strip()
    response.headers["Content-Type"] = "application/json"
    response._content = json.dumps(
        {
            "ok": True,
            "mocked": True,
            "method": str(method or "").upper(),
            "url": str(url or "").strip(),
            "message": "Validation sandbox mocked outbound HTTP request.",
            "payload": payload if payload is not None and payload != "" else {},
        }
    ).encode("utf-8")
    return response


@contextmanager
def _dry_run_environment(recorder: DryRunRecorder):
    from app.vdb import VDBClient

    sandbox = ValidationSandbox.create()
    sandbox.start()
    recorder.sandbox = sandbox.describe()

    original_authenticate = VDBClient.authenticate
    original_execute_vql_query = VDBClient.execute_vql_query
    original_ensure_workspace = VDBClient.ensure_workspace
    original_request = requests.sessions.Session.request

    def patched_authenticate(self):
        ok = original_authenticate(self)
        recorder.vdb_auth = {
            "ok": bool(ok),
            "username": str(getattr(self, "username", "") or ""),
            "error": "" if ok else "Sandbox VDB authentication failed during dry-run validation.",
        }
        recorder.record_event(
            "authenticate",
            str(getattr(self, "username", "") or ""),
            ok=bool(ok),
        )
        return ok

    def tracked_ensure_workspace(self, domain_name: str, db_name: str = "main"):
        detail = f"{str(domain_name or '').strip()}/{str(db_name or '').strip()}"
        try:
            ok = original_ensure_workspace(self, domain_name, db_name)
            recorder.record_event("ensure_workspace", detail, ok=bool(ok))
            return ok
        except Exception as exc:
            recorder.record_event("ensure_workspace", detail, ok=False, metadata={"error": str(exc)})
            raise

    def tracked_execute_vql_query(self, query: dict):
        action, detail = _summarize_vdb_action(query)
        try:
            ok, result = original_execute_vql_query(self, query)
            metadata: dict[str, Any] = {}
            if not ok and isinstance(result, dict):
                metadata["error"] = str(result.get("error") or "").strip()
            recorder.record_event(action, detail, ok=bool(ok), metadata=metadata or None)
            return ok, result
        except Exception as exc:
            recorder.record_event(action, detail, ok=False, metadata={"error": str(exc)})
            raise

    def sandboxed_request(session, method, url, *args, **kwargs):
        target_url = str(url or "").strip()
        if sandbox.allows_request(target_url):
            return original_request(session, method, url, *args, **kwargs)
        payload = kwargs.get("json")
        if payload is None or payload == "":
            payload = kwargs.get("data")
        recorder.record_external_mock(
            "http",
            target_url,
            operation=str(method or "").upper(),
            payload=payload,
        )
        recorder.notices.append(f"Validation sandbox mocked outbound HTTP request: {str(method or '').upper()} {target_url}")
        return _mock_http_response(str(method or "").upper(), target_url, payload)

    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, sandbox.env_overrides(), clear=False))
        stack.enter_context(patch.object(VDBClient, "authenticate", patched_authenticate))
        stack.enter_context(patch.object(VDBClient, "ensure_workspace", tracked_ensure_workspace))
        stack.enter_context(patch.object(VDBClient, "execute_vql_query", tracked_execute_vql_query))
        stack.enter_context(patch.object(requests.sessions.Session, "request", new=sandboxed_request))
        try:
            yield sandbox
        finally:
            pass


def _collect_route_payload_mocks(recorder: DryRunRecorder, response) -> None:
    try:
        payload = response.get_json(silent=True)
    except Exception:
        payload = None
    if not isinstance(payload, dict):
        return
    external_mocks = payload.get("dryRunExternalMocks")
    if not isinstance(external_mocks, list):
        return
    for entry in external_mocks:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "external").strip().lower()
        operation = str(entry.get("operation") or "call").strip()
        target = str(entry.get("target") or "").strip()
        if kind == "http":
            recorder.notices.append(f"Validation sandbox mocked outbound HTTP request: {operation} {target}".strip())
        elif kind == "email":
            recorder.notices.append(f"Validation sandbox mocked outbound email delivery: {target or operation}".strip())
        else:
            recorder.notices.append(f"Validation sandbox mocked {kind} side effect: {operation} {target}".strip())
        recorder.external_mocks.append(
            {
                **entry,
                "scope": "route",
                "endpointId": recorder.current_endpoint_id,
            }
        )


def _attach_sandbox_metadata(result: dict[str, Any], sandbox: ValidationSandbox | None) -> dict[str, Any]:
    if sandbox is None:
        return result
    sandbox_info = sandbox.describe()
    result["sandbox"] = sandbox_info
    result["sandboxId"] = sandbox_info.get("sandboxId") or ""
    result["logsPath"] = sandbox_info.get("logsPath") or ""
    result["summaryPath"] = sandbox_info.get("summaryPath") or ""
    result["snapshotPath"] = sandbox_info.get("snapshotPath") or ""
    return result


def validate_generated_service_dry_run(lapis_config: dict[str, Any]) -> dict[str, Any]:
    from generators.api_generator import generate_api_service

    recorder = DryRunRecorder()
    metadata = lapis_config.get("metadata") if isinstance(lapis_config.get("metadata"), dict) else {}
    base_path = str(metadata.get("basePath") or "").strip()
    endpoint_results: list[dict[str, Any]] = []
    sandbox: ValidationSandbox | None = None

    try:
        with _dry_run_environment(recorder) as active_sandbox:
            sandbox = active_sandbox
            app = generate_api_service(lapis_config)
            # LAPIS examples may probe records declared in metadata.seedData
            # (for example the password-reset example looks up a seeded user).
            # Generation intentionally does not mutate a real workspace, so
            # populate the isolated validation workspace through the same
            # authenticated setup route before exercising endpoint probes.
            seed_cfg = lapis_config.get("metadata", {}).get("seedData") if isinstance(lapis_config.get("metadata"), dict) else {}
            if isinstance(seed_cfg, dict) and bool(seed_cfg.get("enabled")) and isinstance(seed_cfg.get("collections"), dict):
                seed_key = str(lapis_config.get("metadata", {}).get("setupApiKey") or "").strip()
                if seed_key:
                    seed_client = app.test_client()
                    seed_response = seed_client.post(
                        "/liwiro/setup/seed-db",
                        json={"collections": seed_cfg.get("collections")},
                        headers={"X-Liwiro-Setup-Key": seed_key},
                    )
                    seed_payload = seed_response.get_json(silent=True)
                    seed_summary = seed_payload.get("summary") if isinstance(seed_payload, dict) else {}
                    seed_ok = (
                        seed_response.status_code < 400
                        and isinstance(seed_payload, dict)
                        and isinstance(seed_summary, dict)
                        and int(seed_summary.get("failed") or 0) == 0
                    )
                    recorder.record_event(
                        "seed_workspace",
                        "metadata.seedData",
                        ok=seed_ok,
                        metadata=None if seed_ok else {"statusCode": seed_response.status_code, "response": seed_payload or seed_response.get_data(as_text=True)[:1000]},
                    )
                    if not seed_ok:
                        recorder.notices.append("Validation sandbox could not seed metadata.seedData before endpoint probes.")
            recorder.current_phase = "routes"
            client = app.test_client()
            for endpoint_id, endpoint in (lapis_config.get("endpoints") or {}).items():
                if not isinstance(endpoint, dict):
                    continue
                probe = _route_probe_for_endpoint(str(endpoint_id), endpoint, base_path)
                if probe.get("skip"):
                    endpoint_results.append(probe)
                    continue
                recorder.current_endpoint_id = probe["endpointId"]
                response = client.open(
                    probe["route"],
                    method=probe["method"],
                    json=probe.get("json") if isinstance(probe.get("json"), dict) else {},
                    query_string=probe.get("query_string") if isinstance(probe.get("query_string"), dict) else {},
                    headers=probe.get("headers") if isinstance(probe.get("headers"), dict) else {},
                )
                _collect_route_payload_mocks(recorder, response)
                payload_text = response.get_data(as_text=True)
                result = {
                    "endpointId": probe["endpointId"],
                    "route": probe["route"],
                    "method": probe["method"],
                    "statusCode": response.status_code,
                    "ok": response.status_code < 400,
                }
                if response.status_code >= 400:
                    result["error"] = payload_text[:4000] or f"Dry-run request failed with status {response.status_code}"
                    recorder.record_route_error(probe["endpointId"], result["error"])
                endpoint_results.append(result)
                recorder.current_endpoint_id = ""
    except ValidationSandboxError as exc:
        recorder.notices.append(str(exc))
        errors = [f"Validation sandbox failed to start: {exc}"]
        result = {
            "ok": False,
            "errors": errors,
            "endpointResults": endpoint_results,
            "startupEvents": recorder.startup_events,
            "routeEvents": recorder.route_events,
            "notices": recorder.notices,
            "vdbAuth": recorder.vdb_auth,
            "externalMocks": recorder.external_mocks,
            "sandbox": recorder.sandbox,
        }
        if sandbox is not None:
            sandbox.finalize(success=False, summary=result)
        return _attach_sandbox_metadata(result, sandbox)
    except Exception as exc:
        errors = [f"Dry-run startup failed in sandbox: {exc}"]
        result = {
            "ok": False,
            "errors": errors,
            "endpointResults": endpoint_results,
            "startupEvents": recorder.startup_events,
            "routeEvents": recorder.route_events,
            "notices": recorder.notices,
            "vdbAuth": recorder.vdb_auth,
            "externalMocks": recorder.external_mocks,
            "sandbox": recorder.sandbox,
        }
        if sandbox is not None:
            sandbox.finalize(success=False, summary=result)
        return _attach_sandbox_metadata(result, sandbox)

    errors = []
    if not recorder.vdb_auth.get("ok"):
        errors.append(str(recorder.vdb_auth.get("error") or "Sandbox VDB authentication failed during dry-run validation."))
    for route_error in recorder.route_errors:
        errors.append(f"Endpoint '{route_error.get('endpointId')}' failed dry-run validation in sandbox: {route_error.get('error')}")

    result = {
        "ok": not errors,
        "errors": errors,
        "endpointResults": endpoint_results,
        "startupEvents": recorder.startup_events,
        "routeEvents": recorder.route_events,
        "notices": recorder.notices,
        "vdbAuth": recorder.vdb_auth,
        "externalMocks": recorder.external_mocks,
        "sandbox": recorder.sandbox,
    }
    if sandbox is not None:
        sandbox.finalize(success=not errors, summary=result)
    return _attach_sandbox_metadata(result, sandbox)


def detect_dry_run_versa_blockers(script_code: str) -> list[str]:
    del script_code
    return []
