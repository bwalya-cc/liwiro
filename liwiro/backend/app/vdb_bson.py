import os
import struct
import time
import uuid
from pathlib import Path


class BsonDecodeError(ValueError):
    pass


def read_bson_value(path: Path):
    data = Path(path).read_bytes()
    if not data:
        return None
    value, consumed = _decode_document(data, 0)
    if consumed > len(data):
        raise BsonDecodeError("BSON length exceeds available data")
    if isinstance(value, dict) and "_value" in value:
        return value["_value"]
    return value


def write_bson_value(path: Path, value) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _encode_document({"_value": value})
    temp_path = target.parent / f"{target.name}.{uuid.uuid4().hex}.tmp"
    with open(temp_path, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    last_error = None
    for attempt in range(6):
        try:
            temp_path.replace(target)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt >= 5:
                break
            time.sleep(0.05 * (attempt + 1))
    try:
        temp_path.unlink(missing_ok=True)
    except Exception:
        pass
    raise last_error or PermissionError(f"Failed to replace {target}")


def _decode_document(data: bytes, offset: int):
    if offset + 4 > len(data):
        raise BsonDecodeError("Incomplete BSON document length")
    length = struct.unpack_from("<i", data, offset)[0]
    end = offset + length
    if length < 5 or end > len(data):
        raise BsonDecodeError("Invalid BSON document length")
    cursor = offset + 4
    out = {}
    while cursor < end - 1:
        element_type = data[cursor]
        cursor += 1
        key_end = data.find(b"\x00", cursor)
        if key_end == -1 or key_end >= end:
            raise BsonDecodeError("Invalid BSON cstring")
        key = data[cursor:key_end].decode("utf-8")
        cursor = key_end + 1
        value, cursor = _decode_element_value(data, cursor, element_type)
        out[key] = value
    if data[end - 1] != 0:
        raise BsonDecodeError("BSON document missing terminator")
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
            raise BsonDecodeError("Invalid BSON string length")
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
    raise BsonDecodeError(f"Unsupported BSON element type: 0x{element_type:02x}")


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
        normalized = {str(child_key): child_value for child_key, child_value in value.items()}
        return b"\x03" + key_bytes + _encode_document(normalized)
    if isinstance(value, list):
        return b"\x04" + key_bytes + _encode_array(value)
    encoded = str(value).encode("utf-8") + b"\x00"
    return b"\x02" + key_bytes + struct.pack("<i", len(encoded)) + encoded
