"""Build a Claude Code plugin from the repository Skill directory.

The 2026-10 rename moved the Skill from ``easycirq/`` to ``easycirq/``;
the builder copies whatever Skill directory it is pointed at and packages it
under ``skills/<frontmatter name>/``, so both layouts work.

The plugin is what makes "the Skill travels with the task" true: a headless
agent started with ``--plugin-dir <task>/plugin`` loads this Skill without the
customer having installed it globally.  The build is a **read-only copy** of the
Skill tree plus three generated files:

* ``.claude-plugin/plugin.json`` — identity + explicit Skill/plugin version map;
* ``.mcp.json`` — the offline-audit MCP server (already on ``main``);
* ``hooks/hooks.json`` — intentionally empty for the PoC (no blocking hooks).

Determinism matters: the same Skill input must produce byte-identical plugin
files and an identical manifest, independent of file mtimes and directory
iteration order.  All text files are written with LF so the manifest hashes are
stable on Windows and on CI.

The builder never writes into the Skill directory and never runs anything from
it: it only copies files.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterable

from . import (
    PLUGIN_LICENSE,
    PLUGIN_MANIFEST_SCHEMA,
    PLUGIN_NAME,
    PLUGIN_VERSION,
    SKILL_DIR_CANDIDATES,
    __version__,
)
from . import mcpconfig
from .protocol import VERSION_RE, LauncherError

#: Entries copied from the Skill directory, in a fixed order.
SKILL_COPY_ENTRIES = ("SKILL.md", ".version", "LICENSE", "NOTICE", "references", "scripts", "assets")

#: Never copied: VCS/caches/logs and anything that is not part of the Skill.
JUNK_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "node_modules",
    ".agents",
}
JUNK_FILE_NAMES = {".DS_Store", "Thumbs.db"}
JUNK_SUFFIXES = (".pyc", ".pyo", ".log", ".tmp", ".swp")

PLUGIN_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

#: The plugin template shipped inside the launcher package.
TEMPLATE_DIR = Path(__file__).resolve().parent / "plugin_template"


class PluginError(Exception):
    """Internal build error carrying a stable reason token."""

    def __init__(self, reason: str, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.detail = detail or {}


# ---------------------------------------------------------------------------
# frontmatter (minimal but real: `key: value` + indented continuation lines)
# ---------------------------------------------------------------------------


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse the YAML frontmatter of SKILL.md.

    Only the shape used by this repository is supported (top-level scalar keys
    with optional indented continuation lines); anything else is ignored.  This
    is enough to verify that ``name`` and ``description`` are present and that
    the block is closed, without adding a YAML dependency.
    """

    if not text.startswith("---"):
        raise PluginError("frontmatter_missing", "SKILL.md does not start with a '---' frontmatter block")
    lines = text.splitlines()
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise PluginError("frontmatter_unterminated", "SKILL.md frontmatter block is not closed") from None
    data: dict[str, str] = {}
    current: str | None = None
    for raw in lines[1:end]:
        if not raw.strip():
            continue
        if raw[:1] in (" ", "\t") and current:
            data[current] = (data[current] + " " + raw.strip()).strip()
            continue
        if ":" not in raw:
            raise PluginError("frontmatter_invalid", f"invalid frontmatter line: {raw!r}")
        key, _, value = raw.partition(":")
        key = key.strip()
        if not key or key in data:
            raise PluginError("frontmatter_invalid", f"duplicate or empty frontmatter key: {key!r}")
        current = key
        data[key] = value.strip().strip('"').strip("'")
    return data


def _read_skill_version(skill_dir: Path) -> str:
    version_file = skill_dir / ".version"
    try:
        text = version_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise PluginError(
            "skill_version_unreadable",
            f"cannot read Skill version file: {version_file}",
            {"path": str(version_file), "reason": str(exc)},
        ) from None
    if not VERSION_RE.match(text):
        raise PluginError(
            "skill_version_invalid",
            f"Skill .version is not a dotted version: {text!r}",
            {"path": str(version_file), "value": text},
        )
    return text


