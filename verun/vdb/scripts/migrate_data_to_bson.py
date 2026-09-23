#!/usr/bin/env python3
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from bson_store import write_value, _encode_document, ROOT_VALUE_KEY, read_value


USER_MANIFEST_KEY = "usernames"
ROLE_MANIFEST_KEY = "role_names"
SYSTEM_ROLES = {"SUPER_ADMIN", "ADMIN", "APPLICATION"}

def convert_json_file(path: Path, *, delete_source: bool) -> Path:
    target = path.with_suffix(".bson")
    payload = json.loads(path.read_text(encoding="utf-8"))
    write_value(target, payload)
    if delete_source:
        path.unlink(missing_ok=True)
    return target


def convert_jsonl_file(path: Path, *, delete_source: bool) -> Path:
    target = path.with_suffix(".bsonlog")
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        normalized = line.strip()
        if not normalized:
            continue
        entries.append(json.loads(normalized))
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    for entry in entries:
        payload.extend(_encode_document({ROOT_VALUE_KEY: entry}))
    target.write_bytes(bytes(payload))
    if delete_source:
        path.unlink(missing_ok=True)
    return target


def _normalize_user_store(root: Path) -> int:
    store_path = root / "sys" / "users" / "users.bson"
    raw = read_value(store_path)
    if not isinstance(raw, list):
        return 0

    user_dir = store_path.parent
    user_dir.mkdir(parents=True, exist_ok=True)
    usernames: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        username = str(entry.get("username", "")).strip().lower()
        if not username:
            continue
        entry = dict(entry)
        entry["username"] = username
        write_value(user_dir / f"{username}.bson", entry)
        if username not in usernames:
            usernames.append(username)

    write_value(
        store_path,
        {
            USER_MANIFEST_KEY: usernames,
            "updated_at": int(time.time() * 1000),
        },
    )
    return len(usernames)


def _normalize_role_store(root: Path) -> int:
    store_path = root / "sys" / "roles" / "roles.bson"
    raw = read_value(store_path)
    if not isinstance(raw, dict) or ROLE_MANIFEST_KEY in raw:
        return 0

    role_dir = store_path.parent
    role_dir.mkdir(parents=True, exist_ok=True)
    role_names: list[str] = []
    for role_name, entry in raw.items():
        normalized_name = str(role_name or "").strip().upper()
        if not normalized_name or normalized_name in SYSTEM_ROLES or not isinstance(entry, dict):
            continue
        write_value(role_dir / f"{normalized_name}.bson", dict(entry))
        if normalized_name not in role_names:
            role_names.append(normalized_name)

    write_value(
        store_path,
        {
            ROLE_MANIFEST_KEY: role_names,
            "updated_at": int(time.time() * 1000),
        },
    )
    return len(role_names)


def migrate_tree(root: Path, *, delete_source: bool) -> tuple[int, int, int, int]:
    converted_json = 0
    converted_jsonl = 0
    for path in sorted(root.rglob("*.json")):
        convert_json_file(path, delete_source=delete_source)
        converted_json += 1
    for path in sorted(root.rglob("*.jsonl")):
        convert_jsonl_file(path, delete_source=delete_source)
        converted_jsonl += 1
    normalized_users = _normalize_user_store(root)
    normalized_roles = _normalize_role_store(root)
    return converted_json, converted_jsonl, normalized_users, normalized_roles


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert VDB __data__ JSON artifacts to BSON/BSONLOG.")
    parser.add_argument(
        "root",
        nargs="?",
        default=Path(__file__).resolve().parents[1] / "__data__",
        type=Path,
        help="Root __data__ directory to migrate",
    )
    parser.add_argument(
        "--keep-json",
        action="store_true",
        help="Keep source .json/.jsonl files after writing BSON/BSONLOG outputs",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    converted_json, converted_jsonl, normalized_users, normalized_roles = migrate_tree(root, delete_source=not args.keep_json)
    print(
        "Converted "
        f"{converted_json} JSON file(s), {converted_jsonl} JSONL file(s), "
        f"normalized {normalized_users} user record(s), and {normalized_roles} role record(s) under {root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
