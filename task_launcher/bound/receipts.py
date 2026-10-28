"""HMAC-SHA256 receipt chain.

Every accepted supervisor step appends one receipt::

    {
      "schema": "zhigou.bound.receipt/v1",
      "task_id": "task-...",
      "step": "snapshot_read",
      "prev_receipt_sha256": "<hex or null>",
      "payload_sha256": "<hex of canonical payload>",
      "issued_at": "2026-...Z",
      "risk": "none|read_only|write|critical",
      "hmac": "<HMAC-SHA256(key, canonical(receipt without hmac))>"
    }

Rules enforced here (and by ``finalize`` in the supervisor):

* canonical JSON: sorted keys, UTF-8, no insignificant whitespace;
* the HMAC key is generated in the supervisor process memory only
  (``secrets.token_bytes(32)``) and never persisted;
* a payload is stored next to its receipt so the payload hash can be
  re-verified; modifying either half invalidates the chain;
* ``prev_receipt_sha256`` chains receipts in order; reordering/removing a
  receipt breaks the chain;
* each step appears at most once and only in the canonical step order.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from . import RECEIPT_SCHEMA
from .errors import (
    RECEIPT_CHAIN_BROKEN,
    RECEIPT_DUPLICATE_STEP,
    RECEIPT_HMAC_INVALID,
    RECEIPT_PAYLOAD_HASH_MISMATCH,
    RECEIPT_SCHEMA_INVALID,
    RECEIPT_STEP_ORDER,
    BoundError,
)

_VALID_RISKS = ("none", "read_only", "write", "critical")
_REQUIRED_FIELDS = (
    "schema",
    "task_id",
    "step",
    "prev_receipt_sha256",
    "payload_sha256",
    "issued_at",
    "risk",
    "hmac",
)


def canonical_json(value: Any) -> str:
    """Canonical JSON: sorted keys, compact separators, UTF-8, no ASCII escapes."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def payload_sha256(payload: Any) -> str:
    return sha256_hex(canonical_json(payload))


def receipt_sha256(receipt: dict[str, Any]) -> str:
    """Hash of the complete receipt (including its HMAC)."""

    return sha256_hex(canonical_json(receipt))


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class ReceiptSigner:
    """Holds the in-memory key and mints receipts."""

    def __init__(self, task_id: str, key: bytes | None = None) -> None:
        import secrets

        if key is not None and not isinstance(key, (bytes, bytearray)):
            raise TypeError("key must be bytes")
        self._key = bytes(key) if key is not None else secrets.token_bytes(32)
        self.task_id = task_id

    @property
    def key(self) -> bytes:
        return self._key

    def _mac(self, receipt_without_hmac: dict[str, Any]) -> str:
        return hmac.new(
            self._key, canonical_json(receipt_without_hmac).encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def sign(
        self,
        step: str,
        payload: Any,
        *,
        prev_receipt_sha256: str | None,
        risk: str,
        issued_at: str | None = None,
    ) -> dict[str, Any]:
        if risk not in _VALID_RISKS:
            raise BoundError(RECEIPT_SCHEMA_INVALID, f"invalid risk class {risk!r}", {"risk": risk})
        receipt: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA,
            "task_id": self.task_id,
            "step": step,
            "prev_receipt_sha256": prev_receipt_sha256,
            "payload_sha256": payload_sha256(payload),
            "issued_at": issued_at or utc_now(),
            "risk": risk,
        }
        receipt["hmac"] = self._mac(receipt)
        return receipt


