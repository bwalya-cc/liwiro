from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from typing import Any

from app.vdb_bson import write_bson_value


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _BACKEND_ROOT.parent
_REPO_ROOT = _PROJECT_ROOT.parent
_DEFAULT_LOG_ROOT = _REPO_ROOT / "tmp" / "runtime-logs" / "validation-sandbox"
_VDB_JAR = _REPO_ROOT / "verun" / "vdb" / "target" / "vdb-1.0.0-jar-with-dependencies.jar"
_DEFAULT_STARTUP_TIMEOUT_SECONDS = 20.0
_BCRYPT_HASH_RE = re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}")


class ValidationSandboxError(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


def _bool_env(env_key: str, default: bool = False) -> bool:
    raw = os.getenv(env_key)
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _float_env(env_key: str, default: float) -> float:
    raw = str(os.getenv(env_key) or "").strip()
    if not raw:
        return default
    try:
        parsed = float(raw)
    except Exception:
        return default
    return parsed if parsed > 0 else default


def _resolve_log_root() -> Path:
    configured = str(os.getenv("LIWIRO_VALIDATION_SANDBOX_LOG_ROOT") or "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = (_REPO_ROOT / path).resolve()
        return path
    # The repository's normal runtime tmp directory is the preferred location,
    # but validation is also used from managed/read-only checkouts and CI
    # workers.  Select a writable fallback before creating a sandbox so a
    # contract cannot be rejected merely because diagnostic logs lack a path.
    try:
        _DEFAULT_LOG_ROOT.mkdir(parents=True, exist_ok=True)
        if os.access(_DEFAULT_LOG_ROOT, os.W_OK):
            return _DEFAULT_LOG_ROOT
    except OSError:
        pass
    fallback = Path(tempfile.gettempdir()) / "liwiro" / "validation-sandbox"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _reserve_local_http_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _generate_password_hash(password: str) -> str:
    if not _VDB_JAR.is_file():
        raise ValidationSandboxError(f"VDB runtime jar missing at {_VDB_JAR}")

    helper_source = """\
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import org.mindrot.jbcrypt.BCrypt;

class LiwiroSandboxPasswordHash {
    public static void main(String[] args) throws Exception {
        var reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        var password = reader.readLine();
        System.out.println(BCrypt.hashpw(password == null ? "" : password, BCrypt.gensalt(12)));
    }
}
"""
    try:
        with tempfile.TemporaryDirectory(prefix="liwiro-validation-hash-") as helper_dir:
            helper_path = Path(helper_dir) / "LiwiroSandboxPasswordHash.java"
            helper_path.write_text(helper_source, encoding="utf-8")
            proc = subprocess.run(
                ["java", "--class-path", str(_VDB_JAR), str(helper_path)],
                input=f"{str(password or '')}\n",
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                cwd=str(_REPO_ROOT),
            )
    except FileNotFoundError as exc:
        raise ValidationSandboxError("java is required to seed validation sandbox auth data") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValidationSandboxError("Timed out while generating sandbox auth hash with java") from exc

    combined = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
    if match := _BCRYPT_HASH_RE.search(combined):
        return str(match.group(0))
    raise ValidationSandboxError(
        f"Failed to generate sandbox auth hash via java: {(proc.stderr or proc.stdout or '').strip() or 'unknown error'}"
    )


@dataclass
class ValidationSandbox:
    sandbox_id: str
    sandbox_dir: Path
    runtime_root: Path
    logs_dir: Path
    stdout_log_path: Path
    stderr_log_path: Path
    http_port: int
    base_url: str
    vdb_username: str
    vdb_password: str
    liwiro_domain: str
    liwiro_db: str
    retain_failed_data: bool = False
    startup_timeout_seconds: float = _DEFAULT_STARTUP_TIMEOUT_SECONDS
    created_at: str = field(default_factory=_utcnow_iso)
    process: subprocess.Popen | None = field(default=None, init=False, repr=False)
    summary_path: Path | None = field(default=None, init=False)
    snapshot_path: Path | None = field(default=None, init=False)
    runtime_data_retained: bool = field(default=False, init=False)

    @classmethod
    def create(cls) -> "ValidationSandbox":
        sandbox_id = f"validation-{uuid.uuid4().hex[:12]}"
        sandbox_dir = _resolve_log_root() / sandbox_id
        runtime_root = sandbox_dir / "runtime-root"
        logs_dir = sandbox_dir / "logs"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        runtime_root.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        http_port = _reserve_local_http_port()
        username = str(
            os.getenv("VDB_USERNAME")
            or os.getenv("LIWIRO_APP_USERNAME")
            or "liwiro"
        ).strip().lower() or "liwiro"
        password = str(
            os.getenv("VDB_PASSWORD")
            or os.getenv("LIWIRO_APP_PASSWORD")
            or "LiwiroVDBAppPass0!"
        ).strip() or "LiwiroVDBAppPass0!"
        domain = str(os.getenv("LIWIRO_DOMAIN") or "liwiro").strip().lower() or "liwiro"
        database = str(os.getenv("LIWIRO_DB") or "config").strip().lower() or "config"

        return cls(
            sandbox_id=sandbox_id,
            sandbox_dir=sandbox_dir,
            runtime_root=runtime_root,
            logs_dir=logs_dir,
            stdout_log_path=sandbox_dir / "vdb.stdout.log",
            stderr_log_path=sandbox_dir / "vdb.stderr.log",
            http_port=http_port,
            base_url=f"http://127.0.0.1:{http_port}",
            vdb_username=username,
            vdb_password=password,
            liwiro_domain=domain,
            liwiro_db=database,
            retain_failed_data=_bool_env("LIWIRO_VALIDATION_SANDBOX_KEEP_FAILED_DATA", default=False),
            startup_timeout_seconds=_float_env(
                "LIWIRO_VALIDATION_SANDBOX_STARTUP_TIMEOUT_SECONDS",
                _DEFAULT_STARTUP_TIMEOUT_SECONDS,
            ),
        )

    def env_overrides(self) -> dict[str, str]:
        return {
            "VDB_TRANSPORT": "http",
            "VDB_SERVER_URL": self.base_url,
            "VDB_HTTP_PORT": str(self.http_port),
            "VDB_UNIX_SOCKET_PATH": "",
            "VDB_NAMED_PIPE_PATH": "",
            "VDB_USERNAME": self.vdb_username,
            "VDB_PASSWORD": self.vdb_password,
            "LIWIRO_APP_USERNAME": self.vdb_username,
            "LIWIRO_APP_PASSWORD": self.vdb_password,
            "LIWIRO_DOMAIN": self.liwiro_domain,
            "LIWIRO_DB": self.liwiro_db,
            "VERUN_VDB_ROOT": str(self.runtime_root),
            "LIWIRO_DRY_RUN_VALIDATION": "1",
            "LIWIRO_DRY_RUN_SANDBOX_MODE": "1",
            "LIWIRO_DRY_RUN_SANDBOX_ID": self.sandbox_id,
            "LIWIRO_DRY_RUN_SANDBOX_LOGS_PATH": str(self.sandbox_dir),
            "LIWIRO_DRY_RUN_SANDBOX_FILES_ROOT": str(self.sandbox_dir / "mock-files"),
        }

    def describe(self) -> dict[str, Any]:
        return {
            "sandboxId": self.sandbox_id,
            "transport": "http",
            "serverUrl": self.base_url,
            "logsPath": str(self.sandbox_dir),
            "stdoutLogPath": str(self.stdout_log_path),
            "stderrLogPath": str(self.stderr_log_path),
            "summaryPath": str(self.summary_path) if self.summary_path else "",
            "runtimeDataRetained": bool(self.runtime_data_retained),
            "snapshotPath": str(self.snapshot_path) if self.snapshot_path else "",
        }

    def allows_request(self, url: str) -> bool:
        text = str(url or "").strip()
        return bool(text) and text.startswith(self.base_url.rstrip("/") + "/")

    def _seed_runtime_root(self) -> None:
        users_dir = self.runtime_root / "__data__" / "sys" / "users"
        users_dir.mkdir(parents=True, exist_ok=True)
        write_bson_value(
            self.runtime_root / "__data__" / "sys" / "mit-license-acceptance.bson",
            {
                "accepted": True,
                "license": "MIT",
                "spdx_license_expression": "MIT",
                "accepted_at": _utcnow_iso(),
                "accepted_by": "liwiro-validation-sandbox",
                "channel": "validation-sandbox",
                "source_repo": "https://zulan.io/folio/verun",
            },
        )
        password_hash = _generate_password_hash(self.vdb_password)
        write_bson_value(
            users_dir / "users.bson",
            {"usernames": [self.vdb_username], "updated_at": int(time.time() * 1000)},
        )
        write_bson_value(
            users_dir / f"{self.vdb_username}.bson",
            {
                "username": self.vdb_username,
                "email": f"{self.vdb_username}@validation.local",
                "role": "SUPER_ADMIN",
                "passwordHash": password_hash,
                "permissions": {},
                "collectionPermissions": {},
                "ownedDomains": ["default", self.liwiro_domain],
            },
        )

    def start(self) -> None:
        if self.process is not None:
            return
        if not _VDB_JAR.is_file():
            raise ValidationSandboxError(f"VDB runtime jar missing at {_VDB_JAR}")

        self._seed_runtime_root()
        env = dict(os.environ)
        env.update(
            {
                "VERUN_VDB_ROOT": str(self.runtime_root),
                "VDB_HTTP_PORT": str(self.http_port),
                "VI_CUSTOM_MODULES_DIR": str(_REPO_ROOT / "verun" / "vi" / "custom_modules"),
            }
        )

        stdout_handle = self.stdout_log_path.open("w", encoding="utf-8")
        stderr_handle = self.stderr_log_path.open("w", encoding="utf-8")
        try:
            self.process = subprocess.Popen(
                [
                    "java",
                    f"-Dverun.vdb.root={self.runtime_root}",
                    f"-Dvdb.http.port={self.http_port}",
                    "-cp",
                    str(_VDB_JAR),
                    "verun.vdb.VDBHttpServer",
                ],
                cwd=str(self.sandbox_dir),
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                env=env,
            )
        except Exception:
            stdout_handle.close()
            stderr_handle.close()
            raise
        finally:
            try:
                stdout_handle.close()
            except Exception:
                pass
            try:
                stderr_handle.close()
            except Exception:
                pass

        deadline = time.time() + self.startup_timeout_seconds
        last_error = ""
        import requests

        while time.time() < deadline:
            if self.process is not None and self.process.poll() is not None:
                last_error = self._tail_process_logs()
                raise ValidationSandboxError(
                    f"Validation sandbox VDB exited early: {last_error or f'process exited with code {self.process.returncode}'}"
                )
            try:
                health = requests.get(f"{self.base_url}/health", timeout=1.5)
                if health.ok:
                    auth = requests.post(
                        f"{self.base_url}/auth",
                        timeout=2,
                        auth=(self.vdb_username, self.vdb_password),
                    )
                    if auth.ok:
                        return
                    last_error = auth.text.strip() or f"HTTP {auth.status_code}"
            except requests.RequestException as exc:
                last_error = str(exc)
            time.sleep(0.2)

        raise ValidationSandboxError(
            f"Validation sandbox VDB did not become healthy within {self.startup_timeout_seconds:.1f}s: {last_error or 'unknown error'}"
        )

    def stop(self) -> None:
        process = self.process
        self.process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def _tail_process_logs(self) -> str:
        chunks = []
        for path in (self.stderr_log_path, self.stdout_log_path):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if text.strip():
                chunks.append(text.strip().splitlines()[-1])
        return " | ".join(chunks)

    def finalize(self, *, success: bool, summary: dict[str, Any]) -> None:
        self.stop()
        sanitized_summary = dict(summary or {})
        sanitized_summary.setdefault("sandbox", {})
        sanitized_summary["sandbox"] = {
            **sanitized_summary["sandbox"],
            "sandboxId": self.sandbox_id,
            "serverUrl": self.base_url,
            "transport": "http",
            "logsPath": str(self.sandbox_dir),
            "stdoutLogPath": str(self.stdout_log_path),
            "stderrLogPath": str(self.stderr_log_path),
            "createdAt": self.created_at,
            "finishedAt": _utcnow_iso(),
        }
        self.summary_path = self.sandbox_dir / "validation-summary.json"
        self.summary_path.write_text(json.dumps(sanitized_summary, indent=2, sort_keys=True), encoding="utf-8")

        if success:
            self.runtime_data_retained = False
            shutil.rmtree(self.runtime_root, ignore_errors=True)
            return

        snapshot = {
            "status": "failed",
            "sandbox": sanitized_summary.get("sandbox"),
            "errors": list(sanitized_summary.get("errors") or []),
            "notices": list(sanitized_summary.get("notices") or []),
            "vdbAuth": sanitized_summary.get("vdbAuth"),
            "externalMocks": list(sanitized_summary.get("externalMocks") or []),
            "startupEvents": list(sanitized_summary.get("startupEvents") or []),
            "routeEvents": list(sanitized_summary.get("routeEvents") or []),
            "endpointResults": list(sanitized_summary.get("endpointResults") or []),
        }
        self.snapshot_path = self.sandbox_dir / "failure-snapshot.json"
        self.snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

        if self.retain_failed_data:
            self.runtime_data_retained = True
            return

        self.runtime_data_retained = False
        shutil.rmtree(self.runtime_root, ignore_errors=True)
