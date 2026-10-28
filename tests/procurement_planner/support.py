"""Shared helpers for procurement planner tests (subprocess CLI only)."""

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "easycirq" / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

AS_OF = "2026-10-27T12:00:00+08:00"
CAPTURED = "2026-10-27T08:00:00+08:00"
VALID_UNTIL = "2026-10-28T08:00:00+08:00"


def run_cli(args, timeout=120, env_extra=None):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, "-m", "procurement_planner"] + list(args),
        cwd=str(SCRIPTS),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )
    report = None
    if proc.stdout.strip():
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            report = None
    return proc, report


def write_input(directory, data, name="input.json"):
    path = Path(directory) / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return str(path)


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def base_input():
    return copy.deepcopy(load_fixture("basic.json"))


def snapshot(snapshot_id="SNAP-1", channel="lcsc_mall",
             source="synthetic_fixture", truth="synthetic_not_live",
             captured=CAPTURED, valid_until=VALID_UNTIL, sha=None):
    return {
        "snapshot_id": snapshot_id,
        "source": source,
        "declared_truth": truth,
        "captured_at": captured,
        "valid_until": valid_until,
        "channel": channel,
        "sha256": sha or ("a" * 64),
        "notes": "test fixture",
    }


def offer(offer_id="OF-1", mpn="R-10K", footprint="R0603", channel="lcsc_mall",
          product_id="C1", currency="CNY", tax_basis="incl",
          price_mode="total_tier", tiers=None, price_unit=None,
          stock=1000, moq=1, mpq=1, lead_time=None, snapshot_id="SNAP-1",
          smt=None, manufacturer="YAGEO", stock_status=None,
          reserved=0, independent=True, pool_id=None):
    if tiers is None:
        tiers = [{"min_qty": 1, "unit_price": "0.0100"}]
    if price_unit is None:
        price_unit = {"kind": "per_each"}
    if isinstance(stock, dict):
        stock_obj = stock
    else:
        stock_obj = {
            "qty": stock,
            "status": stock_status or "in_stock",
            "reserved": reserved,
            "independent": independent,
        }
        if pool_id is not None:
            stock_obj["pool_id"] = pool_id
        elif independent:
            stock_obj["pool_id"] = "POOL-%s" % offer_id
    result = {
        "offer_id": offer_id,
        "supplier": "TEST-SUPPLIER",
        "channel": channel,
        "product_id": product_id,
        "mpn": mpn,
        "manufacturer": manufacturer,
        "footprint": footprint,
        "package": footprint,
        "currency": currency,
        "tax_basis": tax_basis,
        "price_mode": price_mode,
        "price_tiers": tiers,
        "price_unit": price_unit,
        "moq": moq,
        "mpq": mpq,
        "stock": stock_obj,
        "lead_time": lead_time or {"kind": "in_stock", "days_min": 0,
                                   "days_max": 0},
        "snapshot_id": snapshot_id,
    }
    if smt is not None:
        result["smt"] = smt
    return result


def fee(fee_id="FEE-1", kind="shipping", channel="lcsc_mall",
        basis="per_order", amount="0.00", currency="CNY", tax_basis="incl",
        unknown=False, rate=None, waiver=None):
    result = {
        "fee_id": fee_id,
        "kind": kind,
        "channel": channel,
        "basis": basis,
        "currency": currency,
        "tax_basis": tax_basis,
        "source": "test fixture",
        "captured_at": CAPTURED,
    }
    if unknown:
        result["unknown"] = True
    elif rate is not None:
        result["rate"] = rate
    else:
        result["amount"] = amount
    if waiver is not None:
        result["waiver"] = waiver
    return result


def row(line_id="L1", designators=None, qty_per_board=1, mpn="R-10K",
        manufacturer="YAGEO", footprint="R0603", assembly="smt",
        dnp=False, consigned=0, consigned_qualified=True, lcsc=None):
    if designators is None:
        designators = ["R1"]
    supply_ids = {"lcsc": lcsc} if lcsc else {}
    return {
        "line_id": line_id,
        "designators": designators,
        "qty_per_board": qty_per_board,
        "mpn": mpn,
        "manufacturer": manufacturer,
        "supply_ids": supply_ids,
        "footprint": footprint,
        "package": footprint,
        "assembly": assembly,
        "dnp": dnp,
        "consigned_qty": consigned,
        "consigned_qualified": consigned_qualified,
        "params": {},
        "unknown_fields": [],
        "identity_source": {"kind": "synthetic_fixture",
                            "source": "test fixture"},
    }


def input_doc(rows, offers, snapshots=None, fees=None, board=10,
              attrition=None, demand=None, policies=None, alternates=None,
              budget=None):
    doc = {
        "schema": "procurement-input/v1",
        "project": {
            "name": "unit-test",
            "bom_revision": "rev-T",
            "board_quantity": board,
            "allow_zero_boards": False,
        },
        "evaluation": {"as_of": AS_OF, "freshness": {"max_age_hours": "24"}},
        "policies": policies or {
            "attrition": attrition or {"ratio": "0", "fixed": 0,
                                       "minimum": 0},
            "overbuy": {"max_extra_qty": 50, "max_extra_ratio": "0.20",
                        "allow_price_break_extra": True},
            "order_policy": "moq_mpq",
            "substitution": {"enabled": False,
                             "allowed_grades": ["exact_identity",
                                                "evidence_supported_candidate"]},
            "channel_preference": ["lcsc_mall", "jlc_smt"],
        },
        "bom": {"revision": "rev-T",
                "source": "synthetic test fixture", "rows": rows},
        "demand": demand or {
            "channels": ["lcsc_mall", "jlc_smt"],
            "assembly_strategy": "smt",
            "hand_solder_allowed": False,
            "self_supply_allowed": False,
            "due_date": "2026-11-15T00:00:00+08:00",
            "budget": budget or {"amount": "1000.00", "currency": "CNY"},
            "channel_preference": ["lcsc_mall", "jlc_smt"],
            "split_policy": {"allow_multi_offer": True,
                             "max_orders_per_line": 3,
                             "max_orders_total": None},
        },
        "supply_snapshots": snapshots if snapshots is not None else [],
        "offers": offers,
        "fees": fees if fees is not None else [],
        "alternates": alternates or [],
    }
    return doc
