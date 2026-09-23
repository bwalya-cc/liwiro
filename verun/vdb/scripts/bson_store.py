#!/usr/bin/env python3
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from __future__ import annotations

import json
import struct
import sys
import time
from pathlib import Path


ROOT_VALUE_KEY = "_value"
USER_MANIFEST_KEY = "usernames"


class BsonStoreError(ValueError):
    pass


def read_value(path: Path):
    path = Path(path)
    if not path.exists():
        return None
    if path.suffix != ".bson":
        raw = path.read_text(encoding="utf-8").strip()
        return json.loads(raw) if raw else None
    data = path.read_bytes()
    if not data:
        return None
    value, consumed = _decode_document(data, 0)
    if consumed > len(data):
        raise BsonStoreError("BSON length exceeds available data")
    if isinstance(value, dict) and ROOT_VALUE_KEY in value:
        return value[ROOT_VALUE_KEY]
    return value


def write_value(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix != ".bson":
        path.write_text(json.dumps(value), encoding="utf-8")
        return
    payload = _encode_document({ROOT_VALUE_KEY: value})
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_bytes(payload)
    temp_path.replace(path)


def _decode_document(data: bytes, offset: int):
    if offset + 4 > len(data):
        raise BsonStoreError("Incomplete BSON document length")
    length = struct.unpack_from("<i", data, offset)[0]
    end = offset + length
    if length < 5 or end > len(data):
        raise BsonStoreError("Invalid BSON document length")
    cursor = offset + 4
    out = {}
    while cursor < end - 1:
        element_type = data[cursor]
        cursor += 1
        key_end = data.find(b"\x00", cursor)
        if key_end == -1 or key_end >= end:
            raise BsonStoreError("Invalid BSON cstring")
        key = data[cursor:key_end].decode("utf-8")
        cursor = key_end + 1
        value, cursor = _decode_element_value(data, cursor, element_type)
        out[key] = value
    if data[end - 1] != 0:
        raise BsonStoreError("BSON document missing terminator")
    return out, end


def _decode_array(data: bytes, offset: int):
    document, end = _decode_document(data, offset)
    items = []
    index = 0
    while str(index) in document:
        items.append(document[str(index)])
        index += 1
    if not items and document:
        for _, value in sorted(document.items(), key=lambda item: int(item[0])):
            items.append(value)
    return items, end


def _decode_element_value(data: bytes, offset: int, element_type: int):
    if element_type == 0x01:
        return struct.unpack_from("<d", data, offset)[0], offset + 8
    if element_type == 0x02:
        length = struct.unpack_from("<i", data, offset)[0]
        start = offset + 4
        end = start + length
        if length < 1 or end > len(data):
            raise BsonStoreError("Invalid BSON string length")
        return data[start:end - 1].decode("utf-8"), end
    if element_type == 0x03:
        return _decode_document(data, offset)
    if element_type == 0x04:
        return _decode_array(data, offset)
    if element_type == 0x08:
        return data[offset] != 0, offset + 1
    if element_type == 0x0A:
        return None, offset
    if element_type == 0x10:
        return struct.unpack_from("<i", data, offset)[0], offset + 4
    if element_type == 0x12:
        return struct.unpack_from("<q", data, offset)[0], offset + 8
    raise BsonStoreError(f"Unsupported BSON element type: 0x{element_type:02x}")


def _encode_document(document: dict[str, object]) -> bytes:
    elements = bytearray()
    for key, value in document.items():
        elements.extend(_encode_element(str(key), value))
    body = bytes(elements) + b"\x00"
    return struct.pack("<i", len(body) + 4) + body


def _encode_array(items: list[object]) -> bytes:
    document = {str(index): value for index, value in enumerate(items)}
    return _encode_document(document)


def _encode_element(key: str, value) -> bytes:
    key_bytes = key.encode("utf-8") + b"\x00"
    if value is None:
        return b"\x0A" + key_bytes
    if isinstance(value, bool):
        return b"\x08" + key_bytes + (b"\x01" if value else b"\x00")
    if isinstance(value, int) and not isinstance(value, bool):
        if -(2**31) <= value <= (2**31 - 1):
            return b"\x10" + key_bytes + struct.pack("<i", value)
        return b"\x12" + key_bytes + struct.pack("<q", value)
    if isinstance(value, float):
        return b"\x01" + key_bytes + struct.pack("<d", value)
    if isinstance(value, str):
        encoded = value.encode("utf-8") + b"\x00"
        return b"\x02" + key_bytes + struct.pack("<i", len(encoded)) + encoded
    if isinstance(value, dict):
        return b"\x03" + key_bytes + _encode_document({str(k): v for k, v in value.items()})
    if isinstance(value, list):
        return b"\x04" + key_bytes + _encode_array(value)
    encoded = str(value).encode("utf-8") + b"\x00"
    return b"\x02" + key_bytes + struct.pack("<i", len(encoded)) + encoded


def _user_dir(path: Path) -> Path:
    return Path(path).parent


def _user_record_path(path: Path, username: str) -> Path:
    return _user_dir(path) / f"{str(username or '').strip().lower()}.bson"


def _discover_usernames(path: Path) -> list[str]:
    user_dir = _user_dir(path)
    if not user_dir.exists():
        return []
    usernames = []
    for candidate in sorted(user_dir.glob("*.bson")):
        if candidate.name == Path(path).name:
            continue
        usernames.append(candidate.stem.strip().lower())
    return usernames


def _manifest_usernames(path: Path) -> list[str]:
    raw = read_value(path)
    if isinstance(raw, dict):
        usernames = raw.get(USER_MANIFEST_KEY)
        if isinstance(usernames, list):
            return [str(username or "").strip().lower() for username in usernames if str(username or "").strip()]
    if isinstance(raw, list):
        usernames = []
        for user in raw:
            if isinstance(user, dict):
                username = str(user.get("username", "")).strip().lower()
                if username:
                    usernames.append(username)
        return usernames
    return _discover_usernames(path)


def _load_users(path: Path) -> list[dict[str, object]]:
    raw = read_value(path)
    if isinstance(raw, list):
        return [user for user in raw if isinstance(user, dict)]

    users = []
    for username in _manifest_usernames(path):
        user_path = _user_record_path(path, username)
        user = read_value(user_path)
        if isinstance(user, dict):
            users.append(user)
    return users


def _save_users(path: Path, users: list[dict[str, object]]) -> None:
    path = Path(path)
    user_dir = _user_dir(path)
    user_dir.mkdir(parents=True, exist_ok=True)
    normalized_users = []
    usernames = []

    for raw_user in users:
        if not isinstance(raw_user, dict):
            continue
        user = dict(raw_user)
        username = str(user.get("username", "")).strip().lower()
        if not username:
            continue
        user["username"] = username
        normalized_users.append(user)
        usernames.append(username)
        write_value(_user_record_path(path, username), user)

    for candidate in user_dir.glob("*.bson"):
        if candidate.name == path.name:
            continue
        if candidate.stem.strip().lower() not in usernames:
            candidate.unlink(missing_ok=True)

    write_value(
        path,
        {
            USER_MANIFEST_KEY: usernames,
            "updated_at": int(time.time() * 1000),
        },
    )


def has_any_users(path: Path) -> int:
    return 0 if _load_users(path) else 1


def has_user(path: Path, username: str) -> int:
    wanted = str(username or "").strip()
    for user in _load_users(path):
        if isinstance(user, dict) and str(user.get("username", "")).strip() == wanted:
            return 0
    return 1


def upsert_user(path: Path, username: str, email: str, role: str, password_hash: str, domains: list[str]) -> int:
    users = _load_users(path)
    normalized_domains = []
    for domain in domains:
        value = str(domain or "").strip()
        if value and value not in normalized_domains:
            normalized_domains.append(value)
    updated = False
    for user in users:
        if not isinstance(user, dict):
            continue
        if str(user.get("username", "")).strip() != str(username).strip():
            continue
        user["email"] = email
        user["role"] = role
        user["passwordHash"] = password_hash
        permissions = user.get("permissions")
        collection_permissions = user.get("collectionPermissions")
        user["permissions"] = permissions if isinstance(permissions, dict) else {}
        user["collectionPermissions"] = collection_permissions if isinstance(collection_permissions, dict) else {}
        owned = user.get("ownedDomains")
        owned_domains = owned if isinstance(owned, list) else []
        for domain in normalized_domains:
            if domain not in owned_domains:
                owned_domains.append(domain)
        user["ownedDomains"] = owned_domains
        updated = True
        break
    if not updated:
        users.append(
            {
                "username": username,
                "email": email,
                "role": role,
                "passwordHash": password_hash,
                "permissions": {},
                "collectionPermissions": {},
                "ownedDomains": normalized_domains,
            }
        )
    _save_users(path, users)
    return 0


def record_mit_acceptance(path: Path, channel: str, accepted_by: str, accepted_at: str) -> int:
    write_value(
        path,
        {
            "accepted": True,
            "license": "MIT",
            "spdx_license_expression": "MIT",
            "accepted_at": accepted_at,
            "accepted_by": accepted_by,
            "channel": channel,
            "source_repo": "https://zulan.io/folio/verun",
        },
    )
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Usage: bson_store.py <command> <path> [...]", file=sys.stderr)
        return 2
    command = argv[1]
    path = Path(argv[2])
    try:
        if command == "has-any-users":
            return has_any_users(path)
        if command == "has-user":
            if len(argv) < 4:
                print("has-user requires <username>", file=sys.stderr)
                return 2
            return has_user(path, argv[3])
        if command == "upsert-user":
            if len(argv) < 7:
                print("upsert-user requires <username> <email> <role> <password_hash> [domains...]", file=sys.stderr)
                return 2
            return upsert_user(path, argv[3], argv[4], argv[5], argv[6], argv[7:])
        if command == "record-mit-acceptance":
            if len(argv) < 6:
                print("record-mit-acceptance requires <channel> <accepted_by> <accepted_at>", file=sys.stderr)
                return 2
            return record_mit_acceptance(path, argv[3], argv[4], argv[5])
        print(f"Unknown command: {command}", file=sys.stderr)
        return 2
    except (BsonStoreError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
