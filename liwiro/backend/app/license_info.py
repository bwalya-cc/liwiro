# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: MIT

from __future__ import annotations

from datetime import datetime, timezone
import os
import platform

COPYRIGHT_OWNER = "Bwalya Cameron Chishimba"
SOURCE_REPO = "https://zulan.io/folio/verun"
STARTED_AT = datetime.now(timezone.utc)


def _env(name: str, default: str) -> str:
    value = str(os.getenv(name, "")).strip()
    return value or default


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def source_info() -> dict:
    return {
        "repo": _env("LIWIRO_SOURCE_REPO", SOURCE_REPO),
        "commit": _env("LIWIRO_SOURCE_COMMIT", "unknown"),
        "build_timestamp": _env("LIWIRO_BUILD_AT", "unknown"),
    }


def build_info() -> dict:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "started_at": _iso(STARTED_AT),
    }


def license_disclosure() -> dict:
    return {
        "title": "MIT License",
        "spdx_license_expression": "MIT",
        "license": "MIT",
        "copyright_owner": COPYRIGHT_OWNER,
        "source": source_info(),
        "build": build_info(),
        "permissions": [
            "Use",
            "Copy",
            "Modify",
            "Merge",
            "Publish",
            "Distribute",
            "Sublicense",
            "Sell",
        ],
        "conditions": [
            "Include the copyright notice and MIT license text in substantial portions of the software."
        ],
        "limitations": [
            "Provided AS IS, without warranty of any kind.",
        ],
        "third_party_notice": (
            "The repository is MIT-licensed, but bundled dependencies keep their own licenses."
        ),
        "text": (
            "Verun + Liwiro is distributed under the MIT License. You may use, copy, modify, merge, publish, "
            "distribute, sublicense, and sell copies of the software, subject to preserving the copyright and "
            "license notice."
        ),
        "endpoints": {
            "license": "/license",
            "health": "/health",
        },
    }


def health_payload(runtime: str = "LIWIRO_BACKEND") -> dict:
    return {
        "status": "ok",
        "runtime": runtime,
        "license": "MIT",
        "spdx_license_expression": "MIT",
    }
