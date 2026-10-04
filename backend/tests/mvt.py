"""Just enough of a Mapbox vector tile reader to check what tiles publish: each layer's
features as attribute dicts, without geometry (protocol buffers, MVT spec 2.1)."""

import struct
from collections.abc import Iterator

Value = str | float | int | bool


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    out = shift = 0
    while True:
        b = buf[i]
        i += 1
        out |= (b & 0x7F) << shift
        shift += 7
        if b < 0x80:
            return out, i


def _fields(buf: bytes) -> Iterator[tuple[int, int | bytes]]:
    """(field number, varint or raw bytes) for each field of a message."""
    i = 0
    while i < len(buf):
        key, i = _varint(buf, i)
        wire = key & 7
        if wire == 0:
            value, i = _varint(buf, i)
            yield key >> 3, value
            continue
        size = {1: 8, 5: 4}.get(wire)
        if size is None:  # length-delimited
            size, i = _varint(buf, i)
        yield key >> 3, buf[i : i + size]
        i += size


def _packed(buf: bytes) -> list[int]:
    out, i = [], 0
    while i < len(buf):
        value, i = _varint(buf, i)
        out.append(value)
    return out


def _value(buf: bytes) -> Value:
    for number, v in _fields(buf):
        if isinstance(v, bytes):
            if number == 1:
                return v.decode()
            return struct.unpack("<f" if number == 2 else "<d", v)[0]
        if number == 6:  # sint64, zigzag
            return (v >> 1) ^ -(v & 1)
        return bool(v) if number == 7 else v
    raise ValueError("empty value")


def features(tile: bytes) -> dict[str, list[dict[str, Value]]]:
    layers: dict[str, list[dict[str, Value]]] = {}
    for number, layer in _fields(tile):
        if number != 3 or not isinstance(layer, bytes):
            continue
        name, keys, values, tags = "", [], [], []
        for n, v in _fields(layer):
            if not isinstance(v, bytes):
                continue
            if n == 1:
                name = v.decode()
            elif n == 2:
                tags.append(next((_packed(t) for fn, t in _fields(v) if fn == 2), []))
            elif n == 3:
                keys.append(v.decode())
            elif n == 4:
                values.append(_value(v))
        layers[name] = [
            {keys[k]: values[x] for k, x in zip(t[::2], t[1::2], strict=True)} for t in tags
        ]
    return layers