def _read_skill_identity(skill_dir: Path) -> dict:
    skill_md = skill_dir / "SKILL.md"
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PluginError(
            "skill_missing",
            f"SKILL.md cannot be read: {skill_md}",
            {"path": str(skill_md), "reason": str(exc)},
        ) from None
    front = parse_frontmatter(text)
    name = front.get("name", "")
    description = front.get("description", "")
    if not name or not SKILL_NAME_RE.match(name):
        raise PluginError("skill_frontmatter_invalid", "SKILL.md frontmatter 'name' is missing or invalid", {"name": name})
    if not description.strip():
        raise PluginError("skill_frontmatter_invalid", "SKILL.md frontmatter 'description' is empty")
    return {"name": name, "description": description, "version": _read_skill_version(skill_dir)}


def default_skill_dir(base: Path) -> Path:
    """Locate the Skill directory below ``base`` (``easycirq`` then legacy name)."""

    base = Path(base)
    for name in SKILL_DIR_CANDIDATES:
        candidate = base / name
        if (candidate / "SKILL.md").is_file():
            return candidate
    return base / SKILL_DIR_CANDIDATES[0]


def read_skill_identity(skill_dir: Path) -> dict:
    """Public wrapper: read frontmatter name/description and ``.version``."""

    return _read_skill_identity(Path(skill_dir))


# ---------------------------------------------------------------------------
# copying
# ---------------------------------------------------------------------------


def _is_junk_file(name: str) -> bool:
    return name in JUNK_FILE_NAMES or name.endswith(JUNK_SUFFIXES)


def _iter_skill_files(skill_dir: Path) -> Iterable[tuple[Path, str]]:
    """Yield ``(source, destination_relative_path)`` pairs in deterministic order."""

    entries: list[tuple[Path, str]] = []
    for entry in SKILL_COPY_ENTRIES:
        source = skill_dir / entry
        if not source.exists():
            if entry in ("SKILL.md", ".version"):
                raise PluginError("skill_missing", f"required Skill entry is missing: {source}", {"path": str(source)})
            continue
        if source.is_file():
            entries.append((source, entry))
            continue
        for root, dirs, files in os.walk(source, followlinks=False):
            dirs[:] = sorted(
                name for name in dirs if name not in JUNK_DIR_NAMES and not name.startswith(".cache")
            )
            for name in sorted(files):
                if _is_junk_file(name):
                    continue
                path = Path(root) / name
                if path.is_symlink():
                    continue
                entries.append((path, path.relative_to(skill_dir).as_posix()))
    entries.sort(key=lambda item: item[1])
    return entries


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _dump_json(path: Path, document: Any) -> None:
    _write_text(path, json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_template(relative: str) -> dict:
    path = TEMPLATE_DIR / relative
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - packaging guard
        raise PluginError(
            "template_missing",
            f"launcher plugin template is unreadable: {path}",
            {"path": str(path), "reason": str(exc)},
        ) from exc


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def validate_plugin_dir(plugin_dir: Path) -> list[str]:
    """Structural validation of a built plugin directory (returns problems)."""

    problems: list[str] = []
    plugin_dir = plugin_dir.resolve()
    manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"plugin.json is missing or unparsable: {exc}"]
    if not isinstance(document, dict):
        problems.append("plugin.json must be a JSON object")
    else:
        name = document.get("name")
        if not isinstance(name, str) or not PLUGIN_NAME_RE.match(name):
            problems.append("plugin.json name is missing or invalid")
        for key in ("version", "skill_version", "launcher_version"):
            value = document.get(key)
            if not isinstance(value, str) or not VERSION_RE.match(value):
                problems.append(f"plugin.json {key} is missing or not a dotted version")
        if not isinstance(document.get("description"), str) or not document["description"].strip():
            problems.append("plugin.json description is missing")
        if document.get("license") != PLUGIN_LICENSE:
            problems.append("plugin.json license must be Apache-2.0")

    skills_root = plugin_dir / "skills"
    skill_dirs = sorted(path for path in skills_root.iterdir() if path.is_dir()) if skills_root.is_dir() else []
    if len(skill_dirs) != 1:
        problems.append(f"skills/ must contain exactly one Skill directory, found {len(skill_dirs)}")
    else:
        skill_root = skill_dirs[0]
        skill_md = skill_root / "SKILL.md"
        if not skill_md.is_file():
            problems.append(f"skills/{skill_root.name}/SKILL.md is missing")
        else:
            try:
                front = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
                if front.get("name") != skill_root.name:
                    problems.append(
                        f"packaged SKILL.md frontmatter name {front.get('name')!r} != directory {skill_root.name!r}"
                    )
                if not front.get("description", "").strip():
                    problems.append("packaged SKILL.md frontmatter description is empty")
            except (PluginError, UnicodeDecodeError, OSError) as exc:
                problems.append(f"packaged SKILL.md frontmatter is invalid: {exc}")

    mcp_path = plugin_dir / ".mcp.json"
    try:
        mcp_document = json.loads(mcp_path.read_text(encoding="utf-8"))
        problems.extend(mcpconfig.validate_mcp_config(mcp_document))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        problems.append(f".mcp.json is missing or unparsable: {exc}")

    hooks_path = plugin_dir / "hooks" / "hooks.json"
    try:
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        if not isinstance(hooks, dict) or not isinstance(hooks.get("hooks"), dict):
            problems.append("hooks/hooks.json must be an object with a 'hooks' object")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        problems.append(f"hooks/hooks.json is missing or unparsable: {exc}")

    for root, dirs, files in os.walk(plugin_dir):
        for name in list(dirs) + list(files):
            path = Path(root) / name
            if path.is_symlink():
                try:
                    path.resolve().relative_to(plugin_dir)
                except ValueError:
                    problems.append(f"symlink escapes the plugin directory: {path}")
    return problems


