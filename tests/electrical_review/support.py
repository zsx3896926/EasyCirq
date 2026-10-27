import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "design-hardware" / "scripts"
PACKAGE_DIR = SCRIPTS / "electrical_review"
ALIAS = "electrical_review_impl"


def impl():
    """Load the production package under a non-conflicting alias."""
    if ALIAS in sys.modules:
        return sys.modules[ALIAS]
    spec = importlib.util.spec_from_file_location(
        ALIAS, str(PACKAGE_DIR / "__init__.py"),
        submodule_search_locations=[str(PACKAGE_DIR)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[ALIAS] = module
    spec.loader.exec_module(module)
    return module


def module(name):
    impl()
    return importlib.import_module(ALIAS + "." + name)


def review(data):
    engine = module("engine")
    meta = {"path": "<memory>", "sha256": "0" * 64,
            "semantic_sha256": "0" * 64, "bytes": len(json.dumps(data)),
            "schema": data.get("schema"), "project_id": None,
            "document_id": None, "source_type": None, "units": None,
            "snapshot_binding": {"declared_sha256": None, "verified": False}}
    _normalized, report = engine.review(json.loads(json.dumps(data)), meta)
    return report


def validate(data):
    return module("contract").validate(json.loads(json.dumps(data)))


def cli(args, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SCRIPTS)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "electrical_review"] + list(args),
        cwd=str(cwd or ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", timeout=120)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value + "\n", encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return path


def temporary_dir():
    return tempfile.TemporaryDirectory(prefix="er-test-")


def finding_codes(report):
    return sorted((item["rule_id"], item["state"], item["severity"],
                   item.get("code")) for item in report["findings"]
                  if item["rule_id"] != "INPUT")


def statuses(report):
    return {key: value["status"] for key, value in
            report["summary"]["rules"].items()}
