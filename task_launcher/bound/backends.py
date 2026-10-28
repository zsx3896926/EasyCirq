"""EDA backend abstraction.

Phase 1 uses :class:`FixtureBackend` exclusively: it reads frozen synthetic
fixture data and runs the *real* merged offline audit module when asked to
(``audit_engine = "zhigou_mcp"``), or a deterministic fixture case otherwise.
Either way it never calls EDA, a daemon, a connector or the network, and every
report says ``real_eda: "NOT RUN"`` / ``eda_calls: 0``.

Phase 2 backends (:class:`OfficialCliBackend`, :class:`ADaemonBackend`) exist as
capability stubs only. They are **never** authorized in this delivery: every
operation raises ``EDA_NOT_AUTHORIZED`` / ``NOT_RUN``, so a Phase 2 task cannot
be finalized.

The agent never gets a backend object; only the supervisor owns it.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import (
    AUDIT_ENGINE_FIXTURE,
    AUDIT_ENGINE_ZHIGOU_MCP,
    BACKEND_A_DAEMON,
    BACKEND_FIXTURE,
    BACKEND_OFFICIAL_CLI,
    FIXTURE_DIR,
    REAL_EDA_BACKENDS,
)
from .errors import (
    BACKEND_UNAVAILABLE,
    EDA_NOT_AUTHORIZED,
    NOT_RUN,
    BoundError,
)
from .receipts import canonical_json, sha256_hex

SNAPSHOT_SCHEMA = "zhigou.bound.snapshot/v1"
AUDIT_SCHEMA = "zhigou.bound.audit/v1"

#: Repository layouts / module names for the merged offline MCP layer.  The
#: 2026-10 rebrand moved ``design-hardware/scripts/zhigou_mcp`` to
#: ``easycirq/scripts/easycirq_mcp``; both are accepted (old PRs still use the
#: former, current main uses the latter).
OFFLINE_MCP_CANDIDATES = (
    ("easycirq", "easycirq_mcp"),
    ("design-hardware", "zhigou_mcp"),
)

#: Statuses surfaced by the merged offline-audit modules (verbatim).
AUDIT_STATUSES = ("pass_with_scope", "fail", "review_required", "incomplete", "invalid_input")
#: Statuses that allow ``finalize`` to produce a report.
FINALIZABLE_AUDIT_STATUSES = ("pass_with_scope", "fail", "review_required")


def default_fixture_dir() -> Path:
    return Path(__file__).resolve().parent / FIXTURE_DIR


@dataclass
class Snapshot:
    """Supervisor-owned snapshot view (never supplied by the model)."""

    project: dict[str, Any]
    document: dict[str, Any]
    page: dict[str, Any]
    selection: list[dict[str, Any]]
    missing_fields: list[str]
    files: list[dict[str, Any]]
    snapshot_sha256: str
    source: str = "fixture"
    scope: str = "full"
    generated_at: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "source": self.source,
            "scope": self.scope,
            "project": self.project,
            "document": self.document,
            "page": self.page,
            "selection": self.selection,
            "missing_fields": self.missing_fields,
            "files": self.files,
            "file_count": len(self.files),
            "snapshot_sha256": self.snapshot_sha256,
            "generated_at": self.generated_at,
            "notes": self.notes,
        }


class EdaBackend:
    """Capability surface seen by the supervisor."""

    name = "abstract"
    version = "0"
    available = False
    real_eda = "NOT RUN"

    def capabilities(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "available": self.available,
            "real_eda": self.real_eda,
            "supports_write": False,
        }

    def read_snapshot(self, scope: dict[str, Any]) -> Snapshot:  # pragma: no cover - interface
        raise NotImplementedError

    def run_offline_audit(
        self,
        snapshot: Snapshot,
        *,
        checks: list[str] | None = None,
        detail: str = "summary",
    ) -> dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError

    def apply(self, plan_id: str, plan: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def readback(self, plan_id: str) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


class FixtureBackend(EdaBackend):
    """Read-only backend over frozen synthetic fixtures (no EDA at all)."""

    name = BACKEND_FIXTURE
    real_eda = "NOT RUN"

    def __init__(
        self,
        fixture_dir: Path | None = None,
        *,
        audit_engine: str = AUDIT_ENGINE_FIXTURE,
        audit_case: str = "pass",
        repo_root: Path | None = None,
    ) -> None:
        self.fixture_dir = Path(fixture_dir) if fixture_dir else default_fixture_dir()
        self.audit_engine = audit_engine
        self.audit_case = audit_case
        self.repo_root = Path(repo_root) if repo_root else None
        self.version = self._read_version()
        self.available = True

    # -- fixture loading ---------------------------------------------------
    def _read_version(self) -> str:
        path = self.fixture_dir / "snapshot.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BoundError(
                BACKEND_UNAVAILABLE,
                f"fixture metadata is unavailable: {path}",
                {"path": str(path), "reason": str(exc)},
            ) from exc
        return str(document.get("fixture_version", "fixture-1"))

    def _load_case(self, case: str) -> dict[str, Any]:
        path = self.fixture_dir / "audit_cases.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BoundError(BACKEND_UNAVAILABLE, "audit fixture unavailable", {"path": str(path)}) from exc
        cases = document.get("cases") or {}
        if case not in cases:
            raise BoundError(BACKEND_UNAVAILABLE, f"unknown fixture audit case {case!r}", {"case": case, "known": sorted(cases)})
        return cases[case]

    # -- capability --------------------------------------------------------
    def capabilities(self) -> dict[str, Any]:
        capabilities = super().capabilities()
        capabilities.update(
            {
                "audit_engine": self.audit_engine,
                "audit_case": self.audit_case,
                "eda_calls": 0,
                "project_writes": 0,
                "phase2_write": False,
            }
        )
        return capabilities

    # -- snapshot ----------------------------------------------------------
    def read_snapshot(self, scope: dict[str, Any]) -> Snapshot:
        metadata_path = self.fixture_dir / "snapshot.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BoundError(
                BACKEND_UNAVAILABLE,
                f"cannot read fixture snapshot metadata: {metadata_path}",
                {"path": str(metadata_path)},
            ) from exc
        files_root = self.fixture_dir / str(metadata.get("files_root", "files"))
        files: list[dict[str, Any]] = []
        if files_root.is_dir():
            for path in sorted(files_root.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(self.fixture_dir).as_posix()
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                files.append({"path": relative, "sha256": digest, "size": path.stat().st_size})
        scope_kind = str(scope.get("kind", "full"))
        if scope_kind not in ("full", "selection"):
            raise BoundError(
                "INVALID_ARGUMENTS",
                f"unsupported snapshot scope kind {scope_kind!r}",
                {"kind": scope_kind},
            )
        binding = {
            "schema": "zhigou.bound.snapshot-binding/v1",
            "project": metadata.get("project"),
            "document": metadata.get("document"),
            "page": metadata.get("page"),
            "selection": metadata.get("selection") or [],
            "files": [[row["path"], row["sha256"]] for row in files],
        }
        snapshot_sha256 = sha256_hex(canonical_json(binding))
        return Snapshot(
            project=dict(metadata.get("project") or {}),
            document=dict(metadata.get("document") or {}),
            page=dict(metadata.get("page") or {}),
            selection=list(metadata.get("selection") or []),
            missing_fields=list(metadata.get("missing_fields") or []),
            files=files,
            snapshot_sha256=snapshot_sha256,
            source="fixture",
            scope=scope_kind,
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            notes=list(metadata.get("notes") or []),
        )

    # -- offline audit -----------------------------------------------------
    def run_offline_audit(
        self,
        snapshot: Snapshot,
        *,
        checks: list[str] | None = None,
        detail: str = "summary",
    ) -> dict[str, Any]:
        if detail not in ("summary", "full"):
            raise BoundError("INVALID_ARGUMENTS", "detail must be 'summary' or 'full'", {"detail": detail})
        if self.audit_engine == AUDIT_ENGINE_ZHIGOU_MCP:
            return self._run_zhigou_mcp_audit(snapshot, detail=detail)
        case = self._load_case(self.audit_case)
        selected = case.get("checks") or []
        if checks:
            wanted = set(checks)
            selected = [row for row in selected if row.get("id") in wanted]
            if not selected:
                raise BoundError(
                    "INVALID_ARGUMENTS",
                    "none of the requested checks exist in the fixture case",
                    {"requested": checks},
                )
        audit = {
            "schema": AUDIT_SCHEMA,
            "engine": AUDIT_ENGINE_FIXTURE,
            "case": self.audit_case,
            "status": case["status"],
            "verdict_class": case["status"],
            "checks": selected if detail == "full" else selected[:2],
            "checks_total": len(selected),
            "checks_omitted": max(0, len(selected) - (len(selected) if detail == "full" else 2)),
            "not_checked": list(case.get("not_checked") or []),
            "real_eda": "NOT RUN",
            "eda_calls": 0,
            "project_writes": 0,
            "snapshot_sha256": snapshot.snapshot_sha256,
            "detail": detail,
        }
        audit["audit_sha256"] = sha256_hex(canonical_json(_audit_binding(audit)))
        return audit

    # -- real merged offline module (optional, still no EDA) ---------------
    def _run_zhigou_mcp_audit(self, snapshot: Snapshot, *, detail: str) -> dict[str, Any]:
        # The merged module renamed its input schema in the 2026-10 rebrand
        # (zhigou.electrical-review.input/v1 -> easycirq...); keep one frozen
        # input set per layout so both checkouts audit real fixtures.
        located_before = locate_offline_mcp(self.repo_root)
        input_subdir = "inputs_easycirq" if (located_before and located_before[1] == "easycirq_mcp") else "inputs"
        input_path = self.fixture_dir / input_subdir / f"{self.audit_case}.json"
        if not input_path.is_file():
            raise BoundError(
                BACKEND_UNAVAILABLE,
                f"offline audit input fixture missing: {input_path}",
                {"path": str(input_path)},
            )
        located = locate_offline_mcp(self.repo_root)
        if located is None:
            raise BoundError(
                NOT_RUN,
                "offline audit MCP module is not available in this checkout "
                "(looked for easycirq_mcp / zhigou_mcp)",
                {"repo_root": str(self.repo_root) if self.repo_root else None},
            )
        scripts_dir, module_name = located
        inserted = str(scripts_dir)
        added = inserted not in sys.path
        if added:
            sys.path.insert(0, inserted)
        try:
            import importlib

            call_tool = importlib.import_module(f"{module_name}.tools").call_tool

            started = time.time()
            result = call_tool(
                "offline_electrical_review",
                {"input_path": str(input_path), "detail": "summary"},
            )
            duration_ms = int((time.time() - started) * 1000)
        except BoundError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise BoundError(
                BACKEND_UNAVAILABLE,
                "offline audit module failed",
                {"reason": str(exc)},
            ) from exc
        finally:
            if added:
                try:
                    sys.path.remove(inserted)
                except ValueError:  # pragma: no cover
                    pass
        if result.get("isError"):
            raise BoundError(
                BACKEND_UNAVAILABLE,
                "offline audit module returned an error result",
                {"structured": result.get("structuredContent")},
            )
        structured = result.get("structuredContent") or {}
        status = structured.get("status")
        if status not in AUDIT_STATUSES:
            raise BoundError(
                BACKEND_UNAVAILABLE,
                f"offline audit returned an unknown status {status!r}",
                {"status": status},
            )
        audit = {
            "schema": AUDIT_SCHEMA,
            "engine": AUDIT_ENGINE_ZHIGOU_MCP,
            "module": structured.get("module"),
            "offline_mcp_module": module_name,
            "tool": structured.get("tool"),
            "status": status,
            "verdict_class": structured.get("verdict_class"),
            "checks": list(structured.get("unknown_items") or []),
            "not_checked": list(structured.get("not_checked") or []),
            "real_eda": structured.get("real_eda", "NOT RUN"),
            "eda_calls": int(structured.get("eda_calls") or 0),
            "project_writes": 0,
            "report_sha256": structured.get("report_sha256"),
            "report_schema": structured.get("report_schema"),
            "duration_ms": duration_ms,
            "snapshot_sha256": snapshot.snapshot_sha256,
            "detail": detail,
            "offline": True,
        }
        if audit["real_eda"] != "NOT RUN" or audit["eda_calls"] != 0:
            # The merged module promises this; if it ever changes, refuse to
            # silently claim an EDA run the user did not authorize.
            raise BoundError(
                EDA_NOT_AUTHORIZED,
                "offline audit unexpectedly reported a real EDA call; refusing",
                {"real_eda": audit["real_eda"], "eda_calls": audit["eda_calls"]},
            )
        audit["audit_sha256"] = sha256_hex(canonical_json(_audit_binding(audit)))
        return audit

    # -- writes (Phase 2) --------------------------------------------------
    def apply(self, plan_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        raise BoundError(
            EDA_NOT_AUTHORIZED,
            "Phase 2 writes are blocked: no EDA authorization and no temporary project copy",
            {"plan_id": plan_id},
            status=403,
        )

    def readback(self, plan_id: str) -> dict[str, Any]:
        raise BoundError(
            EDA_NOT_AUTHORIZED,
            "Phase 2 read-back is blocked: no EDA authorization",
            {"plan_id": plan_id},
            status=403,
        )


class _RealEdaBackendStub(EdaBackend):
    """Capability stub for a real EDA backend that is NOT authorized."""

    available = False
    real_eda = "NOT RUN"

    def __init__(self, name: str) -> None:
        self.name = name

    def capabilities(self) -> dict[str, Any]:
        capabilities = super().capabilities()
        capabilities.update({"reason": "EDA authorization absent", "phase2_write": False})
        return capabilities

    def _refuse(self, operation: str) -> None:
        raise BoundError(
            EDA_NOT_AUTHORIZED,
            f"{operation} is blocked: real EDA backend requires explicit user authorization "
            "and a one-time temporary project copy",
            {"backend": self.name, "operation": operation},
            status=403,
        )

    def read_snapshot(self, scope: dict[str, Any]) -> Snapshot:
        self._refuse("read_snapshot")

    def run_offline_audit(self, snapshot: Snapshot, **_: Any) -> dict[str, Any]:
        self._refuse("run_offline_audit")

    def apply(self, plan_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        self._refuse("apply")

    def readback(self, plan_id: str) -> dict[str, Any]:
        self._refuse("readback")


class OfficialCliBackend(_RealEdaBackendStub):
    def __init__(self) -> None:
        super().__init__(BACKEND_OFFICIAL_CLI)


class ADaemonBackend(_RealEdaBackendStub):
    def __init__(self) -> None:
        super().__init__(BACKEND_A_DAEMON)


def locate_offline_mcp(repo_root: Path | None) -> tuple[Path, str] | None:
    """Find the merged offline MCP scripts dir/module for either repo layout."""

    if repo_root is None:
        return None
    root = Path(repo_root)
    for directory, module_name in OFFLINE_MCP_CANDIDATES:
        scripts_dir = root / directory / "scripts"
        if (scripts_dir / module_name).is_dir():
            return scripts_dir, module_name
    return None


def make_backend(config: Any) -> EdaBackend:
    """Instantiate the backend declared by a bound config."""

    if config.backend == BACKEND_FIXTURE:
        return FixtureBackend(
            config.fixture_dir or default_fixture_dir(),
            audit_engine=config.audit_engine,
            audit_case=config.audit_case,
            repo_root=config.repo_root,
        )
    if config.backend == BACKEND_OFFICIAL_CLI:
        return OfficialCliBackend()
    if config.backend == BACKEND_A_DAEMON:
        return ADaemonBackend()
    raise BoundError(BACKEND_UNAVAILABLE, f"unknown backend {config.backend!r}", {"backend": config.backend})


def _audit_binding(audit: dict[str, Any]) -> dict[str, Any]:
    """Stable projection of an audit for hashing (no timestamps)."""

    return {
        "status": audit.get("status"),
        "engine": audit.get("engine"),
        "checks": audit.get("checks"),
        "not_checked": audit.get("not_checked"),
        "real_eda": audit.get("real_eda"),
        "eda_calls": audit.get("eda_calls"),
        "snapshot_sha256": audit.get("snapshot_sha256"),
        "report_sha256": audit.get("report_sha256"),
    }


def is_real_eda_backend(name: str) -> bool:
    return name in REAL_EDA_BACKENDS