def load_plugin_metadata(plugin_dir: Path) -> dict:
    """Read the identity of an existing plugin dir; raises :class:`PluginError`."""

    plugin_dir = Path(plugin_dir)
    manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
    if not manifest_path.is_file():
        raise PluginError(
            "plugin_missing",
            f"plugin manifest is missing: {manifest_path}",
            {"path": str(manifest_path)},
        )
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginError(
            "plugin_manifest_invalid",
            f"plugin manifest cannot be parsed: {manifest_path}",
            {"path": str(manifest_path), "reason": str(exc)},
        ) from None
    if not isinstance(document, dict):
        raise PluginError("plugin_manifest_invalid", "plugin.json must be a JSON object", {"path": str(manifest_path)})
    problems: list[str] = []
    if document.get("name") != PLUGIN_NAME:
        problems.append(f"name must be {PLUGIN_NAME!r}")
    for key in ("version", "skill_version"):
        value = document.get(key)
        if not isinstance(value, str) or not VERSION_RE.match(value):
            problems.append(f"{key} must be a dotted version")
    if problems:
        raise PluginError(
            "plugin_manifest_invalid",
            "plugin manifest is structurally invalid",
            {"path": str(manifest_path), "problems": problems},
        )
    return document


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def _resolve_out(out_dir: Path, skill_dir: Path, force: bool) -> Path:
    out_dir = out_dir.resolve()
    skill_dir = skill_dir.resolve()
    if out_dir == skill_dir:
        raise PluginError("output_invalid", "--out must not be the Skill directory", {"out": str(out_dir)})
    if out_dir in skill_dir.parents or skill_dir in out_dir.parents:
        raise PluginError(
            "output_invalid",
            "--out must not contain or live inside the Skill directory",
            {"out": str(out_dir), "skill_dir": str(skill_dir)},
        )
    if out_dir == Path(out_dir.anchor):
        raise PluginError("output_invalid", "--out must not be a filesystem root", {"out": str(out_dir)})
    if out_dir.exists():
        if not out_dir.is_dir():
            raise PluginError("output_not_directory", "--out exists and is not a directory", {"out": str(out_dir)})
        if any(out_dir.iterdir()):
            if not force:
                raise PluginError(
                    "output_not_empty",
                    "--out is not empty; pass --force to replace it",
                    {"out": str(out_dir)},
                )
            shutil.rmtree(out_dir)
        else:
            out_dir.rmdir()
    return out_dir


def _manifest_for(root: Path) -> dict:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative == "plugin.manifest.json":
            continue
        files.append({"path": relative, "sha256": _sha256_file(path), "size": path.stat().st_size})
    files.sort(key=lambda item: item["path"])
    return {
        "schema": PLUGIN_MANIFEST_SCHEMA,
        "name": PLUGIN_NAME,
        "version": PLUGIN_VERSION,
        "skill_version": "",
        "launcher_version": __version__,
        "file_count": len(files),
        "total_bytes": sum(item["size"] for item in files),
        "files": files,
    }


