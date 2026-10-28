"""Strict JSON reading, hashing and atomic report writing."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def _reject_constant(token):
    raise ValueError("non-finite JSON number is not allowed: " + str(token))


def _unique_pairs(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate JSON key: " + key)
        seen[key] = value
    return seen


def loads_strict(text, name="input"):
    """Parse UTF-8 JSON, rejecting duplicate keys and NaN/Infinity."""
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError(name + ": not valid UTF-8: " + str(error))
    try:
        return json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except ValueError:
        raise
    except Exception as error:  # json.JSONDecodeError subclasses ValueError
        raise ValueError(name + ": invalid JSON: " + str(error))


def load_file(path):
    """Return (raw_bytes, parsed_data, raw_sha256)."""
    data = Path(path).read_bytes()
    return data, loads_strict(data, str(path)), hashlib.sha256(data).hexdigest()


def canonical(value):
    """Deterministic semantic form: sorted object keys, sorted arrays.

    Array order is not meaningful anywhere in this contract, so sorting every
    array makes the semantic hash independent of component/pin/finding order.
    It is a hash definition only; it never re-orders the report itself.
    """
    if isinstance(value, dict):
        return {str(key): canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return sorted((canonical(item) for item in value),
                      key=lambda item: json.dumps(item, ensure_ascii=False,
                                                  sort_keys=True,
                                                  separators=(",", ":")))
    return value


def semantic_text(value):
    return json.dumps(canonical(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def semantic_sha256(value):
    return hashlib.sha256(semantic_text(value).encode("utf-8")).hexdigest()


def stable_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False) + "\n"


def atomic_write_json(path, value):
    """Write JSON atomically in the target directory; never leave partial text."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = stable_json(value)
    handle, temporary = tempfile.mkstemp(
        dir=str(target.parent), prefix="." + target.name + "-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(target))
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass
