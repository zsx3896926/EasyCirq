#!/usr/bin/env python3
"""Rebrand the vendored easyeda-agent Connector extension into Zhigou's connector.

Idempotent. Only touches ``connector/``. Every rule is recorded so the
transformation from the pinned upstream commit is auditable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONNECTOR = REPO / "connector"

EXT_UUID = "a6e6b788551945b399e150d80efa6e31"
EXT_NAME = "zhigou-connector"
EXT_DISPLAY = "Zhigou EDA Connector"
EXT_VERSION = "0.1.0"
EXT_PUBLISHER = "zsx3896926"
REPO_URL = "https://github.com/zsx3896926/hardware-design-skill"

RULES: list[tuple[str, str, str]] = [
    ("easyeda-agent", "zhigou-agent", "service id / socket prefix / log prefix"),
    ("0xeda0", "0x5a47", "daemon port start 60832 -> 23111"),
    ("0xeda9", "0x5a50", "daemon port end 60841 -> 23120"),
    ("60832", "23111", "daemon port literal"),
    ("60841", "23120", "daemon port literal (end)"),
    ("'daemonPorts'", "'zhigouDaemonPorts'", "extension user-config key isolation"),
    ("__easyedaAgentTransportRuntime", "__zhigouTransportRuntime", "shared runtime key isolation"),
    ("EDA Agent", "Zhigou", "in-EDA menu title"),
]

TEXT_SUFFIXES = {".ts", ".mts", ".js", ".mjs", ".json", ".md", ".yml", ".yaml"}
SKIP_DIRS = {"node_modules", "build", "dist", ".git"}
PLACEHOLDER = "@@EASYEDA_DOT_COM@@"


def transform(text: str) -> str:
    text = text.replace("easyeda.com", PLACEHOLDER)
    for old, new, _note in RULES:
        text = text.replace(old, new)
    return text.replace(PLACEHOLDER, "easyeda.com")


def rewrite_manifest() -> dict:
    path = CONNECTOR / "extension.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["name"] = EXT_NAME
    data["uuid"] = EXT_UUID
    data["displayName"] = EXT_DISPLAY
    data["version"] = EXT_VERSION
    data["publisher"] = EXT_PUBLISHER
    data["description"] = (
        "Zhigou (智构) EDA connector: bridges the local Zhigou runtime daemon to the "
        "official eda.* API over a local WebSocket. Derived from easyeda-agent "
        "(MIT) — see NOTICE."
    )
    data["engines"] = {"eda": ">=3.2.0"}
    data["license"] = "MIT"
    data["repository"] = {"type": "github", "url": REPO_URL}
    data["homepage"] = REPO_URL
    for menu_group in data.get("headerMenus", {}).values():
        for menu in menu_group:
            if menu.get("id") == "Zhigou" or menu.get("title") == "Zhigou":
                menu["id"] = "Zhigou"
                menu["title"] = "Zhigou"
            for item in menu.get("menuItems", []):
                if item.get("title") == "About...":
                    item["title"] = "About Zhigou..."
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent="\t") + "\n", encoding="utf-8", newline="\n"
    )
    return data


def rewrite_package_json() -> None:
    path = CONNECTOR / "package.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["name"] = EXT_NAME
    data["version"] = EXT_VERSION
    data["description"] = (
        "Zhigou connector extension for EasyEDA Pro (derived from easyeda-agent, MIT)."
    )
    data["author"] = EXT_PUBLISHER
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent="\t") + "\n", encoding="utf-8", newline="\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--root", default="", help="operate on this tree root instead of the repo")
    args = ap.parse_args()

    global REPO, CONNECTOR
    if args.root:
        REPO = Path(args.root).resolve()
        CONNECTOR = REPO / "connector"

    changed: list[str] = []
    for path in sorted(CONNECTOR.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(CONNECTOR).parts):
            continue
        if path.name in {"extension.json", "package.json", "package-lock.json"}:
            continue
        original = path.read_text(encoding="utf-8")
        updated = transform(original)
        if updated != original:
            changed.append(str(path.relative_to(REPO)))
            if not args.check:
                path.write_text(updated, encoding="utf-8", newline="\n")

    if not args.check:
        rewrite_manifest()
        rewrite_package_json()
        # package-lock: only the top-level name/version identity matters.
        lock = CONNECTOR / "package-lock.json"
        if lock.exists():
            text = lock.read_text(encoding="utf-8")
            data = json.loads(text)
            data["name"] = EXT_NAME
            data["version"] = EXT_VERSION
            pkgs = data.get("packages", {})
            if "" in pkgs:
                pkgs[""]["name"] = EXT_NAME
                pkgs[""]["version"] = EXT_VERSION
            lock.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )

    report = {
        "module": "connector",
        "extension": {
            "name": EXT_NAME,
            "uuid": EXT_UUID,
            "displayName": EXT_DISPLAY,
            "version": EXT_VERSION,
        },
        "rules": [{"pattern": o, "replacement": n, "note": d} for o, n, d in RULES],
        "changed_files": len(changed),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    for item in changed[:10]:
        print("  ", item)
    if len(changed) > 10:
        print(f"   ... {len(changed) - 10} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
