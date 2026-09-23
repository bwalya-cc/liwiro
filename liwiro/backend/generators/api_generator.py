# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from datetime import datetime, timezone
from functools import wraps
from html import escape
import hashlib
import json
import os
import re
import requests
import subprocess
import tempfile
import textwrap
import threading
import time
from typing import Any, Tuple

from flask import Flask, current_app, jsonify, request, Response
from flask.json.provider import DefaultJSONProvider
from werkzeug.security import check_password_hash, generate_password_hash
try:
    import jwt  # type: ignore
except Exception:
    jwt = None

from app.auth_data import load_normalized_auth_data
from config import (
    Config,
    normalize_lapis_config_contract,
    normalize_lapis_crud_operation,
    normalize_lapis_operation_type,
)
from utils.service_capabilities import normalize_config_env, summarize_media_capabilities

_SCRIPT_RESULT_MARKER = "__LIWIRO_RESULT__"
_VI_REQUIRED_MODULE_IMPORTS = ("json_xml", "vdb", "http", "email", "crypto", "jwt", "time", "datetime")
_RUNTIME_SERVICE_ENV_KEYS = (
    "EMAIL_SMTP_HOST",
    "EMAIL_SMTP_PORT",
    "EMAIL_SMTP_STARTTLS",
    "EMAIL_SMTP_SSL",
    "EMAIL_SMTP_AUTH",
    "EMAIL_SMTP_USERNAME",
    "EMAIL_SMTP_PASSWORD",
    "EMAIL_FROM",
    "EMAIL_TO",
    "PASSWORD_RESET_URL",
    "PORT",
)
_VI_MODULE_IMPORT_PATTERN = re.compile(r"^\s*([A-Za-z_]\w*)\s+import\s+.+;?\s*$")
_VI_NAMESPACE_IMPORT_PATTERN = re.compile(r"^\s*import\s+([A-Za-z_]\w*)\s*;?\s*$")


def build_service_preview_bundle(lapis_config: dict) -> dict[str, str]:
    lapis_config = normalize_lapis_config_contract(lapis_config)
    metadata = lapis_config.get("metadata") or {}
    api_name = str(metadata.get("apiName") or "GeneratedService").strip() or "GeneratedService"
    def _preview_env_line(key: str, value: Any) -> str:
        escaped = str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        return f'{key}="{escaped}"'
    env_text = "\n".join(
        _preview_env_line(key, value)
        for key, value in sorted((_normalize_service_env(metadata.get("env")) or {}).items())
    )
    route_summary = []
    for endpoint_id, endpoint_cfg in (lapis_config.get("endpoints") or {}).items():
        if not isinstance(endpoint_cfg, dict):
            continue
        route_summary.append(
            {
                "id": endpoint_id,
                "method": str(endpoint_cfg.get("method") or "GET").upper(),
                "path": str(endpoint_cfg.get("path") or "").strip(),
                "operationType": str(endpoint_cfg.get("operationType") or "").strip(),
                "linkedModel": str(endpoint_cfg.get("linkedModel") or "").strip(),
                "crudOperation": str(endpoint_cfg.get("crudOperation") or "").strip(),
                "requiresAuth": bool(endpoint_cfg.get("requiresAuth", False)),
            }
        )

    embedded_config = json.dumps(lapis_config, indent=2, sort_keys=False)
    route_summary_json = json.dumps(route_summary, indent=2, sort_keys=False)
    app_source = textwrap.dedent(
        f"""\
        # Auto-generated Liwiro preview wrapper.
        # This preview shows the code path the service generator uses at runtime.

        from generators.api_generator import generate_api_service

        LAPIS_CONFIG = {embedded_config}

        app = generate_api_service(LAPIS_CONFIG)

        if __name__ == "__main__":
            from waitress import serve

            metadata = LAPIS_CONFIG.get("metadata") or {{}}
            env = metadata.get("env") or {{}}
            port = int(str(env.get("PORT") or 5001))
            serve(app, host="127.0.0.1", port=port)
        """
    )
    readme = textwrap.dedent(
        f"""\
        # {api_name} Preview

        This folder is an inspectable preview of what Liwiro would run for `{api_name}`.

        Files:
        - `app.py`: generated wrapper that calls `generate_api_service(...)`
        - `lapis_config.json`: normalized LAPIS payload used to build the service
        - `route_summary.json`: endpoint summary extracted from LAPIS
        - `.env`: materialized service environment derived from `metadata.env`

        This preview does not start the service automatically.
        """
    )
    return {
        "app.py": app_source,
        "lapis_config.json": embedded_config + "\n",
        "route_summary.json": route_summary_json + "\n",
        ".env": env_text + ("\n" if env_text else ""),
        "README.md": readme,
    }


def _ensure_vi_module_imports(script_code: Any) -> str:
    code = str(script_code or "")
    if not code.strip():
        return code

    kept_lines = []
    ordered_imports = []
    seen_modules = set()

    for raw_line in code.splitlines():
        module_name = ""
        match = _VI_MODULE_IMPORT_PATTERN.match(raw_line)
        namespace_match = _VI_NAMESPACE_IMPORT_PATTERN.match(raw_line)
        if match:
            module_name = str(match.group(1) or "").strip().lower()
        elif namespace_match:
            module_name = str(namespace_match.group(1) or "").strip().lower()
        else:
            kept_lines.append(raw_line)
            continue
        if not module_name or module_name in seen_modules:
            continue
        seen_modules.add(module_name)
        normalized_line = raw_line.strip()
        if not normalized_line.endswith(";"):
            normalized_line = f"{normalized_line};"
        ordered_imports.append((module_name, normalized_line))

    by_module = {module: line for module, line in ordered_imports}
    final_import_lines = []

    # Keep required imports in canonical order at top.
    for module in _VI_REQUIRED_MODULE_IMPORTS:
        final_import_lines.append(by_module.get(module, f"{module} import *;"))

    # Preserve additional user imports after required imports.
    for module, line in ordered_imports:
        if module in _VI_REQUIRED_MODULE_IMPORTS:
            continue
        final_import_lines.append(line)

    body = "\n".join(kept_lines).strip("\n")
    if body:
        return f"{'\n'.join(final_import_lines)}\n\n{body}"
    return "\n".join(final_import_lines)


def _detect_dry_run_versa_blockers(script_code: Any) -> list[str]:
    del script_code
    return []


def _strip_vi_import_lines(script_code: Any) -> str:
    code = str(script_code or "")
    if not code.strip():
        return ""
    kept = []
    for raw_line in code.splitlines():
        if _VI_MODULE_IMPORT_PATTERN.match(raw_line) or _VI_NAMESPACE_IMPORT_PATTERN.match(raw_line):
            continue
        kept.append(raw_line)
    return "\n".join(kept).strip("\n")


def _split_vi_import_lines(script_code: Any) -> tuple[list[str], str]:
    code = str(script_code or "")
    if not code.strip():
        return [], ""
    import_lines = []
    body_lines = []
    seen = set()
    for raw_line in code.splitlines():
        module_name = ""
        if match := _VI_MODULE_IMPORT_PATTERN.match(raw_line):
            module_name = str(match.group(1) or "").strip().lower()
        elif match := _VI_NAMESPACE_IMPORT_PATTERN.match(raw_line):
            module_name = str(match.group(1) or "").strip().lower()
        if module_name:
            normalized_line = raw_line.strip()
            if not normalized_line.endswith(";"):
                normalized_line = f"{normalized_line};"
            if normalized_line not in seen:
                import_lines.append(normalized_line)
                seen.add(normalized_line)
            continue
        body_lines.append(raw_line)
    return import_lines, "\n".join(body_lines).strip("\n")


def _imported_vi_module_name(import_line: str) -> str:
    line = str(import_line or "").strip()
    if match := _VI_MODULE_IMPORT_PATTERN.match(line):
        return str(match.group(1) or "").strip().lower()
    if match := _VI_NAMESPACE_IMPORT_PATTERN.match(line):
        return str(match.group(1) or "").strip().lower()
    return ""


def _dry_run_vi_mock_prelude() -> list[str]:
    return [
        "let __liwiro_mock_files = {};",
        "func __liwiro_mock_http(method, url, options) {",
        "  let safeOptions = options ?? {};",
        "  __liwiro_mock_calls.add({kind: \"http\", operation: method, target: url, payload: safeOptions});",
        "  let body = {ok: true, mocked: true, method: method, url: url};",
        "  return {",
        "    ok: true,",
        "    mocked: true,",
        "    status: 200,",
        "    method: method,",
        "    url: url,",
        "    headers: {\"Content-Type\": \"application/json\"},",
        "    body: json_xml.to_json(body),",
        "    json: body,",
        "    data: body",  # keep mocked JSON payload accessible to validation callers
        "  };",
        "}",
        "func __liwiro_mock_filer(operation, path, content) {",
        "  let safePath = str(path ?? \"sandbox-file\");",
        "  let redirectedPath = \"/validation-sandbox/\" + safePath;",
        "  if (operation == \"delete\") {",
        "    __liwiro_mock_files[redirectedPath] = null;",
        "  } else {",
        "    __liwiro_mock_files[redirectedPath] = content;",
        "  }",
        "  __liwiro_mock_calls.add({kind: \"file\", operation: operation, target: redirectedPath, payload: content});",
        "  return {",
        "    ok: true,",
        "    mocked: true,",
        "    status: \"success\",",
        "    operation: \"filer.\" + operation,",
        "    message: \"Validation sandbox redirected filesystem mutation.\",",
        "    path: redirectedPath,",
        "    context: {sandbox: true}",
        "  };",
        "}",
        "let http = {",
        "  request: func(method, url, options) { return __liwiro_mock_http(method, url, options); },",
        "  get: func(url, options) { return __liwiro_mock_http(\"GET\", url, options); },",
        "  post: func(url, options) { return __liwiro_mock_http(\"POST\", url, options); },",
        "  put: func(url, options) { return __liwiro_mock_http(\"PUT\", url, options); },",
        "  patch: func(url, options) { return __liwiro_mock_http(\"PATCH\", url, options); },",
        "  delete: func(url, options) { return __liwiro_mock_http(\"DELETE\", url, options); }",
        "};",
        "let email = {",
        "  send: func(options) {",
        "    let safeOptions = options ?? {};",
        "    __liwiro_mock_calls.add({kind: \"email\", operation: \"send\", target: str(safeOptions.to ?? safeOptions[\"to\"] ?? \"\"), payload: safeOptions});",
        "    return {",
        "      ok: true,",
        "      mocked: true,",
        "      status: \"success\",",
        "      operation: \"email.send\",",
        "      message: \"Validation sandbox mocked email delivery.\",",
        "      data: {accepted: true, mocked: true},",
        "      context: {sandbox: true}",
        "    };",
        "  }",
        "};",
        "let filer = {",
        "  write: func(path, content) { return __liwiro_mock_filer(\"write\", path, content); },",
        "  append: func(path, content) { return __liwiro_mock_filer(\"append\", path, content); },",
        "  save: func(path, content) { return __liwiro_mock_filer(\"save\", path, content); },",
        "  delete: func(path) { return __liwiro_mock_filer(\"delete\", path, null); }",
        "};",
        "let mediacloud = {",
        "  status: func() {",
        "    __liwiro_mock_calls.add({kind: \"mediacloud\", operation: \"status\", target: \"cloudinary\", payload: {}});",
        "    return {ok: true, mocked: true, status: \"ready\", provider: \"cloudinary\", configured: true};",
        "  },",
        "  upload: func(options) {",
        "    let safeOptions = options ?? {};",
        "    __liwiro_mock_calls.add({kind: \"mediacloud\", operation: \"upload\", target: \"cloudinary\", payload: safeOptions});",
        "    return {",
        "      ok: true, mocked: true, status: \"success\", provider: \"cloudinary\",",
        "      providerAssetId: \"dry-run-asset\", filename: \"dry-run-upload.bin\",",
        "      mimeType: \"application/octet-stream\", storageBucket: \"validation\",",
        "      storagePath: \"validation/dry-run-asset\", publicUrl: \"https://validation.invalid/dry-run-asset\",",
        "      secureUrl: \"https://validation.invalid/dry-run-asset\", sizeBytes: 0,",
        "      providerResponse: {mocked: true}",
        "    };",
        "  },",
        "  remove: func(options) {",
        "    let safeOptions = options ?? {};",
        "    __liwiro_mock_calls.add({kind: \"mediacloud\", operation: \"remove\", target: \"cloudinary\", payload: safeOptions});",
        "    return {ok: true, mocked: true, status: \"success\", provider: \"cloudinary\", removed: true};",
        "  },",
        "  list: func(options) {",
        "    let safeOptions = options ?? {};",
        "    __liwiro_mock_calls.add({kind: \"mediacloud\", operation: \"list\", target: \"cloudinary\", payload: safeOptions});",
        "    return {ok: true, mocked: true, status: \"success\", provider: \"cloudinary\", assets: []};",
        "  }",
        "};",
    ]


def _script_http_status(result: Any) -> int:
    if isinstance(result, dict):
        explicit_status = _coerce_int(
            result.get("statusCode")
            or result.get("status_code")
            or result.get("httpStatus")
            or result.get("http_status")
        )
        if explicit_status is not None and 100 <= explicit_status <= 599:
            return explicit_status
        if result.get("authenticated") is False:
            return 401
        if result.get("authorized") is False or result.get("forbidden") is True:
            return 403
        if result.get("notFound") is True:
            return 404
        if result.get("ok") is False or result.get("success") is False:
            reason = str(result.get("reason") or result.get("error") or result.get("message") or "").strip().lower()
            if "not found" in reason:
                return 404
            if "already exists" in reason or "duplicate" in reason or "conflict" in reason:
                return 409
            if "forbidden" in reason or "not allowed" in reason or "super admin" in reason or "super-admin" in reason:
                return 403
            return 400
        if result.get("created") is False or result.get("updated") is False or result.get("deleted") is False:
            reason = str(result.get("reason") or result.get("error") or result.get("message") or "").strip().lower()
            if "not found" in reason:
                return 404
            if "already exists" in reason or "duplicate" in reason or "conflict" in reason:
                return 409
            if "forbidden" in reason or "not allowed" in reason or "super admin" in reason or "super-admin" in reason:
                return 403
            return 400
    return 200