def build_plugin(skill_dir: Path, out_dir: Path, *, force: bool = False) -> dict:
    """Build the Claude Code plugin and return the manifest.

    Raises :class:`PluginError` on any failure.  No partial output is left at
    ``out_dir``: the tree is assembled in a sibling temporary directory and
    moved into place only after structural validation passes.
    """

    skill_dir = Path(skill_dir)
    out_dir = Path(out_dir)
    if not skill_dir.is_dir():
        raise PluginError("skill_missing", f"Skill directory does not exist: {skill_dir}", {"path": str(skill_dir)})
    identity = _read_skill_identity(skill_dir)
    out = _resolve_out(out_dir, skill_dir, force)

    out.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{out.name}.tmp-", dir=str(out.parent)))
    try:
        plugin_json = _load_template(".claude-plugin/plugin.json")
        plugin_json.update(
            {
                "name": PLUGIN_NAME,
                "version": PLUGIN_VERSION,
                "skill_name": identity["name"],
                "skill_version": identity["version"],
                "launcher_version": __version__,
                "description": f"Controlled {identity['name']} Skill loader for the EasyCirq task launcher: "
                "read-only EDA review tasks with the offline audit MCP tools.",
                "license": PLUGIN_LICENSE,
            }
        )
        _dump_json(temp / ".claude-plugin" / "plugin.json", plugin_json)

        dest_root = temp / "skills" / identity["name"]
        dest_root.mkdir(parents=True, exist_ok=True)
        for source, relative in _iter_skill_files(skill_dir):
            target = dest_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

        mcpconfig.write_mcp_config(temp / ".mcp.json", skill_dir / "scripts")
        _dump_json(temp / "hooks" / "hooks.json", _load_template("hooks/hooks.json"))

        problems = validate_plugin_dir(temp)
        if problems:
            raise PluginError(
                "plugin_invalid",
                "built plugin failed structural validation",
                {"problems": problems},
            )

        manifest = _manifest_for(temp)
        manifest["skill_version"] = identity["version"]
        # Recompute over the same files (manifest itself is excluded).
        _dump_json(temp / "plugin.manifest.json", manifest)

        if out.exists():  # empty dir / stale leftovers already handled by _resolve_out
            shutil.rmtree(out)
        shutil.move(str(temp), str(out))
        return manifest
    except PluginError:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(temp, ignore_errors=True)
        raise PluginError(
            "plugin_write_failed",
            f"plugin build failed while writing files: {exc}",
            {"out": str(out), "reason": str(exc)},
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive cleanup
        shutil.rmtree(temp, ignore_errors=True)
        raise PluginError(
            "plugin_build_failed",
            f"plugin build failed: {exc}",
            {"out": str(out), "reason": type(exc).__name__},
        ) from exc


def build_plugin_or_error(skill_dir: Path, out_dir: Path, *, force: bool = False) -> dict:
    """Like :func:`build_plugin` but converts errors to :class:`LauncherError`."""

    try:
        return build_plugin(skill_dir, out_dir, force=force)
    except PluginError as exc:
        # Keep the stable machine token in detail.reason; an OS error cause from
        # the builder moves to detail.cause so it cannot overwrite the token.
        detail = dict(exc.detail)
        if "reason" in detail:
            detail["cause"] = detail.pop("reason")
        raise LauncherError(
            "PLUGIN_BUILD_FAILED",
            exc.message,
            {"reason": exc.reason, **detail},
        ) from None


def read_manifest(plugin_dir: Path) -> dict:
    """Read and verify ``plugin.manifest.json`` against the files on disk."""

    plugin_dir = Path(plugin_dir)
    manifest_path = plugin_dir / "plugin.manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginError(
            "manifest_unreadable",
            f"plugin manifest cannot be read: {manifest_path}",
            {"path": str(manifest_path), "reason": str(exc)},
        ) from None
    problems = []
    for item in manifest.get("files", []):
        path = plugin_dir / item["path"]
        if not path.is_file():
            problems.append(f"listed file is missing: {item['path']}")
            continue
        if _sha256_file(path) != item["sha256"]:
            problems.append(f"sha256 mismatch: {item['path']}")
    if problems:
        raise PluginError(
            "manifest_stale",
            "plugin manifest does not match the files on disk",
            {"problems": problems},
        )
    return manifest