def verify_receipt(
    receipt: Any,
    payload: Any,
    signer_or_key: "ReceiptSigner | bytes",
    *,
    expected_prev: str | None,
) -> None:
    """Verify one receipt/payload pair; raises ``BoundError`` on any defect."""

    if not isinstance(receipt, dict):
        raise BoundError(RECEIPT_SCHEMA_INVALID, "receipt must be an object", {"receipt": str(receipt)[:120]})
    for field_name in _REQUIRED_FIELDS:
        if field_name not in receipt:
            raise BoundError(
                RECEIPT_SCHEMA_INVALID,
                f"receipt is missing field {field_name!r}",
                {"field": field_name},
            )
    if receipt["schema"] != RECEIPT_SCHEMA:
        raise BoundError(RECEIPT_SCHEMA_INVALID, "unknown receipt schema", {"schema": receipt["schema"]})
    if receipt["prev_receipt_sha256"] != expected_prev:
        raise BoundError(
            RECEIPT_CHAIN_BROKEN,
            "prev_receipt_sha256 does not match the previous receipt",
            {"expected": expected_prev, "actual": receipt["prev_receipt_sha256"], "step": receipt["step"]},
        )
    actual_payload = payload_sha256(payload)
    if receipt["payload_sha256"] != actual_payload:
        raise BoundError(
            RECEIPT_PAYLOAD_HASH_MISMATCH,
            "payload hash does not match the stored payload",
            {
                "step": receipt["step"],
                "stored": receipt["payload_sha256"],
                "actual": actual_payload,
            },
        )
    key = signer_or_key.key if isinstance(signer_or_key, ReceiptSigner) else signer_or_key
    if isinstance(signer_or_key, ReceiptSigner):
        # bind to the signer's task id; a receipt from another task is not valid
        if receipt["task_id"] != signer_or_key.task_id:
            raise BoundError(
                RECEIPT_CHAIN_BROKEN,
                "receipt belongs to another task",
                {"expected": signer_or_key.task_id, "actual": receipt["task_id"]},
            )
    unsigned = {name: value for name, value in receipt.items() if name != "hmac"}
    expected_mac = hmac.new(key, canonical_json(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(str(receipt["hmac"]), expected_mac):
        raise BoundError(
            RECEIPT_HMAC_INVALID,
            "receipt HMAC is invalid (tampered or signed with another key)",
            {"step": receipt["step"]},
        )


@dataclass
class ChainVerification:
    ok: bool
    steps: list[str] = field(default_factory=list)
    head_sha256: str | None = None
    problems: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "steps": list(self.steps),
            "head_sha256": self.head_sha256,
            "problems": list(self.problems),
        }


def verify_chain(
    entries: Sequence[dict[str, Any]],
    signer_or_key: "ReceiptSigner | bytes",
    *,
    expected_steps: Iterable[str] | None = None,
    require_complete: bool = True,
) -> ChainVerification:
    """Verify an ordered list of ``{"receipt": ..., "payload": ...}`` entries."""

    expected = list(expected_steps) if expected_steps is not None else None
    result = ChainVerification(ok=True)
    previous: str | None = None
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or "receipt" not in entry or "payload" not in entry:
            result.ok = False
            result.problems.append({"index": index, "code": RECEIPT_SCHEMA_INVALID, "message": "entry is not {receipt,payload}"})
            continue
        receipt = entry["receipt"]
        step = receipt.get("step") if isinstance(receipt, dict) else None
        if not isinstance(receipt, dict) or not isinstance(step, str):
            result.ok = False
            result.problems.append({"index": index, "code": RECEIPT_SCHEMA_INVALID, "message": "bad receipt object"})
            continue
        if step in seen:
            result.ok = False
            result.problems.append({"index": index, "step": step, "code": RECEIPT_DUPLICATE_STEP, "message": "duplicate step"})
            continue
        if expected is not None and step not in expected:
            result.ok = False
            result.problems.append({"index": index, "step": step, "code": RECEIPT_STEP_ORDER, "message": "unknown step"})
            continue
        if expected is not None and result.steps:
            expected_index = {item: position for position, item in enumerate(expected)}
            if expected_index[step] < expected_index[result.steps[-1]]:
                result.ok = False
                result.problems.append(
                    {"index": index, "step": step, "code": RECEIPT_STEP_ORDER, "message": "step out of order"}
                )
                continue
        try:
            verify_receipt(receipt, entry["payload"], signer_or_key, expected_prev=previous)
        except BoundError as exc:
            result.ok = False
            result.problems.append({"index": index, "step": step, "code": exc.code, "message": exc.message, "detail": exc.detail})
        seen.add(step)
        result.steps.append(step)
        previous = receipt_sha256(receipt)
        result.head_sha256 = previous
    if require_complete and expected is not None:
        missing = [item for item in expected if item not in seen]
        if missing:
            result.ok = False
            result.problems.append(
                {"code": "RECEIPT_MISSING", "message": "required steps are missing", "missing": missing}
            )
    return result


class ReceiptLog:
    """In-memory + on-disk receipt chain for one task.

    The log is the only evidence structure the supervisor trusts; the agent has
    no Write/Edit tool, so even an external file edit is detected by
    :func:`verify_chain`.
    """

    def __init__(self, signer: ReceiptSigner, path: "object | None" = None) -> None:
        self.signer = signer
        self.entries: list[dict[str, Any]] = []
        self.path = path

    @property
    def head_sha256(self) -> str | None:
        if not self.entries:
            return None
        return receipt_sha256(self.entries[-1]["receipt"])

    def append(self, step: str, payload: Any, *, risk: str, issued_at: str | None = None) -> dict[str, Any]:
        receipt = self.signer.sign(
            step,
            payload,
            prev_receipt_sha256=self.head_sha256,
            risk=risk,
            issued_at=issued_at,
        )
        entry = {"receipt": receipt, "payload": payload}
        self.entries.append(entry)
        if self.path is not None:
            self._append_disk(entry)
        return receipt

    def _append_disk(self, entry: dict[str, Any]) -> None:
        from pathlib import Path

        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(entry) + "\n")

    def verify(self, expected_steps: Iterable[str] | None = None) -> ChainVerification:
        return verify_chain(
            self.entries,
            self.signer,
            expected_steps=expected_steps,
            require_complete=expected_steps is not None,
        )


def load_chain(path: "object") -> list[dict[str, Any]]:
    """Load a receipt log from disk; malformed lines are kept as raw problems."""

    from pathlib import Path

    file_path = Path(path)
    entries: list[dict[str, Any]] = []
    if not file_path.exists():
        return entries
    for line_number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append({"receipt": {"step": None, "invalid_line": line_number}, "payload": None, "_raw": line})
    return entries
