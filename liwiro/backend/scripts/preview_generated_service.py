#!/usr/bin/env python3
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import argparse
import json
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parents[1]
DATA_ROOT = PROJECT_ROOT / "liwiro" / "data" / "generated-service-preview"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import Config
from generators.api_generator import build_service_preview_bundle


def sanitize_name(value: str) -> str:
    text = str(value or "").strip() or "generated-service"
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text)
    return text.strip("-") or "generated-service"


def unique_output_dir(base_dir: Path) -> Path:
    if not base_dir.exists():
        return base_dir
    for index in range(1, 1000):
        candidate = base_dir.with_name(f"{base_dir.name}-{index}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("Unable to allocate preview output directory")


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize an inspectable Liwiro generated-service preview from a LAPIS file.")
    parser.add_argument("lapis_file", help="Path to the LAPIS JSON file")
    parser.add_argument("target", nargs="?", help="Optional output directory")
    args = parser.parse_args()

    lapis_path = Path(args.lapis_file).expanduser().resolve()
    if not lapis_path.is_file():
        print(f"[preview][error] LAPIS file not found: {lapis_path}", file=sys.stderr)
        return 1

    try:
        lapis_config = json.loads(lapis_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[preview][error] Failed to parse LAPIS JSON: {exc}", file=sys.stderr)
        return 1

    valid, error = Config.validate_lapis_config(lapis_config)
    if not valid:
        print(f"[preview][error] Invalid LAPIS configuration: {error}", file=sys.stderr)
        return 1

    metadata = lapis_config.get("metadata") or {}
    default_name = sanitize_name(str(metadata.get("apiName") or lapis_path.stem or "generated-service"))
    target_dir = Path(args.target).expanduser().resolve() if args.target else unique_output_dir(DATA_ROOT / default_name)
    target_dir.mkdir(parents=True, exist_ok=True)

    preview_bundle = build_service_preview_bundle(lapis_config)
    for relative_path, content in preview_bundle.items():
        file_path = target_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    print(f"[preview][ok] Wrote generated-service preview to {target_dir}")
    for relative_path in preview_bundle.keys():
        print(f" - {target_dir / relative_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