def _coerce_int(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def _extract_result_count(result: Any, *keys: str) -> int | None:
    if not isinstance(result, dict):
        return None
    search_spaces = [result]
    context = result.get("context")
    if isinstance(context, dict):
        search_spaces.append(context)
    for space in search_spaces:
        for key in keys:
            if key not in space:
                continue
            numeric = _coerce_int(space.get(key))
            if numeric is not None:
                return numeric
    return None


def _is_vdb_script_metadata_echo(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    required = {"name", "service", "language", "extension", "last_edited", "params"}
    return required.issubset(set(result.keys())) and str(result.get("extension")) == ".versa"


def _normalize_vi_script_route_body(script_code: str) -> str:
    normalized_lines = []
    object_assignment_indent_stack = []
    return_object_indent_stack = []
    for raw_line in str(script_code).splitlines():
        stripped = raw_line.strip()
        if not stripped:
            normalized_lines.append(raw_line)
            continue

        indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        indent_len = len(indent)

        if stripped.startswith("let ") and stripped.endswith("{") and "=" in stripped:
            object_assignment_indent_stack.append(indent_len)
        if stripped.startswith("return {") and not stripped.endswith("};"):
            return_object_indent_stack.append(indent_len)

        if (
            stripped
            and stripped.startswith("{")
            and stripped.endswith("}")
            and not stripped.startswith("return ")
            and not stripped.startswith("throw ")
        ):
            raw_line = f"{indent}return {stripped}"
            stripped = raw_line.strip()

        if stripped.startswith("return {") and stripped.endswith("}") and not stripped.endswith("};"):
            raw_line = f"{raw_line};"
            stripped = raw_line.strip()

        object_assignment_close = stripped.rstrip(";").strip() == "}"
        if object_assignment_close and object_assignment_indent_stack and indent_len == object_assignment_indent_stack[-1]:
            if not stripped.endswith(";"):
                raw_line = f"{raw_line};"
                stripped = raw_line.strip()
            object_assignment_indent_stack.pop()
        return_object_close = stripped.rstrip(";").strip() == "}"
        if return_object_close and return_object_indent_stack and indent_len == return_object_indent_stack[-1]:
            if not stripped.endswith(";"):
                raw_line = f"{raw_line};"
                stripped = raw_line.strip()
            return_object_indent_stack.pop()

        if (
            stripped
            and return_object_indent_stack
            and indent_len > return_object_indent_stack[-1]
            and not stripped.startswith("#")
            and not stripped.endswith((",", "{", "}", ";"))
            and not stripped.startswith(("if ", "else", "func ", "while ", "for ", "try", "catch "))
        ):
            raw_line = f"{raw_line},"
            stripped = raw_line.strip()

        # VI parser in fallback mode is strict about semicolons; many generated
        # LAPIS scripts omit them. Add semicolons for simple statement lines.
        if (
            stripped
            and not stripped.startswith("#")
            and not stripped.endswith((";", "{", "}", ","))
            and not stripped.startswith(("if ", "else", "func ", "while ", "for ", "try", "catch "))
            and not (object_assignment_indent_stack and indent_len > object_assignment_indent_stack[-1])
            and not (return_object_indent_stack and indent_len > return_object_indent_stack[-1])
        ):
            raw_line = f"{raw_line};"
        normalized_lines.append(raw_line)
    return "\n".join(normalized_lines)


def _execute_vi_script(script_code: str, params: dict, service_db: str) -> Tuple[bool, dict]:
    if not script_code or not str(script_code).strip():
        return False, {"error": "Missing script source"}
    script_code = _ensure_vi_module_imports(script_code)
    # Older LAPIS snippets used Python's ``time.time()`` spelling. Stored
    # scripts execute in the nested Versa evaluator, where that legacy member
    # can be shadowed by request data; use the stable datetime module instead.
    script_code = script_code.replace("time.time()", "datetime.now().isoformat()")
    dry_run_mock_mode = (
        str(os.getenv("LIWIRO_DRY_RUN_VALIDATION") or "").strip() == "1"
        and str(os.getenv("LIWIRO_DRY_RUN_SANDBOX_MODE") or "").strip() == "1"
    )

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    vi_jar = os.path.join(repo_root, "verun", "vi", "target", "vi-1.0.0-jar-with-dependencies.jar")
    if not os.path.isfile(vi_jar):
        return False, {
            "error": f"VI runtime jar missing at {vi_jar}",
            "errorType": "VsiRuntimeJarMissingError",
            "code": "VI_RUNTIME_JAR_MISSING",
            "hint": "Build it with: mvn -pl vi -am -DskipTests package",
            "path": vi_jar,
        }

    internal_runtime = params.get("__liwiro_vdb_runtime") if isinstance(params, dict) else {}
    auth_payload = {
        "user": (internal_runtime or {}).get("user") or os.getenv("VDB_USERNAME") or Config.VDB_USERNAME,
        "pass": (internal_runtime or {}).get("pass") or os.getenv("VDB_PASSWORD") or Config.VDB_PASSWORD,
    }
    service_info = params.get("service") if isinstance(params, dict) else {}
    service_domain = str(
        (service_info or {}).get("name")
        or (internal_runtime or {}).get("domain")
        or Config.LIWIRO_DOMAIN
    ).strip() or Config.LIWIRO_DOMAIN
    context_payload = {
        "domain": service_domain,
        "database": (service_info or {}).get("database") or (internal_runtime or {}).get("db") or service_db or Config.LIWIRO_DB,
    }

    params_json_literal = json.dumps(json.dumps(params, separators=(",", ":"), ensure_ascii=False))
    auth_json_literal = json.dumps(json.dumps(auth_payload, separators=(",", ":"), ensure_ascii=False))
    context_json_literal = json.dumps(json.dumps(context_payload, separators=(",", ":"), ensure_ascii=False))
    import_lines, script_body = _split_vi_import_lines(script_code)
    mock_modules = {"http", "email", "filer", "mediacloud"} if dry_run_mock_mode else set()
    custom_import_lines = [
        line for line in import_lines
        if _imported_vi_module_name(line) not in mock_modules
        if not any(
            line.startswith(f"{module} import ") or line == f"import {module};"
            for module in _VI_REQUIRED_MODULE_IMPORTS
        )
    ]
    normalized_script = _normalize_vi_script_route_body(script_body)
    indented_script = "\n".join(f"  {line}" for line in normalized_script.splitlines())
    required_import_lines = [
        "json_xml import *;",
        "vdb import *;",
        "crypto import *;",
        "jwt import *;",
        "time import *;",
        "datetime import *;",
    ]
    if not dry_run_mock_mode:
        required_import_lines.insert(2, "http import *;")
        required_import_lines.insert(3, "email import *;")

    runtime_script = "".join(
        [
            *[f"{line}\n" for line in required_import_lines],
            *[f"{line}\n" for line in custom_import_lines],
            "let __liwiro_mock_calls = [];\n",
            *([f"{line}\n" for line in _dry_run_vi_mock_prelude()] if dry_run_mock_mode else []),
            f"let __liwiro_params_json = {params_json_literal};\n",
            "let params = json_xml.parse_json(__liwiro_params_json);\n",
            "let service = params.service ?? {};\n",
            "let auth = params.auth ?? {};\n",
            f"let __liwiro_vdb_auth = json_xml.parse_json({auth_json_literal});\n",
            "let __liwiro_auth_res = vdb.auth(__liwiro_vdb_auth);\n",
            f"let __liwiro_vdb_ctx = json_xml.parse_json({context_json_literal});\n",
            "if ((__liwiro_auth_res.ok ?? true) == false || ((__liwiro_auth_res.status ?? \"\") == \"error\")) {\n",
            f'  print("{_SCRIPT_RESULT_MARKER}" + json_xml.to_json({{error: "VDB auth failed in VI fallback", auth: __liwiro_auth_res}}));\n',
            "} else {\n",
            "  let __liwiro_ctx_res = vdb.set(__liwiro_vdb_ctx);\n",
            "  if ((__liwiro_ctx_res.ok ?? true) == false || ((__liwiro_ctx_res.status ?? \"\") == \"error\")) {\n",
            f'    print("{_SCRIPT_RESULT_MARKER}" + json_xml.to_json({{error: "VDB context set failed in VI fallback", context: __liwiro_vdb_ctx, contextResult: __liwiro_ctx_res, auth: __liwiro_auth_res}}));\n',
            "  } else {\n",
            "    func __liwiro_route(params) {\n",
            f"{indented_script}\n",
            "    }\n",
            "    let __liwiro_result = __liwiro_route(params);\n",
            "    let __liwiro_payload = __liwiro_result;\n",
            "    if (leng(__liwiro_mock_calls ?? []) > 0) {\n",
            "      if (type(__liwiro_payload) == \"object\") {\n",
            "        __liwiro_payload[\"dryRunExternalMocks\"] = __liwiro_mock_calls;\n",
            "      } else {\n",
            "        __liwiro_payload = {result: __liwiro_result, dryRunExternalMocks: __liwiro_mock_calls};\n",
            "      }\n",
            "    }\n",
            f'    print("{_SCRIPT_RESULT_MARKER}" + json_xml.to_json(__liwiro_payload));\n',
            "  }\n",
            "}\n",
        ]
    )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".versa", delete=False, encoding="utf-8") as handle:
            tmp_path = handle.name
            handle.write(runtime_script)

        proc = subprocess.run(
            ["java", "-cp", vi_jar, "verun.runtime.Main", tmp_path, "--msg-only"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
            env={
                **os.environ,
                "VI_CUSTOM_MODULES_DIR": str(
                    current_app.config.get("VI_CUSTOM_MODULES_DIR")
                    or getattr(Config, "VI_CUSTOM_MODULES_DIR", "")
                    or ""
                ),
                "LIWIRO_VI_MODULE_DOMAIN": service_domain,
            },
        )
        if proc.returncode != 0:
            return False, {"error": (proc.stderr or proc.stdout or "VI execution failed").strip()}

        stdout = proc.stdout or ""
        for raw_line in reversed(stdout.splitlines()):
            line = raw_line.strip()
            if line.startswith(_SCRIPT_RESULT_MARKER):
                payload = line[len(_SCRIPT_RESULT_MARKER):].strip()
                try:
                    parsed = json.loads(payload)
                    if isinstance(parsed, dict):
                        err = str(parsed.get("error") or "")
                        if "VI fallback" in err:
                            return False, parsed
                    return True, parsed if isinstance(parsed, dict) else {"result": parsed}
                except Exception:
                    return False, {"error": f"Invalid JSON result payload from script: {payload}"}
        parser_hint = (proc.stderr or proc.stdout or "").strip()
        if parser_hint:
            return False, {
                "error": "Script executed but did not emit a result payload",
                "runtimeOutput": parser_hint[-2000:],
            }
        return False, {"error": "Script executed but did not emit a result payload"}
    except subprocess.TimeoutExpired:
        return False, {"error": "Script execution timed out"}
    except Exception as exc:
        return False, {"error": f"Script execution failed: {str(exc)}"}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _infer_scalar_type(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "string"


def _build_field_schema(field_def):
    schema = {
        "type": str(field_def.get("type", "string")).lower(),
        "required": bool(field_def.get("required", False)),
        "unique": bool(field_def.get("unique", False)),
    }

    if bool(field_def.get("default", False)):
        default_value = field_def.get("defaultValue")
        if default_value not in (None, ""):
            schema["default"] = default_value

    if schema["type"] == "object":
        nested_fields = field_def.get("embeddedFields") or []
        if nested_fields:
            schema["properties"] = {}
            for child in nested_fields:
                child_name = child.get("name")
                if not child_name:
                    continue
                schema["properties"][child_name] = _build_field_schema(child)
        else:
            template = field_def.get("objectTemplate")
            if isinstance(template, str) and template.strip():
                try:
                    obj = json.loads(template)
                    if isinstance(obj, dict):
                        schema["properties"] = {
                            k: {"type": _infer_scalar_type(v), "required": False}
                            for k, v in obj.items()
                        }
                except Exception:
                    pass

    return schema


def _build_collection_schema(model_def):
    fields = model_def.get("fields", {})
    schema = {}
    is_auth_model = bool((model_def or {}).get("__liwiroAuthModel", False))
    has_password_hash = False
    for field in fields.values():
        field_name = field.get("name")
        if not field_name:
            continue
        normalized = str(field_name).strip().lower()
        # Auth model exception: never persist plain passwords in collection schema.
        if is_auth_model and normalized == "password":
            continue
        if normalized == "passwordhash":
            has_password_hash = True
        schema[field_name] = _build_field_schema(field)
    if is_auth_model and not has_password_hash:
        schema["passwordHash"] = {"type": "string", "required": True, "unique": False}
    return schema


def _collect_unique_fields(model_def):
    unique_fields = []
    fields = (model_def or {}).get("fields") or {}
    for field in fields.values():
        field_name = str((field or {}).get("name") or "").strip()
        if field_name and bool((field or {}).get("unique", False)):
            unique_fields.append(field_name)
    return unique_fields


def _example_value_for_field(field_name, field_def):
    field = str(field_name or "").strip().lower()
    field_type = str((field_def or {}).get("type", "string")).strip().lower()
    if field in {"username", "user_name"}:
        return "kalumbi.banda"
    if field in {"id", "_id", "userid", "user_id"}:
        return "u_1001"
    if "email" in field:
        return "kalulu.kaumba@zmail.com"
    if "name" in field:
        return "Alex Rivera"
    if "phone" in field:
        return "+1-555-0107"
    if "date" in field or "at" in field:
        return datetime.now(timezone.utc).isoformat()
    if field_type == "number":
        return 42
    if field_type == "boolean":
        return True
    if field_type == "date":
        return datetime.now(timezone.utc).isoformat()
    if field_type == "object":
        nested = {}
        embedded = (field_def or {}).get("embeddedFields") or []
        for child in embedded:
            child_name = child.get("name")
            if child_name:
                nested[child_name] = _example_value_for_field(child_name, child)
        if nested:
            return nested
        return {"key": "value"}
    return "kalulu-demo-value"


def _model_example_payload(model_def):
    example = {}
    fields = (model_def or {}).get("fields") or {}
    for field in fields.values():
        field_name = field.get("name")
        if not field_name:
            continue
        example[field_name] = _example_value_for_field(field_name, field)
    return example


def _example_value_from_param_type(param_type):
    kind = str(param_type or "").strip().lower()
    if kind == "number":
        return 1
    if kind == "boolean":
        return True
    if kind == "array":
        return ["one", "two"]
    if kind == "object":
        return {"note": "Kalulu Kaumba confirms the payload for this flow."}
    return "kalulu.kaumba"


def _default_example_params(endpoint_cfg, lapis_config):
    supplied = endpoint_cfg.get("exampleParams")
    if isinstance(supplied, dict) and supplied:
        return supplied

    endpoint = endpoint_cfg or {}
    method = str(endpoint.get("method") or "GET").upper()
    op_type = normalize_lapis_operation_type(endpoint.get("operationType"))
    crud_op = normalize_lapis_crud_operation(endpoint.get("crudOperation"))
    linked_model = str(endpoint.get("linkedModel") or "")

    query = {}
    body = {}
    headers = {}
    if bool(endpoint.get("requiresAuth")):
        headers["Authorization"] = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.demo.signature"

    model_def = None
    if linked_model:
        for candidate in (lapis_config.get("models") or {}).values():
            if str(candidate.get("name") or "") == linked_model:
                model_def = candidate
                break
    model_payload = _model_example_payload(model_def) if model_def else {}

    if op_type == "crud":
        if crud_op in {"read", "delete"}:
            key_name = "_id"
            if model_payload:
                key_name = next(iter(model_payload.keys()))
            query[key_name] = model_payload.get(key_name, "u_1001")
        elif crud_op == "update":
            key_name = "_id"
            if model_payload:
                key_name = next(iter(model_payload.keys()))
            query[key_name] = model_payload.get(key_name, "u_1001")
            body = model_payload or {"status": "active"}
        else:
            body = model_payload or {"name": "Kalulu Kaumba", "email": "kalulu.kaumba@zmail.com"}
    elif method in {"POST", "PUT", "PATCH"}:
        body = {
            "story": "Kalulu Kaumba updates the service record after first login.",
            "active": True,
        }

    for param in endpoint.get("parameters") or []:
        if not isinstance(param, dict):
            continue
        name = str(param.get("name") or "").strip()
        if not name:
            continue
        value = _example_value_from_param_type(param.get("type"))
        where = str(param.get("in") or "").strip().lower()
        if where == "query":
            query[name] = value
        elif where == "body":
            body[name] = value
        elif where == "header":
            headers[name] = value

    example = {"query": query, "headers": headers}
    if method not in {"GET", "HEAD", "DELETE"}:
        example["body"] = body
    return example


def _doc_json_block(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    try:
        return json.dumps(value, indent=2, ensure_ascii=True)
    except Exception:
        return str(value)


def _doc_response_summary(endpoint_cfg: dict) -> str:
    op_type = normalize_lapis_operation_type((endpoint_cfg or {}).get("operationType"))
    crud_op = normalize_lapis_crud_operation((endpoint_cfg or {}).get("crudOperation"))
    method = str((endpoint_cfg or {}).get("method") or "GET").upper()

    if op_type == "crud":
        if crud_op == "create":
            return "Success returns `201 Created` with the insert result. Validation or persistence failures return `400` or `500`."
        if crud_op == "read":
            return "Success returns `200 OK` with every document that matches the supplied query. Empty queries read the full result set."
        if crud_op == "update":
            return "Success returns `200 OK` with update metadata. `404` is returned when no records match the supplied query."
        if crud_op == "delete":
            return "Success returns `200 OK` with delete metadata. `404` is returned when no records match the supplied query."
    if op_type == "custom":
        return "Success returns the JSON payload from the custom VQL query. Request query/body inputs can override the configured `query`, `args`, or `data` sections."
    if op_type == "script":
        return "Success returns a JSON response body from the Versa. Script-level `statusCode` values are propagated to HTTP."
    if method in {"POST", "PUT", "PATCH"}:
        return "Success returns a JSON response body from the Versa. Script-level `statusCode` values are propagated to HTTP."
    return "Success returns a JSON response body. Script-level `statusCode` values are propagated to HTTP."


def _default_endpoint_documentation(endpoint_cfg: dict, lapis_config: dict) -> dict:
    endpoint = endpoint_cfg or {}
    method = str(endpoint.get("method") or "GET").upper()
    path = str(endpoint.get("path") or "/").strip() or "/"
    op_type = normalize_lapis_operation_type(endpoint.get("operationType") or "unknown")
    crud_op = normalize_lapis_crud_operation(endpoint.get("crudOperation"))
    linked_model = str(endpoint.get("linkedModel") or "").strip()
    example = _default_example_params(endpoint, lapis_config)
    requires_auth = bool(endpoint.get("requiresAuth"))
    notes = str(endpoint.get("developerNotes") or "").strip()

    operation_summary = f"{method} {path} handles the {op_type} workflow"
    if crud_op:
        operation_summary += f" for the `{crud_op}` CRUD action"
    if linked_model:
        operation_summary += f" on `{linked_model}`"
    operation_summary += "."

    query_block = _doc_json_block(example.get("query") or {})
    body_block = _doc_json_block(example.get("body") or {})
    header_block = _doc_json_block(example.get("headers") or {})
    parameter_lines = []
    for param in endpoint.get("parameters") or []:
        if not isinstance(param, dict):
            continue
        name = str(param.get("name") or "").strip()
        where = str(param.get("in") or "").strip().lower()
        kind = str(param.get("type") or "").strip().lower()
        required = "required" if bool(param.get("required")) else "optional"
        description = str(param.get("description") or "").strip()
        if not name or not where:
            continue
        line = f"- `{name}` in `{where}` as `{kind or 'string'}` ({required})"
        if description:
            line += f": {description}"
        parameter_lines.append(line)

    sections = [
        {
            "title": "Authorization",
            "body": (
                "Bearer authentication is required before this route can run."
                if requires_auth
                else "This route is public and can be called without a bearer token."
            ),
        },
        {
            "title": "Request Contract",
            "body": "\n\n".join([
                "Empty query objects such as `{}` are forwarded as-is and therefore mean 'match all records' unless route-specific RBAC logic blocks the call.",
                f"Example query JSON:\n{query_block}" if query_block else "Example query JSON:\n{}",
                f"Example body JSON:\n{body_block}" if body_block else "Example body JSON:\n{}",
                f"Example headers:\n{header_block}" if header_block else "Example headers:\n{}",
            ]),
        },
        {
            "title": "Parameters",
            "body": "\n".join(parameter_lines) if parameter_lines else "No explicit parameter list was declared for this endpoint. Use the example request payloads and route notes as the operational contract.",
        },
        {
            "title": "Responses",
            "body": _doc_response_summary(endpoint),
        },
    ]
    if notes:
        sections.append({"title": "Operational Notes", "body": notes})

    return {
        "summary": operation_summary,
        "description": "Generated from the LAPIS endpoint definition. Override `endpoint.documentation` in the service configuration to provide service-specific wording.",
        "sections": sections,
    }


def _endpoint_documentation(endpoint_cfg: dict, lapis_config: dict) -> dict:
    supplied = endpoint_cfg.get("documentation")
    if isinstance(supplied, dict):
        summary = str(supplied.get("summary") or "").strip()
        description = str(supplied.get("description") or "").strip()
        raw_sections = supplied.get("sections")
        sections = []
        if isinstance(raw_sections, list):
            for section in raw_sections:
                if not isinstance(section, dict):
                    continue
                title = str(section.get("title") or "").strip()
                body = str(section.get("body") or "").strip()
                if title and body:
                    sections.append({"title": title, "body": body})
        if summary or description or sections:
            return {
                "summary": summary,
                "description": description,
                "sections": sections,
            }
    return _default_endpoint_documentation(endpoint_cfg, lapis_config)


def _parse_query_param_value(raw_value: Any) -> Any:
    if raw_value is None:
        return ""
    text = str(raw_value).strip()
    if text == "":
        return ""
    if text in {"true", "false", "null"}:
        try:
            return json.loads(text)
        except Exception:
            return text
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        try:
            return json.loads(text)
        except Exception:
            return text
    if text.startswith("{") or text.startswith("[") or (text.startswith('"') and text.endswith('"')):
        try:
            return json.loads(text)
        except Exception:
            return text
    return raw_value


_VQL_DIRECT_OVERRIDE_KEYS = {
    "action",
    "collection",
    "where",
    "document",
    "set",
    "inc",
    "unset",
    "resource",
    "operation",
    "model",
    "name",
    "topic",
    "value",
    "export",
}
_VQL_ARGS_HINT_KEYS = {"limit", "offset", "skip", "page", "sort", "order", "fields", "projection"}


def _deep_merge_dict(base: Any, updates: Any) -> dict:
    merged = json.loads(json.dumps(base if isinstance(base, dict) else {}))
    if not isinstance(updates, dict):
        return merged
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged.get(key), value)
        else:
            merged[key] = value
    return merged


def _extract_request_query_payload(raw_args: Any) -> tuple[dict, str | None]:
    query_params = raw_args.to_dict() if hasattr(raw_args, "to_dict") else dict(raw_args or {})
    if "__query" in query_params:
        raw_structured_query = query_params.pop("__query", None)
        try:
            parsed_structured_query = json.loads(str(raw_structured_query or ""))
        except Exception:
            return {}, "Invalid JSON supplied in __query"
        if not isinstance(parsed_structured_query, dict):
            return {}, "Structured __query payload must decode to an object"
        return parsed_structured_query, None
    return {
        key: _parse_query_param_value(value)
        for key, value in (query_params or {}).items()
    }, None


def _merge_custom_vql_request(base_query: Any, request_query: Any, request_body: Any) -> dict:
    merged = json.loads(json.dumps(base_query if isinstance(base_query, dict) else {}))
    flat_action = str(merged.get("action") or "").strip().lower()
    legacy_keys = {
        "tumi", "read", "create", "update", "delete", "list", "drop", "define", "use", "transaction", "script", "index",
        "find", "insert", "aggregate", "create_collection", "drop_collection", "drop_domain", "drop_db",
        "create_index", "drop_index", "list_indexes", "rebuild_indexes", "model_get", "model_delete",
        "script_create", "script_read", "script_execute", "script_delete", "script_list",
        "transaction_begin", "transaction_commit", "transaction_abort", "domain_status", "domain_suspend", "domain_resume",
        "help", "context", "whoami", "echo", "export",
    }
    if legacy_keys.intersection(merged):
        raise ValueError("Command data cannot override a VDB operation")
    for source in (request_query, request_body):
        if isinstance(source, dict) and legacy_keys.intersection(source):
            raise ValueError("Request data cannot override the configured VDB operation")
    if flat_action in {"find", "read", "aggregate"}:
        where_updates: dict[str, Any] = {}
        direct_updates: dict[str, Any] = {}
        for source in (request_query, request_body):
            if not isinstance(source, dict):
                continue
            if isinstance(source.get("where"), dict):
                where_updates = _deep_merge_dict(where_updates, source["where"])
            # Accept the established request wrapper while keeping the stored
            # command itself flat.
            if isinstance(source.get("query"), dict):
                where_updates = _deep_merge_dict(where_updates, source["query"])
            if isinstance(source.get("args"), dict):
                direct_updates = _deep_merge_dict(direct_updates, source["args"])
            for key, value in source.items():
                if key not in {"where", "query", "args", "data"}:
                    if key in _VQL_ARGS_HINT_KEYS:
                        direct_updates[key] = value
                    elif key not in {"action", "collection"}:
                        where_updates[key] = value
        if where_updates:
            merged["where"] = _deep_merge_dict(merged.get("where"), where_updates)
        merged.update(direct_updates)
        return merged
    # Custom VQL is canonicalized at configuration load time; all mutation
    # below operates on the flat action envelope only.
    operation_kind = flat_action

    query_updates = {}
    args_updates = {}
    data_updates = {}

    if isinstance(request_query, dict):
        if isinstance(request_query.get("query"), dict):
            query_updates = _deep_merge_dict(query_updates, request_query.get("query"))
        if isinstance(request_query.get("args"), dict):
            args_updates = _deep_merge_dict(args_updates, request_query.get("args"))
        if isinstance(request_query.get("data"), dict):
            data_updates = _deep_merge_dict(data_updates, request_query.get("data"))
        for key, value in request_query.items():
            if key in {"query", "args", "data"}:
                continue
            if key in _VQL_ARGS_HINT_KEYS:
                args_updates[key] = value
            else:
                query_updates[key] = value

    if isinstance(request_body, dict) and request_body:
        if any(key in request_body for key in _VQL_DIRECT_OVERRIDE_KEYS):
            merged = _deep_merge_dict(merged, request_body)
        else:
            if isinstance(request_body.get("query"), dict):
                query_updates = _deep_merge_dict(query_updates, request_body.get("query"))
            if isinstance(request_body.get("args"), dict):
                args_updates = _deep_merge_dict(args_updates, request_body.get("args"))
            if isinstance(request_body.get("data"), dict):
                data_updates = _deep_merge_dict(data_updates, request_body.get("data"))
            remainder = {
                key: value
                for key, value in request_body.items()
                if key not in {"query", "args", "data"}
            }
            if remainder:
                if operation_kind in {"create", "update"}:
                    data_updates = _deep_merge_dict(data_updates, remainder)
                elif operation_kind not in {"read", "delete"}:
                    data_updates = _deep_merge_dict(data_updates, remainder)

    if operation_kind in {"read", "find", "aggregate", "delete"}:
        if query_updates:
            merged["where"] = _deep_merge_dict(merged.get("where"), query_updates)
        if args_updates:
            merged.update(args_updates)
        return merged

    if operation_kind in {"create", "insert"}:
        if data_updates:
            merged["document"] = _deep_merge_dict(merged.get("document"), data_updates)
        if args_updates:
            merged.update(args_updates)
        return merged

    if operation_kind == "update":
        if query_updates:
            merged["where"] = _deep_merge_dict(merged.get("where"), query_updates)
        if data_updates:
            merged["set"] = _deep_merge_dict(merged.get("set"), data_updates)
        if args_updates:
            merged.update(args_updates)
        return merged

    if query_updates:
        merged["query"] = _deep_merge_dict(merged.get("query"), query_updates)
    if args_updates:
        merged["args"] = _deep_merge_dict(merged.get("args"), args_updates)
    if data_updates:
        merged["data"] = _deep_merge_dict(merged.get("data"), data_updates)
    return merged


def _normalize_service_env(raw_env):
    normalized = normalize_config_env(raw_env)
    for key in _RUNTIME_SERVICE_ENV_KEYS:
        runtime_val = os.getenv(key)
        if runtime_val is None or str(runtime_val).strip() == "":
            continue
        # Keep scalar-like runtime values as strings to mirror environment semantics.
        normalized[key] = str(runtime_val)
    return normalized


def _password_reset_submission_mode(reset_page_cfg: Any) -> str:
    cfg = reset_page_cfg if isinstance(reset_page_cfg, dict) else {}
    raw_mode = str(cfg.get("submissionMode") or "").strip().lower()
    if raw_mode in {"custom", "custom_page"}:
        return "custom_page"
    if raw_mode in {"auto", "auto_form"}:
        return "auto_form"
    return "custom_page" if cfg.get("enabled") is False else "auto_form"


def _password_reset_auto_form_enabled(reset_page_cfg: Any) -> bool:
    cfg = reset_page_cfg if isinstance(reset_page_cfg, dict) else {}
    if _password_reset_submission_mode(cfg) != "auto_form":
        return False
    return bool(cfg.get("enabled", True))


def _password_reset_route_path(base_path: Any, custom_cfg: Any) -> str:
    reset_cfg = custom_cfg if isinstance(custom_cfg, dict) else {}
    reset_path = str(reset_cfg.get("resetPassword") or "/reset-password").strip() or "/reset-password"
    if not reset_path.startswith("/"):
        reset_path = f"/{reset_path}"
    base_prefix = str(base_path or "").strip()
    if base_prefix and not base_prefix.startswith("/"):
        base_prefix = f"/{base_prefix}"
    if base_prefix and (
        reset_path == base_prefix
        or reset_path.startswith(f"{base_prefix.rstrip('/')}/")
    ):
        return reset_path
    route = f"{base_prefix.rstrip('/')}{reset_path}"
    return route or "/"


def _materialize_password_reset_link_base(raw_value: Any, runtime_port: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    if "{PORT}" in value:
        return value.replace("{PORT}", runtime_port)
    if "127.0.0.1:5001" in value:
        return value.replace("127.0.0.1:5001", f"127.0.0.1:{runtime_port}")
    if "://" in value or value.startswith("mailto:"):
        return value
    normalized_path = value if value.startswith("/") else f"/{value}"
    return f"http://127.0.0.1:{runtime_port}{normalized_path}"


def _resolved_password_reset_link_base(
    base_path: Any,
    custom_cfg: Any,
    reset_page_cfg: Any,
    runtime_port: str,
    current_value: Any = "",
) -> str:
    route = _password_reset_route_path(base_path, custom_cfg)
    default_reset = f"http://127.0.0.1:{runtime_port}{route or '/'}"
    cfg = reset_page_cfg if isinstance(reset_page_cfg, dict) else {}
    mode = _password_reset_submission_mode(cfg)
    if mode == "custom_page":
        custom_link = _materialize_password_reset_link_base(cfg.get("customPageBaseUrl"), runtime_port)
        if custom_link:
            return custom_link
    configured_reset = _materialize_password_reset_link_base(current_value, runtime_port)
    if configured_reset and "example.com/reset-password" not in configured_reset:
        return configured_reset
    return default_reset


def generate_api_service(lapis_config):
    lapis_config = normalize_lapis_config_contract(lapis_config)
    api_name = lapis_config["metadata"]["apiName"]
    base_path = lapis_config["metadata"]["basePath"]
    version = lapis_config["metadata"]["version"]
    service_db = lapis_config["metadata"].get("database", "main")
    metadata_cfg = lapis_config.get("metadata") or {}
    auth_cfg = lapis_config.get("auth") or {}
    service_modules = []
    for item in (lapis_config.get("modules") or []):
        if not isinstance(item, dict):
            continue
        module_name = str(item.get("name") or "").strip().lower()
        if not module_name:
            continue
        service_modules.append(
            {
                "name": module_name,
                "config": item.get("config") if isinstance(item.get("config"), dict) else {},
            }
        )
    service_env = _normalize_service_env(metadata_cfg.get("env"))
    runtime_port = str(os.getenv("PORT", "")).strip()
    if runtime_port:
        service_env["PORT"] = runtime_port
        service_env["PASSWORD_RESET_URL"] = _resolved_password_reset_link_base(
            base_path,
            (auth_cfg or {}).get("customEndpoints") or {},
            (auth_cfg or {}).get("passwordResetPage") or {},
            runtime_port,
            service_env.get("PASSWORD_RESET_URL") or "",
        )

    class _LiwiroJSONProvider(DefaultJSONProvider):
        """Make VDB binary values safe to return from generated endpoints.

        BSON/file-backed values can surface as ``bytes``. Flask's default JSON
        encoder rejects those values and turns an otherwise valid route into a
        500 response (``Object of type bytes is not JSON serializable``).
        Decode textual bytes losslessly where possible and use a stable base64
        representation for binary data.
        """

        @staticmethod
        def _normalize(value):
            import base64

            if isinstance(value, bytes):
                try:
                    return value.decode("utf-8")
                except UnicodeDecodeError:
                    return {"$binary": base64.b64encode(value).decode("ascii")}
            if isinstance(value, (bytearray, memoryview)):
                return _LiwiroJSONProvider._normalize(bytes(value))
            if isinstance(value, dict):
                return {str(key): _LiwiroJSONProvider._normalize(item) for key, item in value.items()}
            if isinstance(value, (list, tuple, set)):
                return [_LiwiroJSONProvider._normalize(item) for item in value]
            return value

        def dumps(self, obj, **kwargs):
            return super().dumps(self._normalize(obj), **kwargs)

    api_app = Flask(__name__)
    api_app.json_provider_class = _LiwiroJSONProvider
    api_app.json = _LiwiroJSONProvider(api_app)
    from app.verse.telemetry import install_telemetry
    install_telemetry(api_app, Config.VERSE_DATA_DIR, service=str((lapis_config.get("metadata") or {}).get("apiName") or "generated-service"))
    api_app.url_map.strict_slashes = False
    rate_limit_cfg = metadata_cfg.get("rateLimiting") if isinstance(metadata_cfg.get("rateLimiting"), dict) else {}
    rate_limit_enabled = bool(rate_limit_cfg.get("enabled", False))
    rate_limit_max = max(0, int(rate_limit_cfg.get("limit") or 0))
    rate_limit_window = {"second": 1.0, "minute": 60.0, "hour": 3600.0, "day": 86400.0}.get(
        str(rate_limit_cfg.get("timeframe") or "minute").strip().lower(), 60.0
    )
    rate_limit_lock = threading.Lock()
    rate_limit_events: dict[tuple[str, str], list[float]] = {}
    api_app.config.from_object(Config)
    # Child service processes receive runtime credentials via env injection.
    # Prefer those values so generated services stay aligned with active login/bootstrap context.
    api_app.config["VDB_TRANSPORT"] = os.getenv("VDB_TRANSPORT", api_app.config.get("VDB_TRANSPORT"))
    api_app.config["VDB_SERVER_URL"] = os.getenv("VDB_SERVER_URL", api_app.config.get("VDB_SERVER_URL"))
    api_app.config["VDB_UNIX_SOCKET_PATH"] = os.getenv(
        "VDB_UNIX_SOCKET_PATH",
        api_app.config.get("VDB_UNIX_SOCKET_PATH"),
    )
    api_app.config["VDB_NAMED_PIPE_PATH"] = os.getenv(
        "VDB_NAMED_PIPE_PATH",
        api_app.config.get("VDB_NAMED_PIPE_PATH"),
    )
    api_app.config["VDB_USERNAME"] = os.getenv("VDB_USERNAME", api_app.config.get("VDB_USERNAME"))
    api_app.config["VDB_PASSWORD"] = os.getenv("VDB_PASSWORD", api_app.config.get("VDB_PASSWORD"))
    api_app.config["LIWIRO_DOMAIN"] = os.getenv("LIWIRO_DOMAIN", api_app.config.get("LIWIRO_DOMAIN"))
    api_app.config["LIWIRO_DB"] = os.getenv("LIWIRO_DB", api_app.config.get("LIWIRO_DB"))
    api_app.config["LIWIRO_DOCS_PASSWORD_HASH"] = os.getenv(
        "LIWIRO_DOCS_PASSWORD_HASH",
        api_app.config.get("LIWIRO_DOCS_PASSWORD_HASH", ""),
    )
    api_app.config["apiName"] = api_name

    @api_app.route('/liwiro')
    def liwiro_info():
        if _production_mode_enabled():
            return jsonify({"error": "Not found"}), 404
        return jsonify({":>": f"{api_name} was built with Liwiro"})

    from models.domain import DomainManager

    domain_manager = DomainManager(api_app)

    def _workspace_failure_message(domain_name: str, database_name: str) -> str:
        """Return an actionable workspace error for setup and auth routes."""
        detail = str(getattr(domain_manager.vdb_client, "workspace_error", "") or "").strip()
        base = f"Failed to prepare VDB workspace {domain_name}/{database_name}"
        return f"{base}: {detail}" if detail else base

    with api_app.app_context():
        if not domain_manager.ensure_workspace(api_name, service_db):
            failure = _workspace_failure_message(api_name, service_db)
            api_app.logger.error(f"Failed to prepare service workspace: {failure}")
            raise RuntimeError(failure)

        auth_model_name = str((auth_cfg or {}).get("authModel") or "").strip()
        for _, model_def in lapis_config["models"].items():
            model_name = str((model_def or {}).get("name") or "").strip()
            model_def = dict(model_def or {})
            model_def["__liwiroAuthModel"] = bool(
                auth_model_name
                and bool((auth_cfg or {}).get("isAuthService", False))
                and model_name == auth_model_name
            )
            collection_name = model_def.get("collection", model_def["name"])
            fields_schema = _build_collection_schema(model_def)
            success, result = domain_manager.create_collection(collection_name, fields_schema)
            if not success:
                error_text = (result or {}).get("error", "unknown collection creation error")
                api_app.logger.error(f"Failed to create collection {collection_name}: {error_text}")
                raise RuntimeError(f"Failed to create collection {collection_name}: {error_text}")
            else:
                api_app.logger.info(f"Created/Verified collection: {collection_name}")
            for unique_field in _collect_unique_fields(model_def):
                idx_ok, idx_result = domain_manager.vdb_client.create_index(
                    collection_name,
                    unique_field,
                    unique=True,
                    sparse=False,
                )
                if not idx_ok:
                    api_app.logger.warning(
                        f"Failed to create unique index on {collection_name}.{unique_field}: "
                        f"{(idx_result or {}).get('error', idx_result)}"
                    )
                else:
                    api_app.logger.info(f"Created/Verified unique index: {collection_name}.{unique_field}")
        if bool((auth_cfg or {}).get("isAuthService", False)):
            session_controls_schema = {
                "schema": {
                    "username": {"type": "string", "required": True},
                    "sessionVersion": {"type": "number"},
                    "revokeAll": {"type": "boolean"},
                    "revokedAt": {"type": "string"},
                    "excludeCurrentSession": {"type": "boolean"},
                    "excludedTokenHash": {"type": "string"},
                    "updatedAt": {"type": "string"},
                    "updatedBy": {"type": "string"},
                    "reason": {"type": "string"},
                }
            }
            session_ok, session_result = domain_manager.create_collection(
                "auth_session_controls", session_controls_schema["schema"]
            )
            if not session_ok:
                error_text = (session_result or {}).get("error", session_result)
                api_app.logger.error(f"Failed to create auth_session_controls collection: {error_text}")
                raise RuntimeError(f"Failed to create auth_session_controls collection: {error_text}")
            else:
                idx_ok, idx_result = domain_manager.vdb_client.create_index(
                    "auth_session_controls",
                    "username",
                    unique=True,
                    sparse=False,
                )
                if not idx_ok:
                    api_app.logger.warning(
                        "Failed to create unique index on auth_session_controls.username: "
                        f"{(idx_result or {}).get('error', idx_result)}"
                    )
            reset_tokens_schema = {
                "schema": {
                    "jti": {"type": "string", "required": True},
                    "username": {"type": "string", "required": True},
                    "tokenHash": {"type": "string", "required": True},
                    "status": {"type": "string", "required": True},
                    "expiresAt": {"type": "number"},
                    "createdAt": {"type": "string"},
                    "usedAt": {"type": "string"},
                    "recipient": {"type": "string"},
                }
            }
            token_ok, token_result = domain_manager.create_collection(
                "auth_password_reset_tokens", reset_tokens_schema["schema"]
            )
            if not token_ok:
                error_text = (token_result or {}).get("error", token_result)
                api_app.logger.error(f"Failed to create auth_password_reset_tokens collection: {error_text}")
                raise RuntimeError(f"Failed to create auth_password_reset_tokens collection: {error_text}")
            else:
                idx_ok, idx_result = domain_manager.vdb_client.create_index(
                    "auth_password_reset_tokens",
                    "jti",
                    unique=True,
                    sparse=False,
                )
                if not idx_ok:
                    api_app.logger.warning(
                        "Failed to create unique index on auth_password_reset_tokens.jti: "
                        f"{(idx_result or {}).get('error', idx_result)}"
                    )

    def _resolve_model_collection(model_name):
        if not model_name:
            return None
        for _, model_def in lapis_config.get("models", {}).items():
            if model_def.get("name") == model_name:
                return model_def.get("collection", model_name)
        return None

    def _normalize_segment(path_part):
        value = str(path_part or "").strip()
        if not value:
            return ""
        return value if value.startswith("/") else f"/{value}"

    def _join_route(base, sub):
        base_norm = _normalize_segment(base)
        sub_norm = _normalize_segment(sub)
        if base_norm and sub_norm and (
            sub_norm == base_norm
            or sub_norm.startswith(f"{base_norm.rstrip('/')}/")
        ):
            route = sub_norm
        else:
            route = f"{base_norm.rstrip('/')}{sub_norm}"
        if route in {"", "/"}:
            return "/"
        return route

    def _auth_password_reset_page_config() -> dict:
        cfg = (auth_cfg or {}).get("passwordResetPage") or {}
        return cfg if isinstance(cfg, dict) else {}

    def _auth_password_reset_page_mode() -> str:
        return _password_reset_submission_mode(_auth_password_reset_page_config())

    def _auth_password_reset_page_enabled() -> bool:
        return _password_reset_auto_form_enabled(_auth_password_reset_page_config())

    def _auth_password_reset_page_copy(reset_route: str, token_present: bool) -> dict:
        cfg = _auth_password_reset_page_config()
        default_status = (
            "Reset token loaded from the email link."
            if token_present
            else "Paste the reset token from the email to continue."
        )
        return {
            "title": str(cfg.get("title") or f"{api_name} Password Reset"),
            "description": str(
                cfg.get("description")
                or "Use the token from the email link to submit a new password for the account."
            ),
            "submitLabel": str(cfg.get("submitLabel") or "Reset Password"),
            "loadingMessage": str(cfg.get("loadingMessage") or "Submitting password reset request..."),
            "successMessage": str(cfg.get("successMessage") or "Password reset completed."),
            "failureMessage": str(cfg.get("failureMessage") or "Password reset failed."),
            "statusText": default_status,
            "routeNote": f"This page submits a `POST` request to {reset_route} after the new password is entered.",
        }

    def _docs_enabled():
        docs_cfg = metadata_cfg.get("documentation") or {}
        return bool(docs_cfg.get("enabled", True))

    def _production_mode_enabled():
        try:
            auth_data = load_normalized_auth_data()
            settings = auth_data.get("settings") or {}
            return bool(settings.get("productionMode", False))
        except Exception:
            return False

    def _management_route_json_unavailable():
        return jsonify({"error": "Not found"}), 404

    def _management_route_html_unavailable():
        return Response(
            "<html><body><h2>Not found.</h2></body></html>",
            status=404,
            mimetype="text/html",
        )

    def _setup_api_key():
        return str(metadata_cfg.get("setupApiKey") or "").strip()

    def _extract_docs_key():
        return (
            request.headers.get("X-Documentation-Key")
            or request.headers.get("X-Docs-Key")
            or request.args.get("key")
            or request.args.get("docKey")
            or ""
        )

    def _docs_authorized():
        docs_key = str(_extract_docs_key() or "")
        docs_cfg = metadata_cfg.get("documentation") or {}
        docs_hash = str(docs_cfg.get("keyHash") or "")
        docs_plain = str(docs_cfg.get("key") or "")
        fallback_hash = str(api_app.config.get("LIWIRO_DOCS_PASSWORD_HASH") or "")

        if not docs_key:
            return False
        if docs_hash:
            try:
                return check_password_hash(docs_hash, docs_key)
            except Exception:
                return False
        if docs_plain:
            return docs_key == docs_plain
        if fallback_hash:
            try:
                return check_password_hash(fallback_hash, docs_key)
            except Exception:
                return False
        return False

    def _setup_authorized():
        configured_key = _setup_api_key()
        if not configured_key:
            return False, "Setup API key is not configured in LAPIS metadata.setupApiKey"
        provided_key = (
            request.headers.get("X-Liwiro-Setup-Key")
            or request.headers.get("X-Setup-Key")
            or request.args.get("setupKey")
            or ""
        )
        if str(provided_key).strip() != configured_key:
            return False, "Invalid setup API key"
        return True, ""

    def _jwt_verification_material():
        auth_settings = auth_cfg or {}
        key_management = str(auth_settings.get("keyManagement") or "auto").strip().lower()
        public_key = str(auth_settings.get("authServicePublicKey") or auth_settings.get("publicKey") or "").strip()
        private_key = str(auth_settings.get("privateKey") or "").strip()
        auth_service_name = str(auth_settings.get("authServiceName") or "").strip()
        configured_secret = str(os.getenv("LIWIRO_JWT_SECRET") or metadata_cfg.get("jwtSecret") or "").strip()
        # Deterministic names are useful for local demos only. Production
        # services must have an operator-provided secret or asymmetric key.
        fallback_secret = configured_secret or ("" if _production_mode_enabled() else str(metadata_cfg.get("setupApiKey") or api_name or "liwiro").strip())
        auth_service_hs256_default = f"{auth_service_name}::liwiro" if auth_service_name else ""
        local_service_hs256_default = f"{api_name}::liwiro" if api_name else ""

        if key_management == "manual":
            verify_key = public_key or private_key
        else:
            verify_key = public_key or fallback_secret
        return verify_key, fallback_secret, auth_service_hs256_default, local_service_hs256_default

    revoked_token_hashes = set()

    def _token_digest(token: str) -> str:
        try:
            return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
        except Exception:
            return ""

    def _auth_bootstrap_password_hash_mode() -> str:
        if not bool(auth_cfg.get("isAuthService", False)):
            return "werkzeug"

        custom_cfg = (auth_cfg or {}).get("customEndpoints") or {}
        if not bool(custom_cfg.get("enabled", False)):
            return "werkzeug"

        sign_in_route = _join_route(base_path, str(custom_cfg.get("signIn") or "/auth/signin"))
        for endpoint_cfg in (lapis_config.get("endpoints") or {}).values():
            if str(endpoint_cfg.get("method") or "GET").upper() != "POST":
                continue
            endpoint_route = _join_route(base_path, endpoint_cfg.get("path", ""))
            if endpoint_route != sign_in_route:
                continue
            if str(endpoint_cfg.get("operationType") or "").strip().lower() != "script":
                continue
            script_src = str(endpoint_cfg.get("versaScript") or "")
            if "crypto.sha256(" in script_src and "passwordHash" in script_src:
                return "sha256"
        return "werkzeug"

    def _hash_auth_bootstrap_password(password: Any) -> str:
        raw = str(password or "")
        if _auth_bootstrap_password_hash_mode() == "sha256":
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return generate_password_hash(raw)

    def _normalize_seed_document(document: dict[str, Any], *, is_auth_collection: bool) -> dict[str, Any]:
        """Prepare a LAPIS seed document without persisting generation-only credentials."""
        payload = dict(document)
        if not is_auth_collection:
            return payload

        # ``seedPassword`` is intentionally transient: LAPIS examples can declare
        # demo credentials without committing a password hash to source control.
        seed_password = str(payload.pop("seedPassword", "") or "").strip()
        # Accept the legacy spelling while ensuring plaintext is never persisted.
        if not seed_password:
            seed_password = str(payload.pop("password", "") or "").strip()
        else:
            payload.pop("password", None)
        if seed_password:
            payload["passwordHash"] = _hash_auth_bootstrap_password(seed_password)
        return payload

    def _epoch_seconds(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            pass
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return None

    def _auth_control_workspace():
        if bool((auth_cfg or {}).get("isAuthService", False)):
            return api_name, service_db
        dependency_name = str((auth_cfg or {}).get("authServiceName") or "").strip()
        if not dependency_name:
            return "", ""
        service_doc = _service_registry_lookup_by_name(dependency_name)
        if not isinstance(service_doc, dict):
            return "", ""
        target_lapis = service_doc.get("lapis_config") or {}
        target_domain = str(service_doc.get("vdb_domain") or service_doc.get("apiName") or "").strip()
        target_db = str((target_lapis.get("metadata") or {}).get("database") or "main").strip() or "main"
        return target_domain, target_db

    def _load_auth_session_control(username: str):
        subject = str(username or "").strip()
        if not subject:
            return None
        target_domain, target_db = _auth_control_workspace()
        if not target_domain:
            return None
        client = domain_manager.vdb_client
        should_restore = target_domain != api_name or target_db != service_db
        try:
            if not client.ensure_workspace(target_domain, target_db):
                return None
            ok, rows = client.read_documents("auth_session_controls", {"username": {"$eq": subject}})
            if ok and isinstance(rows, list) and rows and isinstance(rows[0], dict):
                return rows[0]
            return None
        finally:
            if should_restore:
                client.ensure_workspace(api_name, service_db)

    def _current_auth_session_version(username: str) -> int:
        control = _load_auth_session_control(username)
        version = _coerce_int((control or {}).get("sessionVersion"))
        return version if version and version > 0 else 1

    def _is_token_revoked_by_session_control(token: str, claims: dict | None) -> bool:
        if not isinstance(claims, dict):
            return False
        username = str(claims.get("username") or claims.get("sub") or "").strip()
        if not username:
            return False
        control = _load_auth_session_control(username)
        if not isinstance(control, dict) or not control:
            return False

        token_hash = _token_digest(token)
        excluded_hash = str(control.get("excludedTokenHash") or "").strip()
        if bool(control.get("excludeCurrentSession")) and token_hash and token_hash == excluded_hash:
            return False

        control_version = _coerce_int(control.get("sessionVersion")) or 1
        token_version_raw = claims.get("sessionVersion") if "sessionVersion" in claims else claims.get("session_version")
        token_version = _coerce_int(token_version_raw) or 1
        if token_version < control_version:
            return True

        if bool(control.get("revokeAll")) and token_version_raw is None:
            revoked_at = _epoch_seconds(control.get("revokedAt"))
            token_iat = _epoch_seconds(claims.get("iat"))
            if revoked_at is None or token_iat is None:
                return True
            if token_iat <= revoked_at:
                return True
        return False

    def _revoke_token(token: str) -> None:
        digest = _token_digest(token)
        if digest:
            revoked_token_hashes.add(digest)

    def _is_token_revoked(token: str) -> bool:
        digest = _token_digest(token)
        return bool(digest and digest in revoked_token_hashes)

    def _verify_bearer_token(token: str):
        verify_key, fallback_secret, auth_service_hs256_default, local_service_hs256_default = _jwt_verification_material()
        if not token:
            return False, "Missing bearer token", None
        if _is_token_revoked(token):
            return False, "Token revoked", None
        if jwt is None:
            return False, "PyJWT not installed on service runtime", None

        algorithms = ["RS256", "HS256"]
        if _production_mode_enabled() and not str((auth_cfg or {}).get("privateKey") or "").strip() and not fallback_secret:
            return False, "JWT verification key is not configured", None
        candidates = [verify_key]
        if not _production_mode_enabled() and auth_service_hs256_default and auth_service_hs256_default not in candidates:
            candidates.append(auth_service_hs256_default)
        if not _production_mode_enabled() and local_service_hs256_default and local_service_hs256_default not in candidates:
            candidates.append(local_service_hs256_default)
        if fallback_secret and fallback_secret not in candidates:
            candidates.append(fallback_secret)

        for key in candidates:
            if not key:
                continue
            try:
                payload = jwt.decode(token, key, algorithms=algorithms, options={"verify_aud": False})
                if not isinstance(payload, dict):
                    continue
                purpose = str(payload.get("purpose") or payload.get("token_use") or "").strip().lower()
                audience = payload.get("aud")
                audience_tokens = set()
                if isinstance(audience, str):
                    audience_tokens = {audience.strip().lower()}
                elif isinstance(audience, list):
                    audience_tokens = {
                        str(item).strip().lower()
                        for item in audience
                        if str(item).strip()
                    }
                if purpose in {"password_reset", "reset", "password-reset"} or "password-reset" in audience_tokens:
                    return False, "Invalid bearer token purpose", None
                if _is_token_revoked_by_session_control(token, payload):
                    return False, "Token revoked", None
                return True, "", payload
            except Exception:
                continue
        return False, "Token verification failed", None

    def _auth_required(endpoint_cfg):
        return bool((endpoint_cfg or {}).get("requiresAuth", False))

    def _endpoint_enabled(endpoint_cfg):
        return bool((endpoint_cfg or {}).get("enabled", True))

    def _protect_handler(handler, endpoint_cfg):
        @wraps(handler)
        def _wrapped(*args, **kwargs):
            if not _endpoint_enabled(endpoint_cfg):
                return jsonify({"error": "Endpoint is disabled in LAPIS configuration"}), 403
            if rate_limit_enabled and rate_limit_max > 0:
                key = (request.remote_addr or "unknown", str(endpoint_cfg.get("path") or ""))
                now = time.monotonic()
                with rate_limit_lock:
                    events = [stamp for stamp in rate_limit_events.get(key, []) if now - stamp < rate_limit_window]
                    if len(events) >= rate_limit_max:
                        retry_after = max(1, int(rate_limit_window - (now - events[0])) + 1)
                        response = jsonify({"error": "Rate limit exceeded", "retryAfterSeconds": retry_after})
                        response.status_code = 429
                        response.headers["Retry-After"] = str(retry_after)
                        return response
                    events.append(now)
                    rate_limit_events[key] = events
            if _auth_required(endpoint_cfg):
                auth_header = str(request.headers.get("Authorization") or "")
                if not auth_header.startswith("Bearer "):
                    return jsonify({"error": "Bearer token required"}), 401
                token = auth_header.split(" ", 1)[1].strip()
                ok, message, payload = _verify_bearer_token(token)
                if not ok:
                    return jsonify({"error": message}), 401
                request.liwiro_auth = payload or {}
                request.liwiro_bearer_token = token
                endpoint_path = str((endpoint_cfg or {}).get("path") or "").strip().lower()
                endpoint_method = str((endpoint_cfg or {}).get("method") or "").strip().upper()
                if bool((auth_cfg or {}).get("isAuthService", False)) and endpoint_method == "POST" and endpoint_path.endswith("/signout"):
                    _revoke_token(token)
            return handler(*args, **kwargs)
        return _wrapped

    def _build_endpoint_docs():
        endpoint_docs = []
        for endpoint_id, endpoint_cfg in lapis_config.get("endpoints", {}).items():
            endpoint_docs.append({
                "id": endpoint_id,
                "enabled": bool(endpoint_cfg.get("enabled", True)),
                "toggleable": True,
                "method": endpoint_cfg.get("method"),
                "path": _join_route(base_path, endpoint_cfg.get("path", "")),
                "operationType": endpoint_cfg.get("operationType"),
                "crudOperation": endpoint_cfg.get("crudOperation"),
                "linkedModel": endpoint_cfg.get("linkedModel"),
                "requiresAuth": bool(endpoint_cfg.get("requiresAuth", False)),
                "parameters": endpoint_cfg.get("parameters", []),
                "developerNotes": endpoint_cfg.get("developerNotes", ""),
                "documentation": _endpoint_documentation(endpoint_cfg, lapis_config),
                "exampleParams": _default_example_params(endpoint_cfg, lapis_config),
            })
        # Surface auto-generated auth routes in the main routes list so they use
        # the same default-input testing workflow as other routes.
        custom_cfg = (auth_cfg or {}).get("customEndpoints") or {}
        if bool((auth_cfg or {}).get("enabled", False)):
            signout_route = _join_route(base_path, str(custom_cfg.get("signOut") or "/auth/signout"))
            signout_key = ("POST", signout_route)
            if signout_key not in configured_route_keys:
                endpoint_docs.append({
                    "id": "ep_auth_signout_auto",
                    "enabled": True,
                    "toggleable": False,
                    "method": "POST",
                    "path": signout_route,
                    "operationType": "script",
                    "crudOperation": None,
                    "linkedModel": str((auth_cfg or {}).get("authModel") or ""),
                    "requiresAuth": True,
                    "parameters": [],
                    "developerNotes": "Signout route (bearer token required; revokes the presented bearer token on this service and expects the client to clear it).",
                    "documentation": _default_endpoint_documentation({
                        "method": "POST",
                        "path": signout_route,
                        "operationType": "script",
                        "requiresAuth": True,
                        "developerNotes": "Signout route (bearer token required; revokes the presented bearer token on this service and expects the client to clear it).",
                    }, lapis_config),
                    "exampleParams": {
                        "query": {},
                        "headers": {
                            "Authorization": "Bearer <captured-token>",
                        },
                    },
                })

        if bool((auth_cfg or {}).get("isAuthService", False)) and bool(custom_cfg.get("enabled", False)):
            register_route = _join_route(base_path, str(custom_cfg.get("register") or "/auth/register"))
            register_key = ("POST", register_route)
            if register_key not in configured_route_keys:
                endpoint_docs.append({
                    "id": "ep_auth_register_auto",
                    "enabled": True,
                    "toggleable": False,
                    "method": "POST",
                    "path": register_route,
                    "operationType": "script",
                    "crudOperation": None,
                    "linkedModel": str((auth_cfg or {}).get("authModel") or ""),
                    "requiresAuth": True,
                    "parameters": [],
                    "developerNotes": "Register route (super-admin bearer token required).",
                    "documentation": _default_endpoint_documentation({
                        "method": "POST",
                        "path": register_route,
                        "operationType": "script",
                        "requiresAuth": True,
                        "developerNotes": "Register route (super-admin bearer token required).",
                    }, lapis_config),
                    "exampleParams": {
                        "query": {},
                        "body": {
                            "username": "kalumbi.banda",
                            "email": "kalumbi.banda@zmail.com",
                            "password": "AfricaPatriotic#2026",
                            "role": "ADMIN",
                            "rbac": {"scopes": ["ADMIN", "USER_MANAGE", "USER_READ", "USER_WRITE"]},
                        },
                        "headers": {
                            "Authorization": "Bearer <captured-token>",
                        },
                    },
                })
        return endpoint_docs

    configured_route_keys = set()
    for endpoint_cfg in (lapis_config.get("endpoints") or {}).values():
        route_method = str(endpoint_cfg.get("method") or "GET").upper()
        route_path = _join_route(base_path, endpoint_cfg.get("path", ""))
        configured_route_keys.add((route_method, route_path))

    def _auth_user_summary(doc):
        if not isinstance(doc, dict):
            return None
        username = str(doc.get("username") or "").strip()
        if not username:
            return None
        rbac = doc.get("rbac") if isinstance(doc.get("rbac"), dict) else {}
        return {
            "username": username,
            "email": str(doc.get("email") or "").strip(),
            "role": str(doc.get("role") or "USER"),
            "rbac": {
                "scopes": rbac.get("scopes", []),
                "abilities": rbac.get("abilities", []),
                "tenant": rbac.get("tenant"),
            },
        }

    def _build_docs_payload():
        setup_routes = []
        media_capabilities = summarize_media_capabilities(lapis_config)
        auth_context = {
            "isAuthService": bool(auth_cfg.get("isAuthService", False)),
            "authServiceName": str((auth_cfg or {}).get("authServiceName") or "").strip(),
            "authSignInRoute": "",
            "authSignOutRoute": "",
            "authUsers": [],
        }
        has_auth_required_endpoint = any(bool((ep or {}).get("requiresAuth", False)) for ep in (lapis_config.get("endpoints") or {}).values())
        if bool(auth_cfg.get("isAuthService", False)):
            default_super = auth_cfg.get("defaultSuperAdmin") or {}
            auth_context["authServiceName"] = api_name
            setup_routes.append({
                "method": "POST",
                "path": "/liwiro/setup/reset-super-admin",
                "description": "Idempotently reset or create the auth service super admin from LAPIS defaults",
                "enabled": bool(default_super.get("enabled", False)),
                "payloadTemplate": {
                    "username": default_super.get("username", ""),
                    "email": default_super.get("email", ""),
                    "password": default_super.get("password", ""),
                    "role": default_super.get("role", "SUPER_ADMIN"),
                },
            })
            if has_auth_required_endpoint:
                custom_cfg = (auth_cfg or {}).get("customEndpoints") or {}
                sign_in_path = _join_route(base_path, str(custom_cfg.get("signIn") or "/auth/signin"))
                sign_out_path = _join_route(base_path, str(custom_cfg.get("signOut") or "/auth/signout"))
                register_path = _join_route(base_path, str(custom_cfg.get("register") or "/auth/register"))
                auth_context["authSignInRoute"] = sign_in_path
                auth_context["authSignOutRoute"] = sign_out_path
                setup_routes.append({
                    "method": "POST",
                    "path": sign_in_path,
                    "description": "Authenticate using super admin or created credentials to obtain bearer token for protected routes.",
                    "enabled": True,
                    "kind": "authenticate",
                    "payloadTemplate": {
                        "username": (default_super.get("username") or ""),
                        "password": (default_super.get("password") or ""),
                    },
                })
                setup_routes.append({
                    "method": "POST",
                    "path": sign_out_path,
                    "description": "Sign out current authenticated user context and clear client bearer token.",
                    "enabled": True,
                    "kind": "signout",
                    "payloadTemplate": {},
                })
                setup_routes.append({
                    "method": "POST",
                    "path": register_path,
                    "description": "Register new users (super-admin token required).",
                    "enabled": True,
                    "kind": "register",
                    "payloadTemplate": {
                        "username": "kalumbi.banda",
                        "email": "kalumbi.banda@zmail.com",
                        "password": "AfricaPatriotic#2026",
                        "role": "ADMIN",
                        "rbac": {"scopes": ["ADMIN", "USER_MANAGE", "USER_READ", "USER_WRITE"]},
                    },
                })
        elif has_auth_required_endpoint:
            dependency_name = str((auth_cfg or {}).get("authServiceName") or "").strip()
            auth_context["authServiceName"] = dependency_name
            setup_routes.append({
                "method": "POST",
                "path": "/liwiro/setup/authenticate",
                "description": f"Authenticate against auth service '{dependency_name or 'configured auth service'}' and use returned bearer token for protected routes.",
                "enabled": bool(dependency_name),
                "kind": "authenticate",
                "payloadTemplate": {
                    "username": "",
                    "password": "",
                },
            })
            setup_routes.append({
                "method": "POST",
                "path": "/liwiro/setup/signout",
                "description": f"Sign out against auth service '{dependency_name or 'configured auth service'}' and clear local bearer token state.",
                "enabled": bool(dependency_name),
                "kind": "signout",
                "payloadTemplate": {},
            })
        seed_cfg = metadata_cfg.get("seedData") or {}
        setup_routes.append({
            "method": "POST",
            "path": "/liwiro/setup/seed-db",
            "description": "Seed service collections using LAPIS metadata.seedData.collections",
            "enabled": bool(seed_cfg.get("enabled", False)),
            "payloadTemplate": {
                "collections": seed_cfg.get("collections", {}),
            },
        })
        return {
            "title": api_name,
            "version": version,
            "basePath": base_path,
            "database": service_db,
            "developerNotes": metadata_cfg.get("developerNotes", ""),
            "setupApiKeyConfigured": bool(_setup_api_key()),
            "authContext": auth_context,
            "mediaCapabilities": media_capabilities,
            "setupRoutes": setup_routes,
            "endpoints": _build_endpoint_docs(),
        }

    def _service_registry_lookup_by_name(service_name: str):
        target = str(service_name or "").strip()
        if not target:
            return None
        registry_domain = str(api_app.config.get("LIWIRO_DOMAIN") or Config.LIWIRO_DOMAIN or "").strip()
        registry_db = str(api_app.config.get("LIWIRO_DB") or Config.LIWIRO_DB or "").strip()
        if not registry_domain or not registry_db:
            return None

        client = domain_manager.vdb_client
        try:
            if not client.ensure_workspace(registry_domain, registry_db):
                return None
            ok, rows = client.read_documents("services", {})
            if ok and isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    row_lapis = row.get("lapis_config") or {}
                    row_metadata = row_lapis.get("metadata") or {} if isinstance(row_lapis, dict) else {}
                    aliases = (
                        row.get("apiName"),
                        row.get("name"),
                        row.get("vdb_domain"),
                        row_metadata.get("apiName") if isinstance(row_metadata, dict) else "",
                    )
                    if any(str(alias or "").strip().lower() == target.lower() for alias in aliases):
                        return row
            return None
        finally:
            client.ensure_workspace(api_name, service_db)

    def _persist_service_lapis_config(next_lapis_config: dict) -> bool:
        registry_domain = str(api_app.config.get("LIWIRO_DOMAIN") or Config.LIWIRO_DOMAIN or "").strip()
        registry_db = str(api_app.config.get("LIWIRO_DB") or Config.LIWIRO_DB or "").strip()
        if not registry_domain or not registry_db:
            return False

        client = domain_manager.vdb_client
        payload = {
            "apiName": api_name,
            "lapis_config": next_lapis_config,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        try:
            if not client.ensure_workspace(registry_domain, registry_db):
                return False
            updated, result = client.update_document("services", {"apiName": {"$eq": api_name}}, payload)
            updated_count = _extract_result_count(result, "updated", "affected_count", "count")
            if updated and updated_count and updated_count > 0:
                return True
            created, _ = client.create_document("services", payload)
            return bool(created)
        except Exception:
            return False
        finally:
            client.ensure_workspace(api_name, service_db)

    def _load_auth_service_users(service_doc):
        if not isinstance(service_doc, dict):
            return []
        lapis = service_doc.get("lapis_config") or {}
        auth_settings = lapis.get("auth") or {}
        model_name = str(auth_settings.get("authModel") or "").strip()
        if not model_name:
            return []
        collection_name = None
        for model_def in (lapis.get("models") or {}).values():
            if str((model_def or {}).get("name") or "").strip() == model_name:
                collection_name = str((model_def or {}).get("collection") or model_name).strip()
                break
        if not collection_name:
            return []

        service_domain = str(service_doc.get("apiName") or "").strip()
        service_db_name = str((lapis.get("metadata") or {}).get("database") or "main").strip() or "main"
        if not service_domain:
            return []

        client = domain_manager.vdb_client
        try:
            if not client.ensure_workspace(service_domain, service_db_name):
                return []
            ok, rows = client.read_documents(collection_name, {})
            if not ok or not isinstance(rows, list):
                return []
            users = []
            for row in rows:
                summary = _auth_user_summary(row)
                if summary:
                    users.append(summary)
            return users
        finally:
            client.ensure_workspace(api_name, service_db)

    @api_app.route("/liwiro/setup/reset-super-admin", methods=["POST"])
    @api_app.route("/liwiro/setup/default-super-admin", methods=["POST"])
    def setup_reset_super_admin():
        if _production_mode_enabled():
            return _management_route_json_unavailable()
        if not bool(auth_cfg.get("isAuthService", False)):
            return jsonify({"error": "Super admin reset is available only for auth services"}), 404

        setup_cfg = auth_cfg.get("defaultSuperAdmin") or {}
        if not bool(setup_cfg.get("enabled", False)):
            return jsonify({"error": "Super admin reset is disabled in LAPIS"}), 403
        ok, message = _setup_authorized()
        if not ok:
            return jsonify({"error": message}), 401

        auth_model_name = auth_cfg.get("authModel")
        collection_name = _resolve_model_collection(auth_model_name)
        if not collection_name:
            return jsonify({"error": "auth.authModel is not mapped to a collection"}), 400
        if not domain_manager.ensure_workspace(api_name, service_db):
            return jsonify({"error": _workspace_failure_message(api_name, service_db)}), 500

        configured_username = str(setup_cfg.get("username") or "").strip()
        configured_email = str(setup_cfg.get("email") or "").strip()
        configured_password = str(setup_cfg.get("password") or "").strip()

        body = request.get_json(silent=True) or {}
        username = str(body.get("username") or configured_username).strip()
        email = str(body.get("email") or configured_email).strip()
        password = str(body.get("password") or configured_password).strip()
        role = str(body.get("role") or setup_cfg.get("role") or "SUPER_ADMIN").strip()

        if not username or not email or not password:
            return jsonify({"error": "username, email and password are required"}), 400

        ok, existing = domain_manager.read_documents(collection_name, {"username": {"$eq": username}})
        if ok and isinstance(existing, list) and existing:
            existing_doc = existing[0] if isinstance(existing[0], dict) else {}
            updates = {}

            if str(existing_doc.get("email") or "").strip() != email:
                updates["email"] = email
            if str(existing_doc.get("role") or "").strip() != role:
                updates["role"] = role

            expected_hash = _hash_auth_bootstrap_password(password)
            if str(existing_doc.get("passwordHash") or "").strip() != expected_hash:
                updates["passwordHash"] = expected_hash
            if str(existing_doc.get("password") or "").strip():
                updates["password"] = ""

            if updates:
                updates["updatedAt"] = datetime.now(timezone.utc).isoformat()
                update_ok, update_result = domain_manager.update_document(
                    collection_name,
                    {"username": {"$eq": username}},
                    updates,
                )
                if not update_ok:
                    return jsonify({"error": update_result.get("error", "Failed to reset super admin")}), 500
                return jsonify({
                    "status": "updated",
                    "message": "Super admin already existed and credentials were reset",
                    "username": username,
                    "role": role,
                }), 200
            return jsonify({
                "status": "ready",
                "message": "Super admin already matched the requested credentials",
                "username": username,
                "role": role,
            }), 200

        payload = {
            "username": username,
            "email": email,
            "passwordHash": _hash_auth_bootstrap_password(password),
            "role": role,
            "rbac": {"scopes": ["SUPER_ADMIN"]},
            "profile": body.get("profile") if isinstance(body.get("profile"), dict) else {},
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        success, result = domain_manager.create_document(collection_name, payload)
        if not success:
            return jsonify({"error": result.get("error", "Failed to reset super admin")}), 500
        return jsonify({
            "status": "created",
            "message": "Super admin was created from the requested credentials",
            "username": username,
            "role": role,
        }), 200

    @api_app.route("/liwiro/setup/authenticate", methods=["POST"])
    def setup_authenticate():
        if _production_mode_enabled():
            return _management_route_json_unavailable()
        dependency_name = str((auth_cfg or {}).get("authServiceName") or "").strip()
        if bool((auth_cfg or {}).get("isAuthService", False)):
            return jsonify({"error": "This route is intended for auth-dependent services only"}), 400
        if not dependency_name:
            return jsonify({"error": "auth.authServiceName is required"}), 400

        auth_endpoint = (auth_cfg or {}).get("authServiceEndpoint") or {}
        direct_base_url = str(auth_endpoint.get("baseUrl") or "").rstrip("/") if isinstance(auth_endpoint, dict) else ""
        direct_sign_in_route = str(auth_endpoint.get("signInPath") or "").strip() if isinstance(auth_endpoint, dict) else ""
        target_service = None if direct_base_url and direct_sign_in_route else _service_registry_lookup_by_name(dependency_name)
        if direct_base_url and direct_sign_in_route:
            target_lapis = {}
            target_port = 0
            target_sign_in_route = direct_sign_in_route if direct_sign_in_route.startswith("/") else f"/{direct_sign_in_route}"
        else:
            target_lapis = (target_service or {}).get("lapis_config") or {}
        if not target_service:
            if not (direct_base_url and direct_sign_in_route):
                return jsonify({"error": f"Authentication service '{dependency_name}' was not found"}), 404
        if target_service and str(target_service.get("status") or "").upper() != "RUNNING":
            return jsonify({"error": f"Authentication service '{dependency_name}' is not running"}), 409

        if target_service:
            target_port_raw = target_service.get("port")
            if target_port_raw is None:
                return jsonify({"error": f"Authentication service '{dependency_name}' has no runtime port"}), 409
            try:
                target_port = int(float(str(target_port_raw).strip()))
            except Exception:
                return jsonify({"error": f"Authentication service '{dependency_name}' has invalid runtime port: {target_port_raw}"}), 409
            if target_port <= 0 or target_port > 65535:
                return jsonify({"error": f"Authentication service '{dependency_name}' has out-of-range runtime port: {target_port}"}), 409

        if target_service:
            target_base_path = str((target_lapis.get("metadata") or {}).get("basePath") or "").strip()
            target_auth = (target_lapis.get("auth") or {})
            target_custom = (target_auth.get("customEndpoints") or {})
            target_sign_in = str(target_custom.get("signIn") or "/signin")
            if not bool(target_custom.get("enabled", False)):
                target_sign_in = "/signin"
            target_sign_in_route = _join_route(target_base_path, target_sign_in)

        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            body = {}

        def _auth_signin_script_from_lapis():
            endpoints = (target_lapis.get("endpoints") or {})
            for endpoint_cfg in endpoints.values():
                if str(endpoint_cfg.get("operationType") or "").strip().lower() != "script":
                    continue
                if str(endpoint_cfg.get("method") or "GET").upper() != "POST":
                    continue
                endpoint_route = _join_route(target_base_path, endpoint_cfg.get("path", ""))
                if endpoint_route != target_sign_in_route:
                    continue
                script_src = endpoint_cfg.get("versaScript")
                if isinstance(script_src, str) and script_src.strip():
                    return _ensure_vi_module_imports(script_src)
            return ""

        def _auth_service_runtime_params():
            target_meta = (target_lapis.get("metadata") or {})
            target_env = dict((target_meta.get("env") or {}))
            target_env["PORT"] = str(target_port)
            target_service_db = str(target_meta.get("database") or "main").strip() or "main"
            params = dict(body)
            params["service"] = {
                "name": str(target_lapis.get("apiName") or dependency_name or "AuthService"),
                "basePath": target_base_path,
                "version": str(target_meta.get("version") or "1.0.0"),
                "database": target_service_db,
                "env": target_env,
            }
            params.setdefault("__request", {
                "method": "POST",
                "path": target_sign_in_route,
            })
            params["auth"] = {}
            return params, target_service_db

        try:
            response = requests.post(
                f"{direct_base_url}{target_sign_in_route}" if direct_base_url else f"http://127.0.0.1:{target_port}{target_sign_in_route}",
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=20,
            )
            content_type = str(response.headers.get("Content-Type") or "")
            if "application/json" in content_type.lower():
                payload = response.json()
                if response.ok and _is_vdb_script_metadata_echo(payload):
                    script_src = _auth_signin_script_from_lapis()
                    if not script_src:
                        return jsonify({
                            "error": "Auth service returned script metadata and no signin script was found in LAPIS config",
                            "upstream": payload,
                        }), 502
                    runtime_params, runtime_db = _auth_service_runtime_params()
                    fallback_ok, fallback_payload = _execute_vi_script(script_src, runtime_params, runtime_db)
                    if not fallback_ok:
                        return jsonify({
                            "error": "Authentication fallback execution failed",
                            "details": fallback_payload,
                            "upstream": payload,
                        }), 502
                    payload = fallback_payload
                if response.ok and isinstance(payload, dict):
                    authenticated = payload.get("authenticated")
                    if authenticated is False:
                        return jsonify(payload), 401
                    token = str(
                        payload.get("token")
                        or payload.get("access_token")
                        or payload.get("accessToken")
                        or payload.get("jwt")
                        or ""
                    ).strip()
                    if not token:
                        return jsonify({
                            "error": "Authentication failed: no bearer token returned by auth service",
                            "upstream": payload,
                        }), 401
                return jsonify(payload), response.status_code
            return Response(response.text, status=response.status_code, mimetype="text/plain")
        except Exception as exc:
            return jsonify({"error": f"Authentication request failed: {exc}"}), 502

    @api_app.route("/liwiro/setup/signout", methods=["POST"])
    def setup_signout():
        if _production_mode_enabled():
            return _management_route_json_unavailable()
        dependency_name = str((auth_cfg or {}).get("authServiceName") or "").strip()
        if bool((auth_cfg or {}).get("isAuthService", False)):
            return jsonify({"error": "This route is intended for auth-dependent services only"}), 400
        if not dependency_name:
            return jsonify({"error": "auth.authServiceName is required"}), 400

        target_service = _service_registry_lookup_by_name(dependency_name)
        if not target_service:
            return jsonify({"error": f"Authentication service '{dependency_name}' was not found"}), 404
        if str(target_service.get("status") or "").upper() != "RUNNING":
            return jsonify({"error": f"Authentication service '{dependency_name}' is not running"}), 409

        target_port_raw = target_service.get("port")
        if target_port_raw is None:
            return jsonify({"error": f"Authentication service '{dependency_name}' has no runtime port"}), 409
        try:
            target_port = int(float(str(target_port_raw).strip()))
        except Exception:
            return jsonify({"error": f"Authentication service '{dependency_name}' has invalid runtime port: {target_port_raw}"}), 409
        if target_port <= 0 or target_port > 65535:
            return jsonify({"error": f"Authentication service '{dependency_name}' has out-of-range runtime port: {target_port}"}), 409

        target_lapis = (target_service.get("lapis_config") or {})
        target_base_path = str((target_lapis.get("metadata") or {}).get("basePath") or "").strip()
        target_auth = (target_lapis.get("auth") or {})
        target_custom = (target_auth.get("customEndpoints") or {})
        target_sign_out = str(target_custom.get("signOut") or "/auth/signout")
        target_sign_out_route = _join_route(target_base_path, target_sign_out)

        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            body = {}
        inbound_auth = str(request.headers.get("Authorization") or "").strip()
        token = str(body.get("token") or "").strip()
        if not inbound_auth and token:
            inbound_auth = f"Bearer {token}"
        if not inbound_auth:
            return jsonify({"error": "Authorization bearer token required for signout"}), 401

        try:
            response = requests.post(
                f"http://127.0.0.1:{target_port}{target_sign_out_route}",
                json=body if isinstance(body, dict) else {},
                headers={"Content-Type": "application/json", "Authorization": inbound_auth},
                timeout=20,
            )
            content_type = str(response.headers.get("Content-Type") or "")
            if "application/json" in content_type.lower():
                payload = response.json()
                return jsonify(payload), response.status_code
            return Response(response.text, status=response.status_code, mimetype="text/plain")
        except Exception as exc:
            return jsonify({"error": f"Signout request failed: {exc}"}), 502

    @api_app.route("/liwiro/setup/seed-db", methods=["POST"])
    def setup_seed_db():
        if _production_mode_enabled():
            return _management_route_json_unavailable()
        seed_cfg = metadata_cfg.get("seedData") or {}
        if not bool(seed_cfg.get("enabled", False)):
            return jsonify({"error": "Seed setup is disabled in LAPIS metadata.seedData.enabled"}), 403
        ok, message = _setup_authorized()
        if not ok:
            return jsonify({"error": message}), 401

        body = request.get_json(silent=True) or {}
        collections_data = body.get("collections")
        if not isinstance(collections_data, dict):
            collections_data = seed_cfg.get("collections", {})
        if not isinstance(collections_data, dict) or not collections_data:
            return jsonify({"error": "No seed collections configured"}), 400

        if not domain_manager.ensure_workspace(api_name, service_db):
            return jsonify({"error": _workspace_failure_message(api_name, service_db)}), 500

        summary = {"inserted": 0, "failed": 0, "collections": {}}

        for source_name, docs in collections_data.items():
            if not isinstance(docs, list):
                summary["collections"][source_name] = {"inserted": 0, "failed": 1, "errors": ["Expected array of objects"]}
                summary["failed"] += 1
                continue

            collection_name = _resolve_model_collection(source_name) or source_name
            auth_model_name = str((auth_cfg or {}).get("authModel") or "").strip()
            auth_collection_name = _resolve_model_collection(auth_model_name)
            is_auth_collection = bool(
                bool((auth_cfg or {}).get("isAuthService", False))
                and auth_collection_name
                and str(collection_name).strip() == str(auth_collection_name).strip()
            )
            item = {"inserted": 0, "failed": 0, "errors": []}

            for doc in docs:
                if not isinstance(doc, dict):
                    item["failed"] += 1
                    summary["failed"] += 1
                    item["errors"].append("Document is not an object")
                    continue
                payload = _normalize_seed_document(doc, is_auth_collection=is_auth_collection)
                success, result = domain_manager.create_document(collection_name, payload)
                if success:
                    item["inserted"] += 1
                    summary["inserted"] += 1
                else:
                    item["failed"] += 1
                    summary["failed"] += 1
                    item["errors"].append(result.get("error", "insert failed"))

            summary["collections"][collection_name] = item

        return jsonify({"status": "completed", "summary": summary}), 200

    def _sign_jwt_for_user(user_doc: dict):
        if jwt is None:
            return False, "PyJWT not installed on service runtime", None
        verify_key, fallback_secret, _, _ = _jwt_verification_material()
        now = int(datetime.now(timezone.utc).timestamp())
        username = str(user_doc.get("username") or "").strip()
        rbac = user_doc.get("rbac") if isinstance(user_doc.get("rbac"), dict) else {}
        claims = {
            "sub": username,
            "username": username,
            "email": user_doc.get("email"),
            "role": user_doc.get("role", "USER"),
            "purpose": "access",
            "token_use": "bearer",
            "rbac": rbac,
            "sessionVersion": _current_auth_session_version(username),
            "iat": now,
            "exp": now + (60 * 60 * 12),
            "iss": api_name,
        }
        signing_candidates = []
        private_key = str((auth_cfg or {}).get("privateKey") or "").strip()
        if private_key:
            signing_candidates.append((private_key, "RS256"))
        key_management = str((auth_cfg or {}).get("keyManagement") or "auto").strip().lower()
        if fallback_secret and key_management != "manual":
            signing_candidates.append((fallback_secret, "HS256"))
        for key, algo in signing_candidates:
            try:
                token = jwt.encode(claims, key, algorithm=algo)
                return True, "", token
            except Exception:
                continue
        return False, "Unable to sign JWT with configured auth keys", None

    def _is_super_admin_claims(claims):
        if not isinstance(claims, dict):
            return False
        role = str(claims.get("role") or "").strip().upper().replace("-", "_")
        if role == "SUPER_ADMIN":
            return True
        rbac = claims.get("rbac") if isinstance(claims.get("rbac"), dict) else {}
        scopes = rbac.get("scopes") if isinstance(rbac.get("scopes"), list) else []
        abilities = rbac.get("abilities") if isinstance(rbac.get("abilities"), list) else []
        normalized = {str(x or "").strip().upper() for x in (scopes + abilities)}
        return "SUPER_ADMIN" in normalized or "MANAGE_USERS" in normalized or "MANAGE_AUTH_USERS" in normalized

    def _is_admin_or_super_admin_claims(claims):
        if _is_super_admin_claims(claims):
            return True
        if not isinstance(claims, dict):
            return False
        role = str(claims.get("role") or "").strip().upper().replace("-", "_")
        if role == "ADMIN":
            return True
        rbac = claims.get("rbac") if isinstance(claims.get("rbac"), dict) else {}
        scopes = rbac.get("scopes") if isinstance(rbac.get("scopes"), list) else []
        abilities = rbac.get("abilities") if isinstance(rbac.get("abilities"), list) else []
        normalized = {str(x or "").strip().upper() for x in (scopes + abilities)}
        return "ADMIN" in normalized or "MANAGE_USERS" in normalized or "MANAGE_AUTH_USERS" in normalized

    if bool((auth_cfg or {}).get("enabled", False)):
        custom_cfg = (auth_cfg or {}).get("customEndpoints") or {}
        signout_route = _join_route(base_path, str(custom_cfg.get("signOut") or "/auth/signout"))
        should_register_signout = ("POST", signout_route) not in configured_route_keys

        if should_register_signout:
            @api_app.route(signout_route, methods=["POST"], endpoint=f"{api_name}_auth_signout")
            def auth_signout():
                auth_header = str(request.headers.get("Authorization") or "")
                if not auth_header.startswith("Bearer "):
                    return jsonify({"error": "Bearer token required"}), 401
                token = auth_header.split(" ", 1)[1].strip()
                ok, message, claims = _verify_bearer_token(token)
                if not ok:
                    return jsonify({"error": message}), 401
                username = str((claims or {}).get("username") or (claims or {}).get("sub") or "").strip()
                _revoke_token(token)
                return jsonify({
                    "signedOut": True,
                    "tokenType": "Bearer",
                    "revoke": "service-token-hash",
                    "username": username,
                    "message": "Signed out. Presented bearer token is revoked on this service; clear token on client.",
                }), 200

    if bool((auth_cfg or {}).get("enabled", False)) and bool((auth_cfg or {}).get("isAuthService", False)):
        custom_cfg = (auth_cfg or {}).get("customEndpoints") or {}
        if bool(custom_cfg.get("enabled", False)):
            auth_model_name = auth_cfg.get("authModel")
            auth_collection_name = _resolve_model_collection(auth_model_name)
            signin_route = _join_route(base_path, str(custom_cfg.get("signIn") or "/auth/signin"))
            signup_route = _join_route(base_path, str(custom_cfg.get("signUp") or "/auth/signup"))
            register_route = _join_route(base_path, str(custom_cfg.get("register") or "/auth/register"))
            reset_route = _join_route(base_path, str(custom_cfg.get("resetPassword") or "/auth/reset-password"))
            should_register_signup = ("POST", signup_route) not in configured_route_keys
            should_register_signin = ("POST", signin_route) not in configured_route_keys
            should_register_register = ("POST", register_route) not in configured_route_keys
            should_register_reset_form = _auth_password_reset_page_enabled() and ("GET", reset_route) not in configured_route_keys

            if should_register_signup:
                @api_app.route(signup_route, methods=["POST"], endpoint=f"{api_name}_auth_signup")
                def auth_signup():
                    if not auth_collection_name:
                        return jsonify({"error": "auth.authModel is not mapped to a collection"}), 400
                    body = request.get_json(silent=True) or {}
                    username = str(body.get("username") or "").strip()
                    email = str(body.get("email") or "").strip()
                    password = str(body.get("password") or "").strip()
                    role = str(body.get("role") or "USER").strip().upper().replace("-", "_")
                    if role == "APP":
                        role = "APPLICATION"
                    if not username or not email or not password:
                        return jsonify({"error": "username, email and password are required"}), 400
                    if role in {"ADMIN", "SUPER_ADMIN"}:
                        return jsonify({"error": "signup cannot create ADMIN or SUPER_ADMIN users"}), 403
                    ok, existing = domain_manager.read_documents(auth_collection_name, {"username": {"$eq": username}})
                    if ok and isinstance(existing, list) and existing:
                        return jsonify({"error": "User already exists"}), 409
                    payload = {
                        "username": username,
                        "email": email,
                        "passwordHash": generate_password_hash(password),
                        "role": role,
                        "rbac": body.get("rbac") if isinstance(body.get("rbac"), dict) else {"scopes": ["SELF_SERVICE"]},
                        "createdAt": datetime.now(timezone.utc).isoformat(),
                    }
                    success, result = domain_manager.create_document(auth_collection_name, payload)
                    if not success:
                        return jsonify({"error": result.get("error", "Failed to create user")}), 500
                    return jsonify({"status": "created", "username": username, "role": role, "rbac": payload.get("rbac")}), 201

            if should_register_register:
                @api_app.route(register_route, methods=["POST"], endpoint=f"{api_name}_auth_register")
                def auth_register():
                    if not auth_collection_name:
                        return jsonify({"error": "auth.authModel is not mapped to a collection"}), 400
                    auth_header = str(request.headers.get("Authorization") or "")
                    if not auth_header.startswith("Bearer "):
                        return jsonify({"error": "Super admin bearer token required"}), 401
                    token = auth_header.split(" ", 1)[1].strip()
                    ok, message, claims = _verify_bearer_token(token)
                    if not ok:
                        return jsonify({"error": message}), 401
                    if not _is_admin_or_super_admin_claims(claims):
                        return jsonify({"error": "Admin or super-admin role required for registration"}), 403

                    body = request.get_json(silent=True) or {}
                    username = str(body.get("username") or "").strip()
                    email = str(body.get("email") or "").strip()
                    password = str(body.get("password") or "").strip()
                    role = str(body.get("role") or "USER").strip().upper().replace("-", "_")
                    if role == "APP":
                        role = "APPLICATION"
                    if not username or not email or not password:
                        return jsonify({"error": "username, email and password are required"}), 400
                    if role == "SUPER_ADMIN":
                        return jsonify({"error": "register route cannot create SUPER_ADMIN users"}), 403
                    ok, existing = domain_manager.read_documents(auth_collection_name, {"username": {"$eq": username}})
                    if ok and isinstance(existing, list) and existing:
                        return jsonify({"error": "User already exists"}), 409
                    payload = {
                        "username": username,
                        "email": email,
                        "passwordHash": generate_password_hash(password),
                        "role": role,
                        "rbac": body.get("rbac") if isinstance(body.get("rbac"), dict) else {"scopes": ["USER"]},
                        "createdAt": datetime.now(timezone.utc).isoformat(),
                    }
                    success, result = domain_manager.create_document(auth_collection_name, payload)
                    if not success:
                        return jsonify({"error": result.get("error", "Failed to create user")}), 500
                    return jsonify({"status": "created", "username": username, "role": role, "rbac": payload.get("rbac")}), 201

            if should_register_reset_form:
                @api_app.route(reset_route, methods=["GET"], endpoint=f"{api_name}_auth_reset_password_form")
                def auth_reset_password_form():
                    token = str(request.args.get("token") or "").strip()
                    page_copy = _auth_password_reset_page_copy(reset_route, bool(token))
                    reset_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(page_copy["title"])}</title>
  <style>
    :root {{ color-scheme: light; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; font-family: "Manrope", "Segoe UI", system-ui, sans-serif; background: linear-gradient(180deg, #ecfdf5 0%, #dcfce7 48%, #f8fafc 100%); color: #052e16; }}
    .shell {{ width: min(100%, 760px); background: rgba(255,255,255,0.96); border: 1px solid #bbf7d0; border-radius: 22px; box-shadow: 0 24px 60px rgba(5,46,22,0.12); overflow: hidden; }}
    .hero {{ padding: 28px 30px 18px; background: linear-gradient(135deg, #14532d 0%, #166534 56%, #15803d 100%); color: #f0fdf4; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    p {{ margin: 0; line-height: 1.6; }}
    .body {{ padding: 28px 30px 30px; }}
    .stack {{ display: grid; gap: 14px; }}
    label {{ font-size: 13px; font-weight: 700; letter-spacing: 0.02em; }}
    input {{ width: 100%; border: 1px solid #86efac; border-radius: 12px; padding: 12px 14px; font-size: 15px; color: #14532d; background: #f0fdf4; }}
    input:focus {{ outline: 2px solid #22c55e; outline-offset: 2px; }}
    button {{ border: 0; border-radius: 12px; background: #15803d; color: #f0fdf4; padding: 12px 16px; font-size: 15px; font-weight: 700; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 10px; }}
    button:hover {{ background: #166534; }}
    button:disabled {{ opacity: 0.6; cursor: not-allowed; }}
    .button-dots {{ display: none; align-items: flex-end; gap: 4px; min-width: 22px; }}
    button.loading .button-dots {{ display: inline-flex; }}
    button.loading .button-label {{ opacity: 0.88; }}
    .button-dot {{ width: 6px; height: 6px; border-radius: 999px; background: currentColor; animation: button-dot-bounce 0.9s infinite ease-in-out; }}
    .button-dot:nth-child(2) {{ animation-delay: 0.15s; }}
    .button-dot:nth-child(3) {{ animation-delay: 0.3s; }}
    .status {{ border-radius: 14px; padding: 12px 14px; background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; font-size: 14px; white-space: pre-wrap; }}
    .status.error {{ background: #fef2f2; border-color: #fecaca; color: #991b1b; }}
    .meta {{ display: grid; gap: 4px; color: #166534; font-size: 13px; }}
    @keyframes button-dot-bounce {{
      0%, 80%, 100% {{ transform: translateY(0); opacity: 0.45; }}
      40% {{ transform: translateY(-5px); opacity: 1; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <h1>{escape(page_copy["title"])}</h1>
      <p>{escape(page_copy["description"])}</p>
    </section>
    <section class="body">
      <div class="stack">
        <div class="meta">
          <span>Route: <strong>{escape(reset_route)}</strong></span>
          <span>{escape(page_copy["routeNote"])}</span>
        </div>
        <div id="resetStatus" class="status">{escape(page_copy["statusText"])}</div>
        <label for="resetToken">Reset token</label>
        <input id="resetToken" value="{escape(token)}" placeholder="Paste the password-reset token" autocomplete="off" />
        <label for="newPassword">New password</label>
        <input id="newPassword" type="password" placeholder="Enter a strong replacement password" autocomplete="new-password" />
        <button id="submitReset" type="button">
          <span class="button-label">{escape(page_copy["submitLabel"])}</span>
          <span class="button-dots" aria-hidden="true">
            <span class="button-dot"></span>
            <span class="button-dot"></span>
            <span class="button-dot"></span>
          </span>
        </button>
      </div>
    </section>
  </main>
  <script>
    const button = document.getElementById("submitReset");
    const tokenInput = document.getElementById("resetToken");
    const passwordInput = document.getElementById("newPassword");
    const statusEl = document.getElementById("resetStatus");
    const loadingMessage = {json.dumps(page_copy["loadingMessage"])};
    const successMessage = {json.dumps(page_copy["successMessage"])};
    const failureMessage = {json.dumps(page_copy["failureMessage"])};

    function setButtonLoading(isLoading) {{
      button.disabled = isLoading;
      button.classList.toggle("loading", isLoading);
    }}

    async function submitReset() {{
      const tokenValue = String(tokenInput.value || "").trim();
      const newPassword = String(passwordInput.value || "").trim();
      if (!tokenValue || !newPassword) {{
        statusEl.className = "status error";
        statusEl.textContent = "Both the reset token and the new password are required.";
        return;
      }}
      setButtonLoading(true);
      statusEl.className = "status";
      statusEl.textContent = loadingMessage;
      try {{
        const res = await fetch(window.location.pathname, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ token: tokenValue, newPassword }}),
        }});
        const text = await res.text();
        let parsed = text;
        try {{ parsed = JSON.parse(text); }} catch (_err) {{}}
        statusEl.className = res.ok ? "status" : "status error";
        statusEl.textContent = (res.ok ? `${{successMessage}}\\n\\n` : `${{failureMessage}}\\n\\n`) + (typeof parsed === "string" ? parsed : JSON.stringify(parsed, null, 2));
        if (res.ok) {{
          passwordInput.value = "";
        }}
      }} catch (err) {{
        statusEl.className = "status error";
        statusEl.textContent = "Request failed: " + (err && err.message ? err.message : "unknown error");
      }} finally {{
        setButtonLoading(false);
      }}
    }}

    button.addEventListener("click", submitReset);
    passwordInput.addEventListener("keydown", (event) => {{
      if (event.key === "Enter") {{
        event.preventDefault();
        submitReset();
      }}
    }});
  </script>
</body>
</html>"""
                    return Response(reset_html, mimetype="text/html")

            if should_register_signin:
                @api_app.route(signin_route, methods=["POST"], endpoint=f"{api_name}_auth_signin")
                def auth_signin():
                    if not auth_collection_name:
                        return jsonify({"error": "auth.authModel is not mapped to a collection"}), 400
                    body = request.get_json(silent=True) or {}
                    username = str(body.get("username") or "").strip()
                    password = str(body.get("password") or "").strip()
                    if not username or not password:
                        return jsonify({"error": "username and password are required"}), 400
                    ok, existing = domain_manager.read_documents(auth_collection_name, {"username": {"$eq": username}})
                    if not ok or not isinstance(existing, list) or not existing:
                        return jsonify({"error": "Invalid credentials"}), 401
                    user_doc = existing[0]
                    stored_hash = str(user_doc.get("passwordHash") or "").strip()
                    if stored_hash:
                        if not check_password_hash(stored_hash, password):
                            return jsonify({"error": "Invalid credentials"}), 401
                    else:
                        legacy_password = str(user_doc.get("password") or "")
                        if not legacy_password or legacy_password != password:
                            return jsonify({"error": "Invalid credentials"}), 401
                        upgraded_hash = generate_password_hash(password)
                        domain_manager.update_document(
                            auth_collection_name,
                            {"username": {"$eq": username}},
                            {
                                "passwordHash": upgraded_hash,
                                "password": "",
                                "updatedAt": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                        user_doc["passwordHash"] = upgraded_hash
                        user_doc["password"] = ""
                    signed, message, token = _sign_jwt_for_user(user_doc)
                    if not signed:
                        return jsonify({"error": message}), 500
                    return jsonify({"token": token, "tokenType": "Bearer", "user": {
                        "username": user_doc.get("username"),
                        "email": user_doc.get("email"),
                        "role": user_doc.get("role", "USER"),
                        "rbac": user_doc.get("rbac") if isinstance(user_doc.get("rbac"), dict) else {},
                    }}), 200

    @api_app.route("/docs", methods=["GET"])
    @api_app.route("/openapi", methods=["GET"])
    @api_app.route("/openapi.json", methods=["GET"])
    def docs_disabled():
        if _production_mode_enabled():
            return _management_route_json_unavailable()
        return jsonify({"error": "FastAPI/OpenAPI docs are disabled. Use /liwiro/docs"}), 404

    def liwiro_docs_json():
        if _production_mode_enabled():
            return _management_route_json_unavailable()
        if not _docs_enabled():
            return jsonify({"error": "Service documentation is disabled"}), 404
        if not _docs_authorized():
            return jsonify({"error": "Documentation key required"}), 401
        payload = _build_docs_payload()
        auth_context = payload.get("authContext", {}) if isinstance(payload, dict) else {}
        auth_service_name = str((auth_context or {}).get("authServiceName") or "").strip()
        if auth_service_name:
            service_doc = _service_registry_lookup_by_name(auth_service_name)
            # An auth service can render its docs before its registry record is
            # visible (for example, during first-start). Its own users should
            # still be available to the same authenticator picker.
            if not service_doc and bool((auth_cfg or {}).get("isAuthService", False)):
                service_doc = {"apiName": api_name, "lapis_config": lapis_config}
            if service_doc:
                auth_context["authUsers"] = _load_auth_service_users(service_doc)
                target_lapis = (service_doc.get("lapis_config") or {})
                target_base_path = str((target_lapis.get("metadata") or {}).get("basePath") or "").strip()
                target_auth = (target_lapis.get("auth") or {})
                target_custom = (target_auth.get("customEndpoints") or {})
                target_sign_in = str(target_custom.get("signIn") or "/auth/signin")
                if not bool(target_custom.get("enabled", False)):
                    target_sign_in = "/auth/signin"
                auth_context["authSignInRoute"] = _join_route(target_base_path, target_sign_in)
                target_default_super = (target_auth.get("defaultSuperAdmin") or {})
                if isinstance(payload.get("setupRoutes"), list):
                    for setup_route in payload["setupRoutes"]:
                        if not isinstance(setup_route, dict):
                            continue
                        if str(setup_route.get("kind") or "").strip().lower() != "authenticate":
                            continue
                        route_payload = setup_route.get("payloadTemplate")
                        if not isinstance(route_payload, dict):
                            route_payload = {}
                        if not str(route_payload.get("username") or "").strip():
                            route_payload["username"] = str(target_default_super.get("username") or "").strip()
                        if not str(route_payload.get("password") or "").strip():
                            route_payload["password"] = str(target_default_super.get("password") or "").strip()
                        if not str(route_payload.get("email") or "").strip():
                            route_payload["email"] = str(target_default_super.get("email") or "").strip()
                        setup_route["payloadTemplate"] = route_payload
            payload["authContext"] = auth_context
        return jsonify(payload)

    def liwiro_docs_set_endpoint_enabled(endpoint_id: str):
        if _production_mode_enabled():
            return _management_route_json_unavailable()
        if not _docs_enabled():
            return jsonify({"error": "Service documentation is disabled"}), 404
        if not _docs_authorized():
            return jsonify({"error": "Documentation key required"}), 401

        endpoint_key = str(endpoint_id or "").strip()
        endpoint_map = lapis_config.get("endpoints") or {}
        endpoint_cfg = endpoint_map.get(endpoint_key)
        if not endpoint_key or not isinstance(endpoint_cfg, dict):
            return jsonify({"error": "Endpoint not found"}), 404

        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or "enabled" not in body:
            return jsonify({"error": "`enabled` boolean is required"}), 400

        next_enabled = bool(body.get("enabled"))
        endpoint_cfg["enabled"] = next_enabled

        next_lapis = json.loads(json.dumps(lapis_config))
        next_endpoint_cfg = ((next_lapis.get("endpoints") or {}).get(endpoint_key) or {})
        if not isinstance(next_endpoint_cfg, dict):
            return jsonify({"error": "Endpoint not found"}), 404
        next_endpoint_cfg["enabled"] = next_enabled
        persisted = _persist_service_lapis_config(next_lapis)

        return jsonify({
            "endpointId": endpoint_key,
            "enabled": next_enabled,
            "persisted": persisted,
            "message": f"Endpoint {'enabled' if next_enabled else 'disabled'}",
        }), 200

    def liwiro_docs():
        if _production_mode_enabled():
            return _management_route_html_unavailable()
        if not _docs_enabled():
            return Response(
                "<html><body><h2>Service documentation is disabled for this service.</h2></body></html>",
                status=404,
                mimetype="text/html",
            )
        page_title = escape(f"{api_name} Documentation")
        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{page_title}</title>
  <style>
    :root {{ color-scheme: light; }}
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Manrope", "Segoe UI", system-ui, sans-serif; background: linear-gradient(180deg, #f7faff 0%, #f2f6fc 100%); color: #0f172a; line-height: 1.5; }}
    .wrap {{ max-width: 1380px; margin: 24px auto; padding: 0 20px 56px; }}
    .card {{ background: #fff; border: 1px solid #dbe3ef; border-radius: 14px; padding: 24px; margin-bottom: 18px; box-shadow: 0 8px 24px rgba(15,23,42,0.05); }}
    h1 {{ margin: 0 0 8px 0; font-size: 28px; }}
    h2 {{ margin: 0 0 10px; font-size: 20px; }}
    h3 {{ margin: 0 0 8px; font-size: 16px; }}
    p {{ margin: 6px 0; }}
    .muted {{ color: #475569; }}
    .row {{ display: grid; grid-template-columns: 180px 1fr; gap: 10px; margin: 4px 0; align-items: center; }}
    .stack {{ display: grid; gap: 12px; }}
    input, textarea {{ width: 100%; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px; font-size: 14px; }}
    textarea {{ min-height: 132px; font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace; line-height: 1.55; }}
    button {{ border: 0; border-radius: 8px; background: #0f766e; color: #fff; padding: 10px 14px; cursor: pointer; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; gap: 10px; }}
    button:hover {{ background: #0e685f; }}
    button.secondary {{ background: #0f172a; }}
    button.secondary:hover {{ background: #020617; }}
    .button-dots {{ display: none; align-items: flex-end; gap: 4px; min-width: 22px; }}
    button.loading .button-dots {{ display: inline-flex; }}
    button.loading .button-label {{ opacity: 0.88; }}
    .button-dot {{ width: 6px; height: 6px; border-radius: 999px; background: currentColor; animation: button-dot-bounce 0.9s infinite ease-in-out; }}
    .button-dot:nth-child(2) {{ animation-delay: 0.15s; }}
    .button-dot:nth-child(3) {{ animation-delay: 0.3s; }}
    .docs-shell {{ display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 18px; align-items: start; }}
    .docs-sidebar {{ position: sticky; top: 18px; align-self: start; border: 1px solid #dbe3ef; border-radius: 18px; background: rgba(255,255,255,0.92); padding: 14px; box-shadow: 0 16px 38px rgba(15,23,42,0.08); max-height: calc(100vh - 36px); overflow: auto; }}
    .docs-main {{ min-width: 0; }}
    .sidebar-heading {{ margin: 0 0 10px; font-size: 11px; font-weight: 800; letter-spacing: 0.18em; text-transform: uppercase; color: #0f766e; }}
    .sidebar-group + .sidebar-group {{ margin-top: 14px; padding-top: 14px; border-top: 1px solid #e2e8f0; }}
    .sidebar-list {{ display: grid; gap: 6px; }}
    .sidebar-link {{ display: block; border-radius: 10px; padding: 8px 10px; font-size: 13px; color: #0f172a; text-decoration: none; background: transparent; border: 1px solid transparent; }}
    .sidebar-link:hover {{ background: #f0fdfa; border-color: #99f6e4; color: #115e59; }}
    .sidebar-link small {{ display: block; color: #64748b; }}
    .overview-card {{ scroll-margin-top: 28px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid #dbe3ef; padding: 9px; text-align: left; vertical-align: top; }}
    th {{ background: #f8fafc; }}
    code {{ background: #eef2ff; padding: 1px 6px; border-radius: 6px; }}
    pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.55; }}
    .error {{ color: #b91c1c; font-weight: 600; }}
    .ok {{ color: #065f46; font-weight: 600; }}
    .route {{ border: 1px solid #dbe3ef; border-radius: 16px; padding: 18px; margin: 14px 0; background: #fff; scroll-margin-top: 28px; }}
    .route-head {{ display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 14px; margin-bottom: 12px; }}
    .route-title {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; min-width: 0; }}
    .route-head-actions {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }}
    .top-actions {{ position: sticky; top: 0; display: flex; justify-content: flex-end; margin: 8px 0 12px; z-index: 5; }}
    .pill {{ display: inline-flex; align-items: center; border: 1px solid #dbe3ef; border-radius: 999px; padding: 4px 10px; font-size: 12px; color: #334155; background: #f8fafc; }}
    .route-tab {{ border: 1px solid #cbd5e1; border-radius: 999px; background: #fff; color: #0f172a; padding: 7px 12px; font-size: 12px; font-weight: 700; }}
    .route-tab:hover {{ background: #f8fafc; }}
    .route-tab.active {{ background: #0f766e; border-color: #0f766e; color: #fff; }}
    .route-tab.docs.active {{ background: #166534; border-color: #166534; }}
    .route-panel {{ display: none; min-height: 360px; }}
    .route-panel.active {{ display: block; }}
    .request-box {{ border: 1px solid #dbe3ef; border-radius: 12px; background: #f8fbff; padding: 14px; overflow: hidden; min-height: 360px; }}
    .response-box {{ border: 1px solid #1e3a8a; border-radius: 12px; background: #082f49; color: #dbeafe; padding: 12px; min-height: 360px; overflow: hidden; }}
    .response-box, .response-box * {{ max-width: 100%; box-sizing: border-box; }}
    .docs-box {{ border: 1px solid #166534; border-radius: 14px; background: linear-gradient(180deg, #14532d 0%, #166534 58%, #15803d 100%); color: #ecfdf5; padding: 16px; min-height: 360px; }}
    .docs-box code {{ background: rgba(240,253,244,0.16); color: #f0fdf4; }}
    .docs-summary {{ margin-bottom: 14px; padding: 12px 14px; border: 1px solid rgba(240,253,244,0.18); border-radius: 12px; background: rgba(240,253,244,0.08); }}
    .docs-section {{ margin-top: 12px; padding: 12px 14px; border: 1px solid rgba(240,253,244,0.16); border-radius: 12px; background: rgba(240,253,244,0.08); }}
    .docs-section h4 {{ margin: 0 0 8px; font-size: 13px; letter-spacing: 0.06em; text-transform: uppercase; }}
    .docs-status-row {{ display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 14px; padding: 12px 14px; border: 1px solid rgba(240,253,244,0.18); border-radius: 12px; background: rgba(240,253,244,0.1); }}
    .docs-status-copy {{ display: grid; gap: 4px; }}
    .docs-status-copy strong {{ font-size: 14px; }}
    .route-toggle {{ background: #e0f2fe; color: #0f172a; border: 1px solid rgba(224,242,254,0.65); }}
    .route-toggle:hover {{ background: #bae6fd; }}
    .request-meta {{ margin: 0 0 8px; font-size: 12px; color: #475569; }}
    .params-block {{ display: grid; gap: 10px; margin-top: 6px; }}
    .route-actions {{ display: flex; gap: 10px; align-items: center; justify-content: flex-start; }}
    .response-actions {{ display: flex; justify-content: flex-end; margin-bottom: 8px; }}
    .response-token-row {{ display: flex; gap: 8px; align-items: center; margin: 0 5px 8px; }}
    .response-token-row input {{ background: #0b2447; color: #eff6ff; border: 1px solid #3b82f6; }}
    .copy-response, .copy-token {{ background: #1e3a8a; border: 1px solid #3b82f6; color: #eff6ff; border-radius: 8px; padding: 4px 10px; font-size: 12px; cursor: pointer; }}
    .copy-response:hover, .copy-token:hover {{ background: #334155; }}
    .response-output-wrap {{ display: flex; width: 100%; min-width: 0; min-height: 220px; overflow: hidden; padding: 5px; }}
    .route-response-output {{ display: block; width: 100%; max-width: 100%; min-height: 100%; border: 1px solid #1e3a8a; border-radius: 10px; background: #082f49; color: #dbeafe; padding: 10px; overflow: hidden; resize: none; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; }}
    .mono {{ font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .password-wrap {{ position: relative; }}
    .password-toggle {{ position: absolute; right: 8px; top: 50%; transform: translateY(-50%); border: 0; background: transparent; color: #475569; cursor: pointer; font-size: 13px; padding: 4px; }}
    .password-toggle:hover {{ color: #0f172a; }}
    .password-wrap input {{ padding-right: 44px; }}
    @keyframes button-dot-bounce {{
      0%, 80%, 100% {{ transform: translateY(0); opacity: 0.45; }}
      40% {{ transform: translateY(-5px); opacity: 1; }}
    }}
    @media (max-width: 1100px) {{
      .docs-shell {{ grid-template-columns: 1fr; }}
      .docs-sidebar {{ position: static; max-height: none; }}
    }}
    @media (max-width: 900px) {{
      .row {{ grid-template-columns: 1fr; }}
      .route-head {{ flex-direction: column; }}
      .route-head-actions {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top-actions">
      <button id="lockButton" class="secondary" style="display:none; margin: 10px 8px 0 0;">🔒 Lock Docs</button>
    </div>
    <div id="unlockCard" class="card">
      <h1>{escape(api_name)} Service Documentation</h1>
      <p class="muted">This documentation is protected. Use the service documentation key configured for this service.</p>
      <form id="unlockForm">
        <div class="row">
          <label for="docsKey">Documentation Key</label>
          <input id="docsKey" name="docsKey" type="password" autocomplete="current-password" required />
        </div>
        <div style="margin-top:10px;">
          <button type="submit">Unlock Documentation</button>
        </div>
      </form>
      <p id="status" class="muted"></p>
    </div>
    <div id="docsRoot" style="display:none;"></div>
  </div>
  <script>
    const form = document.getElementById("unlockForm");
    const statusEl = document.getElementById("status");
    const unlockCard = document.getElementById("unlockCard");
    const docsRoot = document.getElementById("docsRoot");
    const lockButton = document.getElementById("lockButton");
    let docsKey = "";
    let capturedBearerToken = "";
    let capturedTokenClaims = null;
    let docsResizeHandler = null;

    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, (ch) => {{
        if (ch === "&") return "&amp;";
        if (ch === "<") return "&lt;";
        if (ch === ">") return "&gt;";
        if (ch === '"') return "&quot;";
        return "&#39;";
      }});
    }}

    function toPretty(value) {{
      if (value === null || value === undefined) return "-";
      if (typeof value === "string") return value || "-";
      return JSON.stringify(value, null, 2);
    }}

    function decodeJwtPayload(token) {{
      try {{
        const parts = String(token || "").split(".");
        if (parts.length < 2) return null;
        const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
        const json = atob(payload.padEnd(payload.length + (4 - payload.length % 4) % 4, "="));
        const parsed = JSON.parse(json);
        return parsed && typeof parsed === "object" ? parsed : null;
      }} catch (_err) {{
        return null;
      }}
    }}

    function attachPasswordToggles(root) {{
      const scope = root || document;
      scope.querySelectorAll('input[type="password"]').forEach((input) => {{
        if (input.dataset.passwordToggleBound === "1") return;
        input.dataset.passwordToggleBound = "1";
        const wrapper = document.createElement("div");
        wrapper.className = "password-wrap";
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "password-toggle";
        toggle.textContent = "Show";
        toggle.setAttribute("aria-label", "Toggle password visibility");
        toggle.addEventListener("click", () => {{
          const nextType = input.type === "password" ? "text" : "password";
          input.type = nextType;
          toggle.textContent = nextType === "password" ? "Show" : "Hide";
        }});
        wrapper.appendChild(toggle);
      }});
    }}

    function getResponseTextarea(endpointId) {{
      const wrap = document.getElementById(`${{endpointId}}-response-wrap`);
      if (!wrap) return document.getElementById(`${{endpointId}}-response`);
      let responseEl = wrap.querySelector("textarea");
      if (!responseEl) {{
        responseEl = document.createElement("textarea");
        responseEl.readOnly = true;
        wrap.appendChild(responseEl);
      }}
      wrap.querySelectorAll("textarea").forEach((node, index) => {{
        if (index > 0) node.remove();
      }});
      responseEl.id = `${{endpointId}}-response`;
      responseEl.className = "mono route-response-output";
      responseEl.readOnly = true;
      return responseEl;
    }}

    function syncResponseTextareaHeight(endpointId, responseEl) {{
      const wrap = document.getElementById(`${{endpointId}}-response-wrap`);
      const textarea = responseEl || document.getElementById(`${{endpointId}}-response`);
      if (!textarea) return;
      textarea.style.height = "0px";
      const targetHeight = Math.max(textarea.scrollHeight, wrap ? wrap.clientHeight : 0, 220);
      textarea.style.height = `${{targetHeight}}px`;
    }}

    function setResponseToken(endpointId, token) {{
      const wrap = document.getElementById(`${{endpointId}}-token-wrap`);
      const input = document.getElementById(`${{endpointId}}-token`);
      if (!wrap || !input) return;
      const value = String(token || "").trim();
      input.value = value;
      wrap.style.display = value ? "block" : "none";
    }}

    function applyCapturedTokenToProtectedRoutes(endpoints) {{
      if (!capturedBearerToken) return;
      (endpoints || []).forEach((endpoint) => {{
        if (!endpoint || !endpoint.requiresAuth) return;
        const endpointId = `ep-${{endpoint.id}}`;
        const bearerInput = document.getElementById(`${{endpointId}}-bearer`);
        if (bearerInput && !String(bearerInput.value || "").trim()) bearerInput.value = capturedBearerToken;
      }});
    }}

    function applyEndpointDefaults(endpoint, endpointId) {{
      if (!endpoint) return;
      const queryEl = document.getElementById(`${{endpointId}}-query`);
      const bodyEl = document.getElementById(`${{endpointId}}-body`);
      const bearerEl = document.getElementById(`${{endpointId}}-bearer`);
      const ex = endpoint.exampleParams || {{}};
      if (queryEl) queryEl.value = JSON.stringify(ex.query || {{}}, null, 2);
      if (bodyEl) bodyEl.value = JSON.stringify(ex.body || {{}}, null, 2);
      if (endpoint.requiresAuth && capturedBearerToken) {{
        if (bearerEl) bearerEl.value = capturedBearerToken;
      }} else {{
        const exAuth = ex.headers && (ex.headers.Authorization || ex.headers.authorization || "");
        if (typeof exAuth === "string" && exAuth.startsWith("Bearer ")) {{
          if (bearerEl) bearerEl.value = exAuth.slice(7);
        }} else if (typeof exAuth === "string") {{
          if (bearerEl) bearerEl.value = exAuth;
        }}
      }}
    }}

    function renderAuthSession() {{
      const box = document.getElementById("auth-session-box");
      const pre = document.getElementById("auth-session-pre");
      if (!box || !pre) return;
      if (!capturedTokenClaims) {{
        box.style.display = "none";
        pre.textContent = "No token captured yet.";
        return;
      }}
      box.style.display = "block";
      pre.textContent = JSON.stringify({{
        username: capturedTokenClaims.username || capturedTokenClaims.sub || "",
        role: capturedTokenClaims.role || "",
        rbac: capturedTokenClaims.rbac || {{}},
      }}, null, 2);
    }}

    function routeAnchorId(ep) {{
      return `route-${{ep.id || Math.random().toString(36).slice(2)}}`;
    }}

    function buildSetupDocumentation(ep) {{
      const bodyExample = JSON.stringify((ep.exampleParams && ep.exampleParams.body) || {{}}, null, 2);
      return {{
        summary: `Setup route for ${{ep.path || "/"}}.`,
        description: ep.developerNotes || "Bootstrap or service-maintenance helper exposed through Liwiro docs.",
        sections: [
          {{
            title: "Authorization",
            body: ep.requiresAuth
              ? "Bearer authentication is required before this setup route can run."
              : "This setup route uses the service setup key rather than bearer authentication unless otherwise noted.",
          }},
          {{
            title: "Payload Template",
            body: `Request body example:\\n${{bodyExample || "{{}}"}}`,
          }},
          {{
            title: "Operational Notes",
            body: ep.enabled
              ? "This setup route is currently enabled in the service configuration."
              : "This setup route is currently disabled in the service configuration.",
          }},
        ],
      }};
    }}

    function normalizeDocumentation(ep) {{
      const supplied = ep && ep.documentation && typeof ep.documentation === "object" ? ep.documentation : null;
      const summary = String((supplied && supplied.summary) || "").trim();
      const description = String((supplied && supplied.description) || "").trim();
      const sections = Array.isArray(supplied && supplied.sections)
        ? supplied.sections
            .filter((section) => section && typeof section === "object")
            .map((section) => ({{
              title: String(section.title || "").trim(),
              body: String(section.body || "").trim(),
            }}))
            .filter((section) => section.title && section.body)
        : [];
      if (summary || description || sections.length) {{
        return {{ summary, description, sections }};
      }}
      return ep && ep.__setup ? buildSetupDocumentation(ep) : {{
        summary: `${{ep.method || "GET"}} ${{ep.path || "/"}} route documentation.`,
        description: ep.developerNotes || "This endpoint definition did not include custom documentation.",
        sections: [],
      }};
    }}

    function renderDocumentationPanel(ep, endpointRootId) {{
      const documentation = normalizeDocumentation(ep);
      const enabled = ep && ep.enabled !== false;
      const sectionsHtml = (documentation.sections || []).map((section) => `
        <section class="docs-section">
          <h4>${{escapeHtml(section.title)}}</h4>
          <pre>${{escapeHtml(section.body)}}</pre>
        </section>
      `).join("");
      return `
        <div class="route-panel" data-panel="docs">
          <div class="docs-box">
            <div class="docs-summary">
              <h3 style="margin:0 0 8px;">Endpoint Documentation</h3>
              <p>${{escapeHtml(documentation.summary || "No summary provided.")}}</p>
              ${{documentation.description ? `<p>${{escapeHtml(documentation.description)}}</p>` : ""}}
            </div>
            <div class="docs-status-row">
              <div class="docs-status-copy">
                <span style="font-size:11px; letter-spacing:0.14em; text-transform:uppercase;">Route Status</span>
                <strong>${{enabled ? "Enabled" : "Disabled"}}</strong>
                <span>${{enabled ? "Requests are accepted for this endpoint." : "Requests are blocked until the endpoint is re-enabled."}}</span>
              </div>
              ${{ep && ep.toggleable !== false ? `
              <button
                data-config-endpoint="${{escapeHtml(ep.id || "")}}"
                data-endpoint-root-id="${{escapeHtml(endpointRootId || "")}}"
                data-current-enabled="${{enabled ? "true" : "false"}}"
                class="route-toggle"
                type="button"
              >${{enabled ? "Disable Endpoint" : "Enable Endpoint"}}</button>` : ""}}
            </div>
            ${{sectionsHtml || `<section class="docs-section"><h4>Notes</h4><pre>${{escapeHtml(ep.developerNotes || "No additional documentation sections were supplied for this endpoint.")}}</pre></section>`}}
          </div>
        </div>
      `;
    }}

    function setRouteTab(endpointId, nextTab) {{
      const routeEl = document.querySelector(`[data-endpoint-root="${{endpointId}}"]`);
      if (!routeEl) return;
      routeEl.querySelectorAll(".route-tab").forEach((button) => {{
        const isActive = button.getAttribute("data-tab") === nextTab;
        button.classList.toggle("active", isActive);
      }});
      routeEl.querySelectorAll(".route-panel").forEach((panel) => {{
        const isActive = panel.getAttribute("data-panel") === nextTab;
        panel.classList.toggle("active", isActive);
      }});
      if (nextTab === "response") {{
        syncResponseTextareaHeight(endpointId);
      }}
    }}

    function setAsyncButtonState(button, isLoading) {{
      if (!button) return;
      const lockedDisabled = button.dataset.disabledByConfig === "true";
      button.disabled = isLoading || lockedDisabled;
      button.classList.toggle("loading", isLoading);
    }}

    function renderEndpoint(ep) {{
      const endpointId = `ep-${{ep.id || Math.random().toString(36).slice(2)}}`;
      const anchorId = routeAnchorId(ep);
      const routeLabel = ep.__setup ? "Setup" : "Route";
      const enabled = ep && ep.enabled !== false;
      const authProfiles = Array.isArray(ep.__authProfiles) ? ep.__authProfiles : [];
      const isAuthenticationRoute = ep.__setupKind === "authenticate" || (ep.__authSignInRoute && ep.path === ep.__authSignInRoute);
      return `
      <div class="route" id="${{anchorId}}" data-endpoint-root="${{endpointId}}">
        <div class="route-head">
          <div style="min-width:0;">
            <div class="route-title">
              <h3 style="margin:0;">
                <code>${{escapeHtml(ep.method || "GET")}}</code>
                <code>${{escapeHtml(ep.path || "/")}}</code>
              </h3>
              <span class="pill">${{escapeHtml(ep.operationType || "unknown")}}</span>
              <span class="pill">${{enabled ? "enabled" : "disabled"}}</span>
              ${{ep.crudOperation ? `<span class="pill">${{escapeHtml(ep.crudOperation)}}</span>` : ""}}
              ${{ep.requiresAuth ? `<span class="pill">requiresAuth</span>` : ""}}
            </div>
            ${{ep.developerNotes ? `<p><strong>${{routeLabel}} notes:</strong> ${{escapeHtml(ep.developerNotes)}}</p>` : ""}}
          </div>
          <div class="route-head-actions">
            <button data-endpoint="${{escapeHtml(endpointId)}}" data-tab="request" class="route-tab active" type="button">Request</button>
            <button data-endpoint="${{escapeHtml(endpointId)}}" data-tab="response" class="route-tab" type="button">Response</button>
            <button data-endpoint="${{escapeHtml(endpointId)}}" data-tab="docs" class="route-tab docs" type="button">Docs</button>
          </div>
        </div>
        <div id="${{endpointId}}-route">
          <div class="route-panel active" data-panel="request">
            <div class="request-box">
              <p class="request-meta">Request</p>
              <div class="stack">
                ${{ep.__setup ? `
                <label>Setup API Key</label>
                <input id="${{endpointId}}-setup-key" type="password" placeholder="Shared setup API key from LAPIS metadata.setupApiKey" />` : ""}}
                <div class="route-actions">
                  <button data-endpoint="${{escapeHtml(endpointId)}}" class="apply-default-inputs" type="button">Populate default inputs</button>
                </div>
                <div id="${{endpointId}}-params" class="params-block">
                  ${{isAuthenticationRoute && authProfiles.length ? `
                  <label>Authenticate as user</label>
                  <select id="${{endpointId}}-auth-profile" class="auth-profile-picker" data-endpoint="${{escapeHtml(endpointId)}}">
                    <option value="">Choose an auth-service user</option>
                    ${{authProfiles.map((profile) => `<option value="${{escapeHtml(profile.username || "")}}" data-email="${{escapeHtml(profile.email || "")}}">${{escapeHtml(profile.username || "")}} (${{escapeHtml(profile.role || "USER")}})</option>`).join("")}}
                  </select>` : ""}}
                  <label>Query JSON</label>
                  <textarea id="${{endpointId}}-query" class="mono"></textarea>
                  <label>Request Body JSON</label>
                  <textarea id="${{endpointId}}-body" class="mono"></textarea>
                  <label>${{ep.requiresAuth ? "Bearer Token" : "Bearer Token (optional)"}}</label>
                  <input id="${{endpointId}}-bearer" class="mono" />
                </div>
                <div class="route-actions">
                  <button
                    data-endpoint="${{escapeHtml(endpointId)}}"
                    class="try-route"
                    data-disabled-by-config="${{enabled ? "false" : "true"}}"
                    ${{enabled ? "" : "disabled"}}
                  >
                    <span class="button-label">${{ep.__setup ? "Run Setup" : "Try Route"}}</span>
                    <span class="button-dots" aria-hidden="true">
                      <span class="button-dot"></span>
                      <span class="button-dot"></span>
                      <span class="button-dot"></span>
                    </span>
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div class="route-panel" data-panel="response">
            <div class="response-box">
              <p class="request-meta" style="color:#93c5fd;">Response</p>
              <div class="response-actions">
                <button data-endpoint="${{escapeHtml(endpointId)}}" class="copy-response" type="button" title="Copy response">Copy</button>
              </div>
              <div id="${{endpointId}}-token-wrap" class="response-token-row" style="display:none;">
                <input id="${{endpointId}}-token" class="mono" readonly />
                <button data-endpoint="${{escapeHtml(endpointId)}}" class="copy-token" type="button" title="Copy bearer token">Copy Token</button>
              </div>
              <div id="${{endpointId}}-response-wrap" class="response-output-wrap">
                <textarea id="${{endpointId}}-response" class="mono route-response-output" readonly>Run the route to see response.</textarea>
              </div>
            </div>
          </div>
          ${{renderDocumentationPanel(ep, endpointId)}}
        </div>
      </div>`;
    }}

    function renderMediaCapabilities(mediaCapabilities, basePath) {{
      const media = mediaCapabilities && typeof mediaCapabilities === "object" ? mediaCapabilities : {{}};
      const providers = Array.isArray(media.providers) ? media.providers : [];
      const inputModes = Array.isArray(media.inputModes) ? media.inputModes : [];
      if (!providers.length) return "";

      const normalizedBase = String(basePath || "").trim();
      const defaultProviderLabel = (() => {{
        const match = providers.find((provider) => provider && provider.id === media.defaultProvider);
        if (match && match.label) return String(match.label);
        return String(media.defaultProvider || "").trim() || "-";
      }})();

      const providerCards = providers.map((provider) => {{
        const envKeys = Array.isArray(provider && provider.envKeys) ? provider.envKeys : [];
        const routes = Array.isArray(provider && provider.routes) ? provider.routes : [];
        const testInputs = Array.isArray(provider && provider.inputModes) ? provider.inputModes : [];
        const routeHtml = routes.length
          ? routes.map((route) => {{
              const rawPath = String(route.path || "/").trim() || "/";
              const prefixedPath = normalizedBase && rawPath.startsWith("/") && !rawPath.startsWith(normalizedBase)
                ? `${{normalizedBase.replace(/\\/+$/, "")}}${{rawPath}}`
                : rawPath;
              return `<code>${{escapeHtml(String(route.method || "GET").toUpperCase())}} ${{escapeHtml(prefixedPath || "/")}}</code>`;
            }}).join(" ")
          : '<span class="muted">No upload routes detected.</span>';
        const envHtml = envKeys.length
          ? envKeys.map((key) => `<code>${{escapeHtml(key)}}</code>`).join(" ")
          : '<span class="muted">No media env keys found.</span>';
        const inputHtml = testInputs.length
          ? testInputs.map((value) => `<code>${{escapeHtml(value)}}</code>`).join(" ")
          : '<span class="muted">No test inputs listed.</span>';
        return `
          <div style="margin-top:12px; border:1px solid #dbe3ef; border-radius:14px; background:#f8fbff; padding:14px;">
            <div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-bottom:8px;">
              <strong>${{escapeHtml(provider.label || provider.id || "Provider")}}</strong>
              <span class="pill">${{provider.ready ? "ready" : "needs env values"}}</span>
              ${{provider.default ? '<span class="pill">default</span>' : ""}}
            </div>
            <div class="row"><strong>Routes</strong><span>${{routeHtml}}</span></div>
            <div class="row"><strong>Env Keys</strong><span>${{envHtml}}</span></div>
            <div class="row"><strong>Test Inputs</strong><span>${{inputHtml}}</span></div>
          </div>
        `;
      }}).join("");

      const summaryInputs = inputModes.length
        ? inputModes.map((value) => `<code>${{escapeHtml(value)}}</code>`).join(" ")
        : "-";

      return `
        <div id="media-capabilities-section" style="margin-top:18px;">
          <h3>Media Integrations</h3>
          <p class="muted">This service exposes media storage through Versa script routes. Route testing in Liwiro docs uses JSON request bodies.</p>
          <div class="row"><strong>Asset Collection</strong><span><code>${{escapeHtml(media.assetCollection || "-")}}</code></span></div>
          <div class="row"><strong>Default Provider</strong><span>${{escapeHtml(defaultProviderLabel)}}</span></div>
          <div class="row"><strong>JSON Test Inputs</strong><span>${{summaryInputs}}</span></div>
          ${{media.jsonRequestOnly ? '<p class="muted" style="margin-top:10px;">Use JSON body fields like <code>sourceUrl</code>, <code>dataUri</code>, <code>dataBase64</code>, or <code>textBody</code>. Multipart uploads are not generated by the Liwiro route tester.</p>' : ""}}
          ${{providerCards}}
        </div>
      `;
    }}

    function renderDocs(payload) {{
      const endpoints = Array.isArray(payload.endpoints) ? payload.endpoints : [];
      const setupRoutes = Array.isArray(payload.setupRoutes) ? payload.setupRoutes : [];
      const authContext = payload.authContext && typeof payload.authContext === "object" ? payload.authContext : {{}};
      const authUsers = Array.isArray(authContext.authUsers) ? authContext.authUsers : [];
      const mediaCapabilities = payload.mediaCapabilities && typeof payload.mediaCapabilities === "object" ? payload.mediaCapabilities : {{}};
      const mediaProviders = Array.isArray(mediaCapabilities.providers) ? mediaCapabilities.providers : [];
      const setupEndpoints = setupRoutes.map((route, idx) => {{
        const routePath = String(route.path || "").toLowerCase();
        const kind = route.kind || (
          (routePath.endsWith("/auth/signin") || routePath.endsWith("/signin")) || routePath.endsWith("/liwiro/setup/authenticate")
            ? "authenticate"
            : (routePath.endsWith("/auth/signout") || routePath.endsWith("/liwiro/setup/signout")
                ? "signout"
                : (routePath.endsWith("/auth/register") ? "register" : "setup"))
        );
        const requiresAuth = kind === "register" || kind === "signout";
        return {{
          id: `setup_${{idx}}`,
          method: String(route.method || "POST").toUpperCase(),
          path: String(route.path || "/"),
          operationType: "setup",
          requiresAuth,
          developerNotes: String(route.description || ""),
          documentation: buildSetupDocumentation({{
            path: route.path,
            method: route.method,
            requiresAuth,
            developerNotes: route.description,
            exampleParams: {{ body: route.payloadTemplate || {{}} }},
            enabled: Boolean(route.enabled),
          }}),
          exampleParams: {{
            query: {{}},
            body: route.payloadTemplate || {{}},
            headers: {{}},
          }},
          __setup: true,
          __setupKind: kind,
          enabled: Boolean(route.enabled),
        }};
      }});
      const allRoutes = [...setupEndpoints, ...endpoints].map((endpoint) => ({{
        ...endpoint,
        __authProfiles: authUsers,
        __authSignInRoute: authContext.authSignInRoute || "",
      }}));
      const sidebarLink = (ep) => `
        <a class="sidebar-link" href="#${{routeAnchorId(ep)}}">
          <span>${{escapeHtml(ep.method || "GET")}} ${{escapeHtml(ep.path || "/")}}</span>
          <small>${{escapeHtml(ep.operationType || "route")}}</small>
        </a>
      `;
      const routes = allRoutes.filter((endpoint) => !endpoint.__setup).map(renderEndpoint).join("");
      const setupCards = allRoutes.filter((endpoint) => endpoint.__setup).map(renderEndpoint).join("");
      const setupLinks = setupEndpoints.map(sidebarLink).join("");
      const routeLinks = endpoints.map(sidebarLink).join("");

      docsRoot.innerHTML = `
        <div class="docs-shell">
          <aside class="docs-sidebar">
            <div class="sidebar-group">
              <p class="sidebar-heading">Overview</p>
              <div class="sidebar-list">
                <a class="sidebar-link" href="#overview-section">
                  <span>Service Overview</span>
                  <small>Runtime, auth, notes</small>
                </a>
                ${{authUsers.length ? `
                <a class="sidebar-link" href="#auth-users-section">
                  <span>Authenticator Users</span>
                  <small>Seeded auth principals</small>
                </a>` : ""}}
                ${{mediaProviders.length ? `
                <a class="sidebar-link" href="#media-capabilities-section">
                  <span>Media Integrations</span>
                  <small>Providers, routes, inputs</small>
                </a>` : ""}}
                <a class="sidebar-link" href="#auth-session-box">
                  <span>Captured Auth Context</span>
                  <small>Bearer token claims</small>
                </a>
              </div>
            </div>
            ${{setupEndpoints.length ? `
            <div class="sidebar-group">
              <p class="sidebar-heading">Setup Endpoints</p>
              <div class="sidebar-list">${{setupLinks}}</div>
            </div>` : ""}}
            <div class="sidebar-group">
              <p class="sidebar-heading">Service Endpoints</p>
              <div class="sidebar-list">
                <a class="sidebar-link" href="#routes-section">
                  <span>All Routes</span>
                  <small>Interactive testing</small>
                </a>
                ${{routeLinks || '<span class="sidebar-link"><span>No endpoints configured</span><small>Nothing to index</small></span>'}}
              </div>
            </div>
          </aside>
          <div class="docs-main">
            <div id="overview-section" class="card overview-card">
              <h2 style="margin-top:0;">Overview</h2>
              <div class="row"><strong>Title</strong><span>${{escapeHtml(payload.title || "-")}}</span></div>
              <div class="row"><strong>Version</strong><span>${{payload.version || "-"}}</span></div>
              <div class="row"><strong>Base Path</strong><span><code>${{payload.basePath || "/"}}</code></span></div>
              <div class="row"><strong>Database</strong><span>${{payload.database || "-"}}</span></div>
              <div class="row"><strong>Auth Service</strong><span>${{escapeHtml(authContext.authServiceName || "-")}}</span></div>
              <div class="row"><strong>Auth Sign-In Route</strong><span><code>${{escapeHtml(authContext.authSignInRoute || "-")}}</code></span></div>
              ${{payload.developerNotes ? `<p><strong>Developer notes:</strong> ${{escapeHtml(payload.developerNotes)}}</p>` : ""}}
              ${{renderMediaCapabilities(mediaCapabilities, payload.basePath)}}
              ${{authUsers.length ? `<div id="auth-users-section">
                <h3>Authenticator Users</h3>
                <table><thead><tr><th>Username</th><th>Role</th><th>RBAC</th></tr></thead><tbody>
                  ${{authUsers.map((u) => `<tr><td>${{escapeHtml(u.username || "")}}</td><td>${{escapeHtml(u.role || "")}}</td><td><code>${{escapeHtml(JSON.stringify(u.rbac || {{}}))}}</code></td></tr>`).join("")}}
                </tbody></table>
              </div>` : ""}}
              <div id="auth-session-box" class="route" style="display:none;">
                <h3>Authenticated User Context</h3>
                <pre id="auth-session-pre">No token captured yet.</pre>
              </div>
            </div>
            ${{setupEndpoints.length ? `<div id="setup-section" class="card">
              <h3 style="margin-top:0;">Setup Endpoints</h3>
              <p class="muted">Setup routes are indexed in the sidebar and documented with the same Request, Response, and Docs views as primary endpoints.</p>
              ${{setupCards}}
            </div>` : ""}}
            <div id="routes-section" class="card">
              <h3 style="margin-top:0;">Service Endpoints</h3>
              <p class="muted">Use Request, Response, and Docs to switch between live testing and full endpoint documentation.</p>
              ${{routes || "<p>No endpoints configured.</p>"}}
            </div>
          </div>
        </div>`;
      docsRoot.style.display = "block";

      document.querySelectorAll(".route-tab").forEach((btn) => {{
        btn.addEventListener("click", (e) => {{
          e.preventDefault();
          const endpointId = btn.getAttribute("data-endpoint");
          const tab = btn.getAttribute("data-tab") || "request";
          setRouteTab(endpointId, tab);
        }});
      }});

      document.querySelectorAll(".route-toggle").forEach((btn) => {{
        btn.addEventListener("click", async (e) => {{
          e.preventDefault();
          const configEndpointId = btn.getAttribute("data-config-endpoint");
          const endpointRootId = btn.getAttribute("data-endpoint-root-id");
          const currentEnabled = btn.getAttribute("data-current-enabled") !== "false";
          if (!configEndpointId) return;
          setAsyncButtonState(btn, true);
          try {{
            const toggleResponse = await fetch(`/liwiro/docs/endpoints/${{encodeURIComponent(configEndpointId)}}/enabled`, {{
              method: "POST",
              headers: {{
                "Content-Type": "application/json",
                "X-Docs-Key": docsKey,
              }},
              body: JSON.stringify({{ enabled: !currentEnabled }}),
            }});
            const togglePayload = await toggleResponse.json();
            if (!toggleResponse.ok) {{
              throw new Error(togglePayload.error || "Failed to update endpoint status");
            }}

            const docsResponse = await fetch("/liwiro/docs.json", {{
              headers: {{ "X-Docs-Key": docsKey }},
            }});
            const docsPayload = await docsResponse.json();
            if (!docsResponse.ok) {{
              throw new Error(docsPayload.error || "Failed to reload documentation");
            }}

            renderDocs(docsPayload);
            const anchor = document.getElementById(`route-${{configEndpointId}}`);
            if (anchor) {{
              anchor.scrollIntoView({{ block: "start", behavior: "smooth" }});
            }}
            if (endpointRootId) {{
              setRouteTab(endpointRootId, "docs");
            }}
          }} catch (_err) {{
            btn.textContent = "Toggle Failed";
            setTimeout(() => {{
              btn.textContent = currentEnabled ? "Disable Endpoint" : "Enable Endpoint";
            }}, 1400);
          }} finally {{
            setAsyncButtonState(btn, false);
          }}
        }});
      }});

      document.querySelectorAll(".try-route").forEach((btn) => {{
        btn.addEventListener("click", async (e) => {{
          e.preventDefault();
          const endpointId = btn.getAttribute("data-endpoint");
          const endpoint = allRoutes.find((item) => `ep-${{item.id}}` === endpointId);
          if (!endpoint) return;
          const responseEl = getResponseTextarea(endpointId);
          const queryRaw = document.getElementById(`${{endpointId}}-query`).value.trim();
          const bodyRaw = document.getElementById(`${{endpointId}}-body`).value.trim();
          const bearer = document.getElementById(`${{endpointId}}-bearer`).value.trim();
          const setupKey = endpoint.__setup ? String((document.getElementById(`${{endpointId}}-setup-key`) || {{ value: "" }}).value || "").trim() : "";

          let query = {{}};
          let body = null;
          try {{
            if (queryRaw) query = JSON.parse(queryRaw);
            if (bodyRaw) body = JSON.parse(bodyRaw);
          }} catch (err) {{
            setResponseToken(endpointId, "");
            responseEl.value = "Invalid JSON in query/body: " + err.message;
            syncResponseTextareaHeight(endpointId, responseEl);
            setRouteTab(endpointId, "response");
            return;
          }}

          const params = new URLSearchParams();
          if (endpoint.operationType === "script") {{
            params.append("__query", JSON.stringify(query || {{}}));
          }} else {{
            Object.entries(query || {{}}).forEach(([k, v]) => {{
              if (v === undefined || v === null) return;
              params.append(k, typeof v === "object" ? JSON.stringify(v) : String(v));
            }});
          }}

          const url = endpoint.path + (params.toString() ? `?${{params.toString()}}` : "");
          const method = String(endpoint.method || "GET").toUpperCase();
          const allowBody = method !== "GET" && method !== "HEAD";
          const headers = {{}};
          if (allowBody && body !== null) headers["Content-Type"] = "application/json";
          if (bearer) headers["Authorization"] = `Bearer ${{bearer}}`;
          if (endpoint.__setup) {{
            headers["X-Liwiro-Setup-Key"] = setupKey;
          }}
          setAsyncButtonState(btn, true);
          setResponseToken(endpointId, "");
          responseEl.value = "Sending request...";
          syncResponseTextareaHeight(endpointId, responseEl);
          try {{
            const res = await fetch(url, {{
              method,
              headers,
              body: allowBody && body !== null ? JSON.stringify(body) : undefined,
            }});
            const text = await res.text();
            let parsed = text;
            try {{ parsed = JSON.parse(text); }} catch (_e) {{}}
            if (res.ok && parsed && typeof parsed === "object") {{
              const tokenType = String(parsed.tokenType || parsed.token_type || parsed.type || "Bearer").trim();
              const rawToken = parsed.token ?? parsed.access_token ?? parsed.accessToken ?? parsed.jwt ?? "";
              let token = typeof rawToken === "string" ? rawToken.trim() : "";
              if (token.toLowerCase().startsWith("bearer ")) {{
                token = token.slice(7).trim();
              }}
              if (token && tokenType.toLowerCase() === "bearer") {{
                setResponseToken(endpointId, token);
                capturedBearerToken = token;
                capturedTokenClaims = decodeJwtPayload(token);
                applyCapturedTokenToProtectedRoutes(allRoutes);
                renderAuthSession();
              }}
            }}
            const isSignOutEndpoint = endpoint.__setupKind === "signout" || String(endpoint.path || "").toLowerCase().endsWith("/signout");
            if (res.ok && isSignOutEndpoint) {{
              setResponseToken(endpointId, "");
              capturedBearerToken = "";
              capturedTokenClaims = null;
              allRoutes.forEach((ep) => {{
                if (!ep || !ep.requiresAuth) return;
                const epId = `ep-${{ep.id}}`;
                const bearerInput = document.getElementById(`${{epId}}-bearer`);
                if (bearerInput) bearerInput.value = "";
              }});
              renderAuthSession();
            }}
            responseEl.value = `HTTP ${{res.status}} ${{res.statusText}}\\n` +
              `Request URL: ${{url}}\\n` +
              `Method: ${{method}}\\n\\n` +
              toPretty(parsed);
            syncResponseTextareaHeight(endpointId, responseEl);
            setRouteTab(endpointId, "response");
          }} catch (err) {{
            setResponseToken(endpointId, "");
            responseEl.value = "Request failed: " + err.message;
            syncResponseTextareaHeight(endpointId, responseEl);
            setRouteTab(endpointId, "response");
          }} finally {{
            setAsyncButtonState(btn, false);
          }}
        }});
      }});

      document.querySelectorAll(".apply-default-inputs").forEach((btn) => {{
        btn.addEventListener("click", (e) => {{
          e.preventDefault();
          const endpointId = btn.getAttribute("data-endpoint");
          const endpoint = allRoutes.find((item) => `ep-${{item.id}}` === endpointId);
          applyEndpointDefaults(endpoint, endpointId);
        }});
      }});

      document.querySelectorAll(".auth-profile-picker").forEach((picker) => {{
        picker.addEventListener("change", () => {{
          const endpointId = picker.getAttribute("data-endpoint");
          const bodyEl = endpointId ? document.getElementById(`${{endpointId}}-body`) : null;
          const selected = picker.options[picker.selectedIndex];
          if (!bodyEl || !selected || !selected.value) return;
          let body = {{}};
          try {{ body = bodyEl.value.trim() ? JSON.parse(bodyEl.value) : {{}}; }} catch (_err) {{ body = {{}}; }}
          body.username = selected.value;
          const email = String(selected.getAttribute("data-email") || "").trim();
          if (email) body.email = email;
          bodyEl.value = JSON.stringify(body, null, 2);
        }});
      }});

      allRoutes.forEach((endpoint) => {{
        const endpointId = `ep-${{endpoint.id}}`;
        applyEndpointDefaults(endpoint, endpointId);
        syncResponseTextareaHeight(endpointId);
      }});

      if (docsResizeHandler) {{
        window.removeEventListener("resize", docsResizeHandler);
      }}
      docsResizeHandler = () => {{
        allRoutes.forEach((endpoint) => {{
          syncResponseTextareaHeight(`ep-${{endpoint.id}}`);
        }});
      }};
      window.addEventListener("resize", docsResizeHandler);

      document.querySelectorAll(".copy-response").forEach((btn) => {{
        btn.addEventListener("click", async (e) => {{
          e.preventDefault();
          const endpointId = btn.getAttribute("data-endpoint");
          const responseEl = getResponseTextarea(endpointId);
          if (!responseEl) return;
          const text = String(responseEl.value || "");
          try {{
            await navigator.clipboard.writeText(text);
            btn.textContent = "Copied";
            setTimeout(() => {{
              btn.textContent = "Copy";
            }}, 1200);
          }} catch (_err) {{
            btn.textContent = "Failed";
            setTimeout(() => {{
              btn.textContent = "Copy";
            }}, 1200);
          }}
        }});
      }});

      document.querySelectorAll(".copy-token").forEach((btn) => {{
        btn.addEventListener("click", async (e) => {{
          e.preventDefault();
          const endpointId = btn.getAttribute("data-endpoint");
          const input = document.getElementById(`${{endpointId}}-token`);
          const text = String((input && input.value) || "");
          if (!text.trim()) return;
          try {{
            await navigator.clipboard.writeText(text);
            btn.textContent = "Copied";
            setTimeout(() => {{
              btn.textContent = "Copy Token";
            }}, 1200);
          }} catch (_err) {{
            btn.textContent = "Failed";
            setTimeout(() => {{
              btn.textContent = "Copy Token";
            }}, 1200);
          }}
        }});
      }});

      attachPasswordToggles(docsRoot);
      renderAuthSession();
    }}

    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      docsKey = document.getElementById("docsKey").value;
      statusEl.textContent = "Loading documentation...";
      statusEl.className = "muted";
      try {{
        const response = await fetch("/liwiro/docs.json", {{
          headers: {{ "X-Docs-Key": docsKey }}
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.error || "Failed to load docs");
        }}
        lockButton.style.display = "inline-block";
        unlockCard.style.display = "none";
        renderDocs(payload);
      }} catch (error) {{
        statusEl.textContent = error.message || "Documentation key validation failed.";
        statusEl.className = "error";
      }}
    }});

    lockButton.addEventListener("click", async () => {{
      docsRoot.style.display = "none";
      unlockCard.style.display = "block";
      lockButton.style.display = "none";
      docsKey = "";
      capturedBearerToken = "";
      capturedTokenClaims = null;
      const keyInput = document.getElementById("docsKey");
      if (keyInput) keyInput.value = "";
      statusEl.textContent = "Documentation locked. Enter password again to reopen.";
      statusEl.className = "muted";
    }});

    attachPasswordToggles(document);
  </script>
</body>
</html>"""
        return Response(html, mimetype="text/html")

    docs_route_prefix = _normalize_segment(base_path).rstrip("/")
    docs_json_routes = ["/liwiro/docs.json"]
    docs_html_routes = ["/liwiro/docs"]
    docs_toggle_routes = ["/liwiro/docs/endpoints/<endpoint_id>/enabled"]
    if docs_route_prefix and docs_route_prefix != "/":
        docs_json_routes.append(f"{docs_route_prefix}/liwiro/docs.json")
        docs_html_routes.append(f"{docs_route_prefix}/liwiro/docs")
        docs_toggle_routes.append(f"{docs_route_prefix}/liwiro/docs/endpoints/<endpoint_id>/enabled")

    for idx, route in enumerate(docs_json_routes):
        api_app.add_url_rule(
            route,
            endpoint=f"{api_name}_liwiro_docs_json_{idx}",
            view_func=liwiro_docs_json,
            methods=["GET"],
        )
    for idx, route in enumerate(docs_html_routes):
        api_app.add_url_rule(
            route,
            endpoint=f"{api_name}_liwiro_docs_html_{idx}",
            view_func=liwiro_docs,
            methods=["GET"],
        )
    for idx, route in enumerate(docs_toggle_routes):
        api_app.add_url_rule(
            route,
            endpoint=f"{api_name}_liwiro_docs_toggle_endpoint_{idx}",
            view_func=liwiro_docs_set_endpoint_enabled,
            methods=["POST"],
        )

    def create_resource(model_name):
        if not domain_manager.ensure_workspace(api_name, service_db):
            return jsonify({"error": _workspace_failure_message(api_name, service_db)}), 500
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid data format"}), 400

        success, result = domain_manager.create_document(model_name, data)
        if success:
            return jsonify({"message": f"Resource created in {model_name}", "created": True, "result": result}), 201
        return jsonify({"error": result.get('error', 'Creation failed')}), 500

    def read_resource(model_name):
        if not domain_manager.ensure_workspace(api_name, service_db):
            return jsonify({"error": _workspace_failure_message(api_name, service_db)}), 500
        query, query_error = _extract_request_query_payload(request.args)
        if query_error:
            return jsonify({"error": query_error}), 400
        success, data = domain_manager.read_documents(model_name, query)
        if success:
            return jsonify(data), 200
        return jsonify({"error": "Failed to read resources"}), 500

    def update_resource(model_name):
        if not domain_manager.ensure_workspace(api_name, service_db):
            return jsonify({"error": _workspace_failure_message(api_name, service_db)}), 500
        query, query_error = _extract_request_query_payload(request.args)
        if query_error:
            return jsonify({"error": query_error}), 400
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid data format"}), 400
        success, result = domain_manager.update_document(model_name, query, data)
        if not success:
            return jsonify({"error": (result or {}).get("error", "Update failed")}), 500
        updated_count = _extract_result_count(result, "updated", "affected_count", "count")
        if updated_count == 0:
            return jsonify({
                "error": "Resource not found for update",
                "updated": False,
                "notFound": True,
                "query": query,
                "result": result,
            }), 404
        return jsonify({
            "message": f"Resource updated in {model_name}",
            "updated": True,
            "count": updated_count,
            "result": result,
        }), 200

    def delete_resource(model_name):
        if not domain_manager.ensure_workspace(api_name, service_db):
            return jsonify({"error": _workspace_failure_message(api_name, service_db)}), 500
        query, query_error = _extract_request_query_payload(request.args)
        if query_error:
            return jsonify({"error": query_error}), 400
        success, result = domain_manager.delete_document(model_name, query)
        if success:
            deleted_count = _extract_result_count(result, "deleted", "affected_count", "count")
            if deleted_count == 0:
                return jsonify({
                    "error": "Resource not found for deletion",
                    "deleted": False,
                    "notFound": True,
                    "query": query,
                    "result": result,
                }), 404
            return jsonify({
                "message": f"Resource deleted from {model_name}",
                "deleted": True,
                "count": deleted_count,
                "result": result,
            }), 200
        return jsonify({"error": (result or {}).get("error", "Deletion failed")}), 500

    def run_custom_vql(endpoint_cfg):
        if not domain_manager.ensure_workspace(api_name, service_db):
            return jsonify({"error": _workspace_failure_message(api_name, service_db)}), 500
        query_text = endpoint_cfg.get("vqlQuery", "")
        if not isinstance(query_text, str) or not query_text.strip():
            return jsonify({"error": "Missing custom VQL query"}), 400
        from app.vdb_commands import parse_command, command_text
        try:
            query_obj = parse_command(query_text)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        request_query, query_error = _extract_request_query_payload(request.args)
        if query_error:
            return jsonify({"error": query_error}), 400
        request_body = request.get_json(silent=True)
        if request_body is not None and not isinstance(request_body, dict):
            return jsonify({"error": "Custom VQL body must be a JSON object"}), 400
        try:
            query_obj = _merge_custom_vql_request(query_obj, request_query, request_body)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        success, result = domain_manager.vdb_client.execute_vql_query(command_text(query_obj))
        if success:
            return jsonify(result), 200
        return jsonify({"error": result.get("error", "VQL execution failed")}), 500

    for endpoint_id, endpoint_config in lapis_config["endpoints"].items():
        method = endpoint_config["method"]
        path = endpoint_config["path"]
        operation_type = endpoint_config["operationType"]
        crud_operation = endpoint_config.get("crudOperation")
        linked_model = endpoint_config.get("linkedModel")

        collection_name = None
        if operation_type == "crud":
            if not linked_model:
                current_app.logger.error(f"Endpoint {endpoint_id} missing linked model.")
                continue

            for _, model_def in lapis_config["models"].items():
                if model_def["name"] == linked_model:
                    collection_name = model_def.get("collection", linked_model)
                    break

            if not collection_name:
                current_app.logger.error(f"No collection found for model: {linked_model}")
                continue

        def make_handler(op_type, crud_op, coll_name, endpoint_cfg, endpoint_key):
            if op_type == "crud":
                if crud_op == "create":
                    return lambda: create_resource(coll_name)
                if crud_op == "read":
                    return lambda: read_resource(coll_name)
                if crud_op == "update":
                    return lambda: update_resource(coll_name)
                if crud_op == "delete":
                    return lambda: delete_resource(coll_name)
            elif op_type == "script":
                script_code = _ensure_vi_module_imports(endpoint_cfg.get("versaScript"))
                script_name = f"{api_name}_{endpoint_key}"
                script_ready = False

                if script_code:
                    created, _ = domain_manager.vdb_client.create_script(script_name, api_name, script_code)
                    script_ready = bool(created)
                else:
                    current_app.logger.warning(f"Script endpoint {endpoint_key} has empty script payload.")

                def _run_script():
                    nonlocal script_ready
                    if script_code and not script_ready:
                        created, result = domain_manager.vdb_client.create_script(script_name, api_name, script_code)
                        if not created:
                            return jsonify({"error": result.get("error", "Script creation failed")}), 500
                        script_ready = True
                    if not domain_manager.ensure_workspace(api_name, service_db):
                        return jsonify({"error": _workspace_failure_message(api_name, service_db)}), 500

                    body = request.get_json(silent=True)
                    body_params = body if isinstance(body, dict) else {}
                    query_params, query_error = _extract_request_query_payload(request.args)
                    if query_error:
                        return jsonify({"error": query_error}), 400
                    params = {**query_params, **body_params}
                    params["query"] = dict(query_params)
                    params["body"] = dict(body_params)
                    bearer_token = ""
                    if hasattr(request, "liwiro_bearer_token"):
                        bearer_token = str(getattr(request, "liwiro_bearer_token") or "").strip()
                    if not bearer_token:
                        auth_header = str(request.headers.get("Authorization") or "")
                        if auth_header.startswith("Bearer "):
                            bearer_token = auth_header.split(" ", 1)[1].strip()
                    if bearer_token:
                        params.setdefault("bearerToken", bearer_token)
                        params.setdefault("authToken", bearer_token)
                        params.setdefault("token", bearer_token)
                    # Common auth aliases from clients: `userame` typo and single-field identifiers.
                    if not str(params.get("username") or "").strip():
                        alias_username = str(params.get("userame") or "").strip()
                        if alias_username:
                            params["username"] = alias_username
                    identifier = str(params.get("identifier") or params.get("login") or "").strip()
                    if identifier:
                        if "@" in identifier:
                            params.setdefault("email", identifier)
                        else:
                            params.setdefault("username", identifier)
                    if (
                        not str(params.get("email") or "").strip()
                        and "@" in str(params.get("username") or "").strip()
                    ):
                        params["email"] = str(params.get("username") or "").strip()
                    params["service"] = {
                        "name": api_name,
                        "basePath": base_path,
                        "version": version,
                        "database": service_db,
                        "env": dict(service_env),
                        "modules": list(service_modules),
                    }
                    # Auth scripts use ``req.jwtSecret`` for every JWT they
                    # issue or verify.  Supplying the same effective secret
                    # used by the HTTP bearer verifier is essential: without
                    # it, a custom sign-in script falls back to its embedded
                    # demo secret, so sign-in succeeds but every protected
                    # endpoint rejects the returned token in production.
                    # Keep this internal runtime input out of request bodies
                    # and only provide it to an auth service.
                    if bool((auth_cfg or {}).get("isAuthService", False)):
                        _, jwt_fallback_secret, _, _ = _jwt_verification_material()
                        if jwt_fallback_secret:
                            params["jwtSecret"] = jwt_fallback_secret
                    params.setdefault("__request", {
                        "method": request.method,
                        "path": request.path,
                    })
                    params["auth"] = getattr(request, "liwiro_auth", {}) if hasattr(request, "liwiro_auth") else {}
                    fallback_params = dict(params)
                    fallback_params["__liwiro_vdb_runtime"] = {
                        "user": getattr(domain_manager.vdb_client, "username", None),
                        "pass": getattr(domain_manager.vdb_client, "password", None),
                        "domain": getattr(domain_manager.vdb_client, "domain", None) or api_name,
                        "db": getattr(domain_manager.vdb_client, "db", None) or service_db,
                    }
                    auth_script_keys = {"ep_signin", "ep_signout", "ep_signup", "ep_forgot_password", "ep_reset_password"}
                    prefer_vi_fallback = (
                        str(os.getenv("LIWIRO_DRY_RUN_VALIDATION") or "").strip() == "1"
                        or bool((auth_cfg or {}).get("isAuthService", False))
                        or (
                        str(api_name or "").strip().lower() == "authcoreservice" and str(endpoint_key or "") in auth_script_keys
                        )
                    )
                    if prefer_vi_fallback:
                        fallback_ok, fallback_result = _execute_vi_script(script_code, fallback_params, service_db)
                        if not fallback_ok:
                            return jsonify({
                                "error": fallback_result.get("error", "Script execution failed"),
                                "details": fallback_result,
                            }), 500
                        return jsonify(fallback_result), _script_http_status(fallback_result)

                    success, result = domain_manager.vdb_client.execute_script(script_name, params)
                    if success and _is_vdb_script_metadata_echo(result):
                        fallback_ok, fallback_result = _execute_vi_script(script_code, fallback_params, service_db)
                        if not fallback_ok:
                            return jsonify({
                                "error": fallback_result.get("error", "Script execution failed"),
                                "details": fallback_result,
                            }), 500
                        result = fallback_result
                    if success:
                        return jsonify(result), _script_http_status(result)
                    return jsonify({"error": result.get("error", "Script execution failed")}), 500

                return _run_script
            elif op_type == "custom":
                return lambda: run_custom_vql(endpoint_cfg)
            raise ValueError(
                f"Unsupported endpoint operation type '{op_type or 'unset'}' for '{endpoint_id}'"
            )

        handler = make_handler(operation_type, crud_operation, collection_name, endpoint_config, endpoint_id)
        handler = _protect_handler(handler, endpoint_config)
        route_path = _join_route(base_path, path)
        api_app.route(route_path, methods=[method], endpoint=f"{api_name}_{endpoint_id}")(handler)

    return api_app


def register_service(api_name, lapis_config, port, process_id):
    vdb_client = current_app.vdb_client

    service_info = {
        "apiName": api_name,
        "processId": str(process_id),
        "status": "RUNNING",
        "lapis_config": lapis_config,
        "port": port,
        "createdAt": datetime.now().isoformat()
    }

    success, existing = vdb_client.update_document(
        "services",
        {"apiName": api_name},
        service_info
    )

    if not success or not existing:
        vdb_client.create_document("services", service_info)