def _unique_temp_name() -> str:  # pragma: no cover - only used for naming
    return f"task-launcher-plugin-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# per-launcher plugin cache
# ---------------------------------------------------------------------------


def skill_fingerprint(skill_dir: Path) -> str:
    """Cheap content fingerprint of the Skill copy entries.

    The cache key must change whenever the Skill payload changes, otherwise a
    task could be started with a stale plugin.  Hashing every byte of the ~13 MB
    tree once per launcher process is also acceptable, but size+mtime_ns of each
    file is enough to detect an edited Skill while staying O(files) and cheap.
    """

    skill_dir = Path(skill_dir).resolve()
    digest = hashlib.sha256()
    digest.update(PLUGIN_VERSION.encode())
    digest.update(__version__.encode())
    for source, relative in _iter_skill_files(skill_dir):
        stat = source.stat()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(str(stat.st_size).encode())
        digest.update(b"\0")
        digest.update(str(stat.st_mtime_ns).encode())
        digest.update(b"\0")
    # SKILL.md and .version bytes are the identity-bearing files: hash them
    # fully so a same-size same-mtime edit is still noticed.
    for name in ("SKILL.md", ".version"):
        path = skill_dir / name
        if path.is_file():
            digest.update(name.encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def ensure_cached_plugin(
    skill_dir: Path,
    cache_root: Path,
    *,
    plugin_version: str = PLUGIN_VERSION,
    launcher_version: str = __version__,
) -> tuple[Path, dict]:
    """Build the plugin once per Skill fingerprint and return ``(dir, manifest)``.

    Concurrency-safe enough for a local sidecar: the tree is assembled in a
    temporary sibling and moved into place; a racing process that wins the move
    is detected and its identical cache entry reused.
    """

    fingerprint = skill_fingerprint(skill_dir)
    key = f"{plugin_version}-{launcher_version}-{fingerprint[:20]}"
    cache_root = Path(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_dir = cache_root / key

    if cache_dir.is_dir():
        try:
            # The cache key already covers the Skill payload, so the stored
            # manifest can be trusted; re-hashing 13 MB on every task start
            # would dominate the launcher latency.
            manifest = json.loads((cache_dir / "plugin.manifest.json").read_text(encoding="utf-8"))
            if not validate_plugin_dir(cache_dir):
                return cache_dir, manifest
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        shutil.rmtree(cache_dir, ignore_errors=True)

    try:
        temp_out = cache_root / f".building-{uuid.uuid4().hex}"
        manifest = build_plugin(Path(skill_dir), temp_out)
        try:
            os.replace(temp_out, cache_dir)
        except OSError:
            # Another launcher process won the race with an identical build.
            shutil.rmtree(temp_out, ignore_errors=True)
            manifest = json.loads((cache_dir / "plugin.manifest.json").read_text(encoding="utf-8"))
    except PluginError as exc:
        if exc.reason == "output_not_empty" and cache_dir.is_dir():
            manifest = read_manifest(cache_dir)
        else:
            raise
    problems = validate_plugin_dir(cache_dir)
    if problems:
        raise PluginError(
            "plugin_invalid",
            "cached plugin failed structural validation",
            {"plugin_dir": str(cache_dir), "problems": problems},
        )
    return cache_dir, manifest


def materialize_plugin(source: Path, destination: Path) -> dict:
    """Copy a cached/prebuilt plugin into the task workspace.

    Files are hard-linked where the filesystem supports it (same volume), and
    copied otherwise.  The plugin tree is read-only for the agent, so sharing
    inodes with the cache cannot change the source content; it only makes task
    start fast (622 files, ~13 MB per task).
    """

    source = Path(source).resolve()
    destination = Path(destination)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    linked = 0
    copied = 0
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(path, target)
            linked += 1
        except OSError:
            shutil.copyfile(path, target)
            copied += 1
    if copied == 0:
        mode = "hardlink"
    elif linked == 0:
        mode = "copy"
    else:
        mode = "mixed"
    return {
        "mode": mode,
        "linked": linked,
        "copied": copied,
        "source": str(source),
        "dir": str(destination),
    }
