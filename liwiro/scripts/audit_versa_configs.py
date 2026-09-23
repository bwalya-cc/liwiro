#!/usr/bin/env python3
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
LIWIRO_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = LIWIRO_ROOT.parent
BACKEND_ROOT = LIWIRO_ROOT / "backend"


def _bootstrap_backend_imports() -> None:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))


def _reexec_with_project_python(cause: Exception) -> None:
    candidates = [
        REPO_ROOT / ".venv" / "bin" / "python",
        LIWIRO_ROOT / "backend" / "vvv" / "bin" / "python",
        LIWIRO_ROOT / "backend" / ".venv" / "bin" / "python",
    ]
    current = Path(sys.executable)
    for candidate in candidates:
        if candidate.exists() and candidate != current:
            os.execv(str(candidate), [str(candidate), str(SCRIPT_PATH), *sys.argv[1:]])
    raise RuntimeError("dotenv is unavailable and no project Python interpreter was found.") from cause


_bootstrap_backend_imports()
try:
    from config import Config  # noqa: E402
    from app.versa_validation import validate_versa_source  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover
    if exc.name == "dotenv":
        _reexec_with_project_python(exc)
    raise


def _candidate_paths() -> list[Path]:
    patterns = [
        "data/lapis-examples/*.json",
        "data/vdb-export-*/liwiro/dbs/config/collections/services/data/*.json",
    ]
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(sorted(LIWIRO_ROOT.glob(pattern)))
    return paths


def _standalone_versa_paths() -> list[Path]:
    return [
        LIWIRO_ROOT / "vi_portal_sources" / "scratch" / "ella-fashion-house-cli.versa",
    ]


def _local_tcp_bind_available() -> bool:
    """Whether generated-service dry runs can start their local sandbox server."""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return False
    try:
        probe.bind(("127.0.0.1", 0))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _load_config(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload.get("lapis_config"), dict):
        return payload["lapis_config"]
    return payload


def main() -> int:
    failures: list[str] = []
    checked = 0
    include_dry_run = _local_tcp_bind_available()
    if not include_dry_run:
        print(
            "NOTICE: localhost TCP binding is unavailable; auditing LAPIS syntax/configuration without sandbox execution.",
            file=sys.stderr,
        )
    for path in _candidate_paths():
        try:
            detail = Config.validate_lapis_config_detailed(_load_config(path), include_dry_run=include_dry_run)
        except Exception as exc:  # pragma: no cover
            failures.append(f"{path}: failed to audit ({exc})")
            continue
        checked += 1
        if detail.get("valid"):
            continue
        error = str(detail.get("error") or "invalid LAPIS config").strip()
        failures.append(f"{path}: {error}")

    for path in _standalone_versa_paths():
        if not path.exists():
            failures.append(f"{path}: standalone Versa artifact is missing")
            continue
        checked += 1
        result = validate_versa_source(path.read_text(encoding="utf-8"), path_hint=path.as_posix())
        if result.get("ok"):
            continue
        failures.append(f"{path}: {str(result.get('error') or 'invalid Versa source').strip()}")

    if failures:
        print(f"Versa audit failed for {len(failures)} of {checked} configs.", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1

    print(f"Versa audit passed for {checked} configs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
