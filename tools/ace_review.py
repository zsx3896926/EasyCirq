"""Ace-review: deterministic checklist reviewer for schematic snapshots.

The checklist encodes "ace engineer" questions that a senior reviewer asks
before signing off a schematic.  Input is a snapshot JSON (components, pins,
nets, geometry) captured from a live page; output is findings + a verdict.

No EDA, no LLM: every rule is a pure function over the snapshot.

Rule policy
-----------
* ``error`` blocks the review verdict (structural defects that must be fixed);
* ``warn`` reports a suspicious structure without blocking.  A rule that
  cannot judge because the snapshot lacks an optional field also reports
  ``warn`` with the word "unknown" in the message -- never ``error`` and never
  a crash.  (``info`` is intentionally not emitted: the review gate treats an
  unknown severity as blocking evidence.)

Rule ids are stable (R01..R30); the module-level :data:`RULES` table is the
single source of truth consumed by :func:`review`.
"""

from __future__ import annotations

import math
import re

SCHEMA = "easycirq-ace-snapshot/v1"
REVIEW_SCHEMA = "easycirq-ace-review/v1"

POWER_RE = re.compile(
    r"^(?:\+?[0-9]+V[0-9]*|[A-Z0-9_]*VDD[A-Z0-9_]*|[A-Z0-9_]*VCC[A-Z0-9_]*|"
    r"VBUS[A-Z0-9_]*|VBAT[A-Z0-9_]*|VSYS[A-Z0-9_]*|VIN[A-Z0-9_]*|"
    r"3V3[A-Z0-9_]*|5V[A-Z0-9_]*)$",
    re.IGNORECASE,
)
GROUND_RE = re.compile(r"^(?:A?GND[A-Z0-9_]*|PGND[A-Z0-9_]*|DGND[A-Z0-9_]*|VSS[A-Z0-9_]*)$",
                       re.IGNORECASE)
I2C_RE = re.compile(r"(?i)(?:I2C|SCL|SDA|SCX|SDX|SCLK|SDATA)")
FB_RE = re.compile(r"(?i)^(?:FB|ADJ|VFB|FB_[A-Z0-9_]+|.*_FB)$")
ENABLE_RE = re.compile(r"(?i)^(?:EN[_0-9A-Z#]*|CE#?|SHDN#?)$")
AUTO_NET_RE = re.compile(r"^[A-Z]{1,3}[0-9]+_N[0-9]+$")

POWER_PIN_NAMES = ("VDD", "VDDIO", "VCC", "AVDD", "DVDD", "PVDD",
                   "VDDA", "VDDD", "VBAT", "VSYS", "VIN")
RESET_BOOT_RE = re.compile(
    r"(?i)^(?:N?RESET|NRST|RST|RESET#|BOOT0|BOOT_[0-9A-Z]+|STRAP[0-9]*|IO0|GPIO0)$")
UNUSED_PIN_RE = re.compile(r"(?i)^(?:NC|DNU|DNI|RESERVED|RSVD)(?:[0-9_#/() -].*)?$")
CS_PIN_RE = re.compile(r"(?i)^(?:CS|CS#|NCS|SS|SS#|NSS|SSN|CHIP_?SELECT)$")
ADDR_PIN_RE = re.compile(r"(?i)^(?:ADDR|ADDRESS|A[0-2]|SEL|SA[0-1]|I2C_ADDR|ADDR[0-9])$")
INPUT_RAIL_RE = re.compile(
    r"(?i)^(?:VBUS|VIN|VIN_[A-Z0-9_]+|DC_?IN|PWR_?IN|BAT\+?|VBAT|VBAT_[A-Z0-9_]+|"
    r"\+?5V_?IN)$")
PLACEHOLDER_RE = re.compile(r"\{[^}]*\}")
CAP_UF_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(u|µ|n|p)f", re.IGNORECASE)
CAP_VOLT_RE = re.compile(r"(?<![0-9.])([0-9]+(?:\.[0-9]+)?)\s*v(?![a-z0-9])", re.IGNORECASE)

POLAR_TEXT = ("electrolytic", "e-cap", "ecap", "tantalum", "tant", "polarized",
              "polarised", "铝电解", "钽", "有极性")
CERAMIC_TEXT = ("ceramic", "mlcc", "x7r", "x5r", "c0g", "np0", "瓷片")
LDO_TEXT = ("ldo", "low dropout", "low-dropout", "linear regulator", "1117",
            "lp2985", "mic5205", "tps7", "ams1117")
TVS_TEXT = ("tvs", "esd", "smf", "pesd", "transient voltage", "防静电")
FUSE_TEXT = ("fuse", "ptc", "polyfuse", "self-resetting", "保险丝", "自恢复")

DERATING_FACTOR = {"ceramic": 2.0, "unknown": 2.0,
                   "polarized": 1.5, "electrolytic": 1.5, "tantalum": 1.5}
DECOUPLING_MAX_DIST = 180.0
LDO_MIN_MARGIN_V = 0.2

DESIGNATOR_KIND = (
    ("C", "capacitor"), ("R", "resistor"), ("L", "inductor"), ("D", "diode"),
    ("Q", "transistor"), ("U", "ic"), ("J", "connector"), ("CN", "connector"),
    ("FB", "ferrite"), ("SW", "switch"), ("Y", "crystal"), ("X", "crystal"),
    ("TP", "testpoint"), ("MK", "ic"), ("F", "fuse"),
)


def designator_kind(ref: str) -> str:
    for prefix, kind in DESIGNATOR_KIND:
        if str(ref).startswith(prefix):
            return kind
    return "other"


# ---------------------------------------------------------------------------
# defensive accessors: missing data must never raise
# ---------------------------------------------------------------------------

def _ref(comp):
    return str(comp.get("ref") or "?")


def _text(comp):
    """Lower-cased searchable text for a component (value/mpn/type/params)."""
    parts = [comp.get("ref"), comp.get("value"), comp.get("mpn"),
             comp.get("type"), comp.get("notes")]
    params = comp.get("params") or {}
    if isinstance(params, dict):
        parts.extend(str(v) for v in params.values()
                     if isinstance(v, (str, int, float)))
    return " ".join(str(p) for p in parts if p).lower()


def _components(snapshot):
    comps = snapshot.get("components") if isinstance(snapshot, dict) else None
    return comps if isinstance(comps, list) else []


def _comp_pins(comp):
    pins = comp.get("pins") if isinstance(comp, dict) else None
    return pins if isinstance(pins, list) else []


def _pins_iter(snapshot):
    for comp in _components(snapshot):
        if not isinstance(comp, dict):
            continue
        for pin in _comp_pins(comp):
            if isinstance(pin, dict):
                yield comp, pin


def _net_str(net):
    if net is None:
        return None
    text = str(net).strip()
    return text or None


def _norm(net):
    return _net_str(net).replace("-", "_") if _net_str(net) else ""


def _matches(regex, value):
    text = _net_str(value)
    if not text:
        return False
    try:
        return bool(regex.match(text.replace("-", "_")))
    except TypeError:  # pragma: no cover - defensive
        return False


def _pins(snapshot):
    out = {}
    for comp, pin in _pins_iter(snapshot):
        out[(_ref(comp), str(pin.get("number")))] = pin
    return out


def _nets(snapshot):
    """name -> set of (ref, pin)"""
    out = {}
    for comp, pin in _pins_iter(snapshot):
        net = _net_str(pin.get("net"))
        if net:
            out.setdefault(net, set()).add((_ref(comp), str(pin.get("number"))))
    return out


def _comp(snapshot, ref):
    for comp in _components(snapshot):
        if isinstance(comp, dict) and _ref(comp) == ref:
            return comp
    return None


def _bbox_center(comp):
    b = comp.get("bbox") or {}
    if not isinstance(b, dict):
        return None
    try:
        return ((b["minX"] + b["maxX"]) / 2.0, (b["minY"] + b["maxY"]) / 2.0)
    except (KeyError, TypeError):
        return None


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _add(findings, rule, severity, message, refs=None):
    findings.append({"rule": rule, "severity": severity,
                     "message": message, "refs": list(refs or [])})


def _is_power(net):
    return _matches(POWER_RE, net)


def _is_ground(net):
    return _matches(GROUND_RE, net)


def _other_nets(comp, net):
    return {_net_str(p.get("net")) for p in _comp_pins(comp)
            if _net_str(p.get("net")) and _net_str(p.get("net")) != net}


def _cap_on_ground(comp):
    return any(_is_ground(p.get("net")) for p in _comp_pins(comp))


def _param(comp, *names):
    """First numeric parameter among params[key] / comp[key]."""
    params = comp.get("params") if isinstance(comp.get("params"), dict) else {}
    for name in names:
        for holder in (params, comp):
            if not isinstance(holder, dict):
                continue
            value = holder.get(name)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                m = re.search(r"-?[0-9]+(?:\.[0-9]+)?", value)
                if m:
                    return float(m.group(0))
    return None


def _cap_uf(comp):
    m = CAP_UF_RE.search(_text(comp))
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2).lower()
    return {"u": value, "µ": value, "n": value / 1000.0,
            "p": value / 1000000.0}.get(unit)


def _cap_voltage(comp):
    volts = _param(comp, "voltage", "rated_voltage", "vrating", "voltage_rating")
    if volts is not None:
        return volts
    text = " ".join(str(comp.get(k) or "") for k in ("value", "mpn"))
    m = CAP_VOLT_RE.search(text)
    return float(m.group(1)) if m else None


def _cap_kind(comp):
    text = _text(comp)
    if any(key in text for key in POLAR_TEXT):
        return "polarized"
    if any(key in text for key in CERAMIC_TEXT):
        return "ceramic"
    declared = str(comp.get("type") or "").lower()
    if declared:
        if any(key in declared for key in ("electrolytic", "tantalum")):
            return "polarized"
        if "ceramic" in declared:
            return "ceramic"
        return declared
    return "unknown"


def _cap_type(comp):
    return _cap_kind(comp)


def _net_voltage(snapshot, net):
    name = _net_str(net)
    if not name:
        return None
    table = snapshot.get("net_voltage") if isinstance(snapshot, dict) else None
    if isinstance(table, dict):
        for key in (name, name.upper(), name.lstrip("+"), "+" + name.lstrip("+")):
            if key in table:
                try:
                    return float(table[key])
                except (TypeError, ValueError):
                    pass
    norm = name.replace("-", "_")
    m = re.match(r"^\+?([0-9]+)V([0-9])$", norm, re.IGNORECASE)
    if m:  # 3V3 -> 3.3, 1V8 -> 1.8
        return float(m.group(1)) + float("0." + m.group(2))
    m = re.match(r"^\+?([0-9]+(?:\.[0-9]+)?)V$", norm, re.IGNORECASE)
    if m:
        return float(m.group(1))
    if norm.upper() in ("VBUS", "USB_VBUS", "5V0"):
        return 5.0
    return None


def _is_output_net(net):
    name = _net_str(net)
    if not name:
        return False
    if _is_ground(name):
        return False
    norm = name.upper().replace("-", "_")
    return _is_power(name) or norm in ("VOUT", "VO", "OUT", "VDD_OUT") or \
        norm.endswith(("_OUT", "_VOUT"))


def _members(snapshot, net):
    return _nets(snapshot).get(_net_str(net), set())


def _net_on_connector(snapshot, net):
    name = _net_str(net)
    if not name:
        return False
    for comp, pin in _pins_iter(snapshot):
        if designator_kind(_ref(comp)) == "connector" and \
                _net_str(pin.get("net")) == name:
            return True
    return False


def _is_usb_data_net(net):
    name = _net_str(net)
    if not name:
        return False
    norm = name.upper().replace("-", "_").replace("+", "P").replace("_", "")
    base = norm[3:] if norm.startswith("USB") else norm
    return base in ("DP", "DN", "DPLUS", "DMINUS")


def _diff_pair_key(net):
    """Return (base, polarity) for a differential-style net name, else None."""
    name = _net_str(net)
    if not name:
        return None
    upper = name.upper()
    # Only explicit _P/_N-style names count as declared differential pairs.
    # A lone "+"/"-" net may be legacy single-ended naming (reported by R22
    # only when both polarities exist).
    for suffix, polarity in (("_P", "P"), ("_DP", "P"), ("_N", "N"), ("_DN", "N")):
        if upper.endswith(suffix):
            return name[:-len(suffix)], polarity
    return None


# ---------------------------------------------------------------------------
# R01-R10: original checklist (ids and severities are stable)
# ---------------------------------------------------------------------------

def rule_floating_pins(snapshot, findings):
    for comp, pin in _pins_iter(snapshot):
        if _net_str(pin.get("net")) is None and not pin.get("nc"):
            _add(findings, "R01-floating-pin", "warn",
                 "%s:%s (%s) is floating" % (
                     _ref(comp), pin.get("number"), pin.get("name")),
                 [_ref(comp)])


def rule_i2c_pullups(snapshot, findings):
    nets = _nets(snapshot)
    for name, pins in nets.items():
        if not _matches(I2C_RE, name):
            continue
        has_pull = False
        for ref, _pin in pins:
            comp = _comp(snapshot, ref)
            if comp and designator_kind(ref) == "resistor":
                for p in _comp_pins(comp):
                    target = _net_str(p.get("net"))
                    if target and target != name and _is_power(target):
                        has_pull = True
        if not has_pull:
            _add(findings, "R02-i2c-pullup", "error",
                 "I2C net %r has no pull-up to a power rail" % name,
                 sorted({r for r, _ in pins}))


def rule_decoupling(snapshot, findings, max_dist=DECOUPLING_MAX_DIST):
    nets = _nets(snapshot)
    for comp in _components(snapshot):
        if designator_kind(_ref(comp)) != "ic":
            continue
        ic_center = _bbox_center(comp)
        for pin in _comp_pins(comp):
            pname = str(pin.get("name") or "").upper()
            pnet = _net_str(pin.get("net")) or ""
            if pname not in POWER_PIN_NAMES:
                continue
            if not (_is_power(pnet) or _is_ground(pnet)):
                continue
            ok = False
            for ref, _ in nets.get(pnet, set()):
                if designator_kind(ref) != "capacitor":
                    continue
                cap = _comp(snapshot, ref)
                cap_center = _bbox_center(cap) if cap else None
                if ic_center and cap_center and _dist(ic_center, cap_center) <= max_dist:
                    if cap and _cap_on_ground(cap):
                        ok = True
            if not ok:
                _add(findings, "R03-decoupling", "error",
                     "%s power pin %s (%s) has no nearby ground cap"
                     % (_ref(comp), pin.get("number"), pname), [_ref(comp)])


def rule_ground_tie(snapshot, findings):
    """AGND/DGND/PGND must be tied to GND exactly once (0R / net-tie)."""
    if not any(True for _ in _pins_iter(snapshot)):
        return  # no connectivity data: cannot judge, do not invent an error
    # A single-ground design (only GND / VSS) needs no tie; the rule only
    # applies when at least one non-plain ground domain (AGND/DGND/PGND/...)
    # exists and must be stitched to the plain ground exactly once.
    ground_names = set()
    for comp, pin in _pins_iter(snapshot):
        net = _net_str(pin.get("net"))
        if net and _is_ground(net):
            ground_names.add(net.upper())
    declared = list(snapshot.get("nets") or [])
    for page_nets in (snapshot.get("nets_by_page") or {}).values():
        declared.extend(page_nets or [])
    for net in declared:
        name = net.get("name") if isinstance(net, dict) else net
        if isinstance(name, str) and _is_ground(name):
            ground_names.add(name.upper())
    plain = {"GND", "VSS", "0V", "GNDA", "GNDD"}
    non_plain = {n for n in ground_names if n not in plain and not n.startswith("GND")}
    if not non_plain:
        return
    if len(ground_names) <= 1:
        # a single ground domain (even if it is named AGND/DGND) needs no tie
        return
    tie_refs = []
    for comp in _components(snapshot):
        if designator_kind(_ref(comp)) not in ("resistor", "ferrite"):
            continue
        ground_nets = {n for n in (_net_str(p.get("net")) for p in _comp_pins(comp))
                       if n and _is_ground(n)}
        if len(ground_nets) >= 2:
            tie_refs.append(_ref(comp))
    if len(tie_refs) != 1:
        _add(findings, "R04-ground-tie", "error",
             "expected exactly one AGND/DGND-to-GND tie; found %d (%s)"
             % (len(tie_refs), ", ".join(tie_refs) or "none"), tie_refs)


def rule_feedback_after_cap(snapshot, findings):
    nets = _nets(snapshot)
    for comp, pin in _pins_iter(snapshot):
        pname = str(pin.get("name") or "")
        pnet = _net_str(pin.get("net")) or ""
        if not (_matches(FB_RE, pname) or _matches(FB_RE, pnet)):
            continue
        has_cap = any(designator_kind(ref) == "capacitor"
                      for ref, _ in nets.get(pnet, set()))
        if not has_cap:
            _add(findings, "R05-feedback-cap", "warn",
                 "%s:%s feedback net %r has no capacitor (check "
                 "feedback taken after output cap)"
                 % (_ref(comp), pin.get("number"), pnet), [_ref(comp)])


def rule_enable_pull(snapshot, findings):
    for comp, pin in _pins_iter(snapshot):
        if designator_kind(_ref(comp)) != "ic":
            continue
        pname = str(pin.get("name") or "")
        if not _matches(ENABLE_RE, pname):
            continue
        if _net_str(pin.get("net")) is None:
            _add(findings, "R06-enable-net", "error",
                 "%s enable pin %s (%s) is unconnected"
                 % (_ref(comp), pin.get("number"), pname), [_ref(comp)])


def rule_esd_connector(snapshot, findings):
    nets = _nets(snapshot)
    for comp in _components(snapshot):
        if designator_kind(_ref(comp)) != "connector":
            continue
        for pin in _comp_pins(comp):
            net = _net_str(pin.get("net"))
            if not net:
                continue
            members = nets.get(net, set())
            guarded = any(designator_kind(ref) in ("diode", "resistor", "ferrite")
                          for ref, _ in members)
            if not guarded:
                _add(findings, "R07-esd-series", "warn",
                     "connector %s pin %s net %r has no series/ESD part"
                     % (_ref(comp), pin.get("number"), net), [_ref(comp)])


def rule_power_testpoint(snapshot, findings):
    nets = _nets(snapshot)
    for name, pins in nets.items():
        if not _is_power(name):
            continue
        upper = name.upper()
        if upper.startswith(("VIN", "VBUS", "VDD", "VBAT", "VSYS", "5V")) or \
           upper.startswith(("3V3", "+3V3", "+5V")):
            if not any(designator_kind(ref) == "testpoint" for ref, _ in pins):
                _add(findings, "R08-power-testpoint", "warn",
                     "power net %r has no test point" % name,
                     sorted({r for r, _ in pins})[:4])


def rule_net_naming(snapshot, findings):
    auto = []
    for comp, pin in _pins_iter(snapshot):
        net = _net_str(pin.get("net"))
        if net and _matches(AUTO_NET_RE, net):
            auto.append(net)
    for name in sorted(set(auto))[:20]:
        _add(findings, "R09-auto-net-name", "warn",
             "auto-generated net name %r (rename to intent name)" % name)


def rule_titleblock(snapshot, findings):
    titleblock = snapshot.get("titleblock") if isinstance(snapshot, dict) else None
    fields = (titleblock or {}).get("fields") or {}
    missing = [k for k, v in fields.items() if not str(v or "").strip()]
    if missing:
        _add(findings, "R10-titleblock", "warn",
             "title block fields empty: %s" % ", ".join(sorted(missing)[:6]))


# ---------------------------------------------------------------------------
# R11-R30: expanded checklist (deterministic, snapshot-only)
# ---------------------------------------------------------------------------

def rule_bulk_ceramic_per_rail(snapshot, findings):
    """R11: every IC power rail needs bulk (>=1uF) and ceramic (<=1uF) caps."""
    nets = _nets(snapshot)
    rails = set()
    for comp, pin in _pins_iter(snapshot):
        if designator_kind(_ref(comp)) != "ic":
            continue
        net = _net_str(pin.get("net"))
        if str(pin.get("name") or "").upper() in POWER_PIN_NAMES and _is_power(net):
            rails.add(net)
    for rail in sorted(rails):
        caps = []
        for ref, _ in nets.get(rail, set()):
            if designator_kind(ref) != "capacitor":
                continue
            comp = _comp(snapshot, ref)
            if comp and _cap_on_ground(comp):
                caps.append(comp)
        if not caps:
            continue  # R03 already reports the missing decoupling
        # Classifying bulk vs ceramic needs an explicit cap type: bare
        # capacitance values (older snapshots) are not enough to call a rail
        # incomplete, so stay silent instead of guessing.
        if not any(comp.get("type") for comp in caps):
            continue
        values = [_cap_uf(comp) for comp in caps]
        if any(v is None for v in values):
            _add(findings, "R11-bulk-ceramic", "warn",
                 "rail %r: capacitor values unknown; bulk+ceramic mix not verified"
                 % rail, sorted({_ref(c) for c in caps})[:4])
            continue
        has_ceramic = any(
            _cap_type(comp) == "ceramic" or (v is not None and v < 1.0)
            for comp, v in zip(caps, values))
        has_bulk = any(v is not None and v >= 1.0 for v in values)
        if not (has_ceramic and has_bulk):
            missing = "bulk (>=1uF)" if not has_bulk else "ceramic (<=1uF)"
            _add(findings, "R11-bulk-ceramic", "warn",
                 "power rail %r lacks %s decoupling (%d cap(s): %s)"
                 % (rail, missing, len(caps), ", ".join(_ref(c) for c in caps[:5])),
                 sorted({_ref(c) for c in caps})[:6])


def rule_polarized_polarity(snapshot, findings):
    """R12: electrolytic/tantalum caps need a documented polarity/orientation."""
    for comp in _components(snapshot):
        if designator_kind(_ref(comp)) != "capacitor":
            continue
        if _cap_kind(comp) != "polarized":
            continue
        params = comp.get("params") if isinstance(comp.get("params"), dict) else {}
        polarity = comp.get("polarity") or params.get("polarity")
        text_polarity = str(polarity or "").strip().lower()
        if not text_polarity or text_polarity in ("unknown", "tbd", "?", "n/a"):
            _add(findings, "R12-pol-cap-polarity", "warn",
                 "polarized cap %s polarity/orientation unknown in snapshot; "
                 "verify the + terminal" % _ref(comp), [_ref(comp)])


def rule_cap_voltage_derating(snapshot, findings):
    """R13: capacitor rated voltage vs the supply voltage implied by the net name."""
    for comp in _components(snapshot):
        if designator_kind(_ref(comp)) != "capacitor":
            continue
        power_nets = [n for n in (_net_str(p.get("net")) for p in _comp_pins(comp))
                      if n and _is_power(n) and not _is_ground(n)]
        if not power_nets:
            continue
        rated = _cap_voltage(comp)
        if rated is None:
            continue  # no rated voltage recorded: nothing to derate (not guessed)
        factor = DERATING_FACTOR.get(_cap_type(comp), 2.0)
        for net in sorted(set(power_nets)):
            net_v = _net_voltage(snapshot, net)
            if net_v is None:
                _add(findings, "R13-cap-derating", "warn",
                     "cap %s on %r: net voltage unknown; %.1fx derating not verified"
                     % (_ref(comp), net, factor), [_ref(comp)])
                continue
            needed = net_v * factor
            if rated < needed - 1e-9:
                _add(findings, "R13-cap-derating", "warn",
                     "cap %s rated %.1fV < %.1fx%.1fV=%.2fV on net %r"
                     % (_ref(comp), rated, factor, net_v, needed, net),
                     [_ref(comp)])


def rule_ldo_dropout(snapshot, findings):
    """R14: LDO dropout must leave headroom between input and output rails."""
    for comp in _components(snapshot):
        if designator_kind(_ref(comp)) != "ic":
            continue
        dropout = _param(comp, "dropout_mv", "dropout", "dropout_voltage")
        if dropout is None:
            # No dropout record: a bare "LDO" name is not a spec, so headroom
            # cannot be judged.  Stay silent instead of inventing a finding.
            continue
        vin_net = None
        vout_net = None
        for pin in _comp_pins(comp):
            pname = str(pin.get("name") or "").upper()
            net = _net_str(pin.get("net"))
            if pname in ("VIN", "VI", "IN", "INPUT", "VIN_") and vin_net is None:
                vin_net = net
            if pname in ("VOUT", "VO", "OUT", "OUTPUT") and vout_net is None:
                vout_net = net
        if not vin_net or not vout_net:
            _add(findings, "R14-ldo-dropout", "warn",
                 "LDO %s input/output pin not identified; dropout not verified "
                 "(unknown)" % _ref(comp), [_ref(comp)])
            continue
        drop_v = dropout / 1000.0 if dropout > 10 else dropout
        vin_v = _net_voltage(snapshot, vin_net)
        vout_v = _net_voltage(snapshot, vout_net)
        if vin_v is None or vout_v is None:
            _add(findings, "R14-ldo-dropout", "warn",
                 "LDO %s input/output voltage unknown; dropout headroom not verified"
                 % _ref(comp), [_ref(comp)])
            continue
        margin = vin_v - vout_v - drop_v
        if margin < LDO_MIN_MARGIN_V - 1e-9:
            _add(findings, "R14-ldo-dropout", "warn",
                 "LDO %s dropout margin %.2fV < %.2fV (Vin %.2fV, Vout %.2fV, "
                 "dropout %.2fV)" % (_ref(comp), margin, LDO_MIN_MARGIN_V,
                                     vin_v, vout_v, drop_v), [_ref(comp)])


def rule_feedback_divider(snapshot, findings):
    """R15: an FB net needs a resistor divider to output (top) and GND (bottom)."""
    nets = _nets(snapshot)
    seen = set()
    for comp, pin in _pins_iter(snapshot):
        if designator_kind(_ref(comp)) != "ic":
            continue  # the divider hangs off the regulator IC's FB pin
        pname = str(pin.get("name") or "")
        pnet = _net_str(pin.get("net"))
        if not (_matches(FB_RE, pname) or _matches(FB_RE, pnet)):
            continue
        if not pnet or pnet in seen:
            continue
        seen.add(pnet)
        # Fixed-output regulators tie FB straight to their own VOUT pin: there
        # is no external divider to expect.
        tied = any(
            str(pin2.get("name") or "").upper() in ("VOUT", "VO", "OUT", "OUTPUT")
            and _net_str(pin2.get("net")) == pnet for pin2 in _comp_pins(comp))
        if tied:
            continue
        has_top = False
        has_bottom = False
        for ref, _ in nets.get(pnet, set()):
            if designator_kind(ref) != "resistor":
                continue
            resistor = _comp(snapshot, ref)
            if not resistor:
                continue
            others = _other_nets(resistor, pnet)
            if any(_is_ground(n) for n in others):
                has_bottom = True
            if any(_is_output_net(n) for n in others if n and not _is_ground(n)):
                has_top = True
        if has_top and has_bottom:
            continue
        missing = "upper divider to output" if not has_top else "lower divider to GND"
        _add(findings, "R15-fb-divider", "warn",
             "feedback net %r lacks %s (divider incomplete)" % (pnet, missing),
             [_ref(comp)])


def rule_crystal_load_caps(snapshot, findings):
    """R16: each crystal terminal needs a load capacitor to ground."""
    nets = _nets(snapshot)
    for comp in _components(snapshot):
        declared = str(comp.get("type") or "").lower()
        if designator_kind(_ref(comp)) != "crystal" and "crystal" not in declared:
            continue
        crystal_nets = [n for n in (_net_str(p.get("net")) for p in _comp_pins(comp)) if n]
        if not crystal_nets:
            _add(findings, "R16-xtal-load-cap", "warn",
                 "crystal %s nets unknown; load capacitors not verified"
                 % _ref(comp), [_ref(comp)])
            continue
        for net in sorted(set(crystal_nets)):
            has_cap = any(
                designator_kind(ref) == "capacitor" and
                _cap_on_ground(_comp(snapshot, ref) or {})
                for ref, _ in nets.get(net, set()))
            if not has_cap:
                _add(findings, "R16-xtal-load-cap", "warn",
                     "crystal %s net %r has no load capacitor to GND"
                     % (_ref(comp), net), [_ref(comp)])


def rule_reset_boot_tie(snapshot, findings):
    """R17: reset/boot-strap pins must be hard-tied or pulled to a rail."""
    for comp, pin in _pins_iter(snapshot):
        if designator_kind(_ref(comp)) != "ic":
            continue
        pname = str(pin.get("name") or "")
        if not _matches(RESET_BOOT_RE, pname):
            continue
        net = _net_str(pin.get("net"))
        if not net:
            _add(findings, "R17-reset-boot", "warn",
                 "reset/strap pin %s:%s (%s) is not tied or pulled (floating)"
                 % (_ref(comp), pin.get("number"), pname), [_ref(comp)])
            continue
        if _is_power(net) or _is_ground(net):
            continue
        pulled = False
        for ref, _ in _members(snapshot, net):
            if designator_kind(ref) != "resistor":
                continue
            resistor = _comp(snapshot, ref)
            if not resistor:
                continue
            if any(_is_power(n) or _is_ground(n)
                   for n in _other_nets(resistor, net)):
                pulled = True
        if not pulled:
            _add(findings, "R17-reset-boot", "warn",
                 "reset/strap pin %s:%s net %r has no pull resistor to power/GND"
                 % (_ref(comp), pin.get("number"), net), [_ref(comp)])


def rule_led_series_resistor(snapshot, findings):
    """R18: every LED needs a series resistor on its current path."""
    for comp in _components(snapshot):
        if designator_kind(_ref(comp)) != "diode":
            continue
        if "led" not in _text(comp):
            continue
        led_nets = [n for n in (_net_str(p.get("net")) for p in _comp_pins(comp)) if n]
        has_series = False
        for net in led_nets:
            if _is_ground(net):
                continue
            for ref, _ in _members(snapshot, net):
                if designator_kind(ref) != "resistor":
                    continue
                resistor = _comp(snapshot, ref)
                if resistor and any(_is_power(n) or _is_ground(n)
                                    for n in _other_nets(resistor, net)):
                    has_series = True
        if not has_series:
            _add(findings, "R18-led-series", "warn",
                 "LED %s has no series resistor on its current path" % _ref(comp),
                 [_ref(comp)])


def rule_button_pullup_debounce(snapshot, findings):
    """R19: a button signal needs a pull-up and a debounce cap to ground."""
    for comp in _components(snapshot):
        if designator_kind(_ref(comp)) != "switch":
            continue
        signal_nets = [n for n in (_net_str(p.get("net")) for p in _comp_pins(comp))
                       if n and not _is_ground(n)]
        if not signal_nets:
            _add(findings, "R19-button", "warn",
                 "switch %s wiring unknown (no non-ground net); pull-up/debounce "
                 "not verified" % _ref(comp), [_ref(comp)])
            continue
        for net in sorted(set(signal_nets)):
            has_pull = False
            has_cap = False
            for ref, _ in _members(snapshot, net):
                part = _comp(snapshot, ref)
                if not part:
                    continue
                others = _other_nets(part, net)
                if designator_kind(ref) == "resistor" and any(_is_power(n) for n in others):
                    has_pull = True
                if designator_kind(ref) == "capacitor" and any(_is_ground(n) for n in others):
                    has_cap = True
            if not has_pull:
                _add(findings, "R19-button", "warn",
                     "button %s net %r has no pull-up resistor to a power rail"
                     % (_ref(comp), net), [_ref(comp)])
            if not has_cap:
                _add(findings, "R19-button", "warn",
                     "button %s net %r has no debounce capacitor to GND"
                     % (_ref(comp), net), [_ref(comp)])


def rule_unused_pin_nc(snapshot, findings):
    """R20: pins named NC/DNU/RESERVED must be marked no-connect explicitly."""
    for comp, pin in _pins_iter(snapshot):
        if designator_kind(_ref(comp)) != "ic":
            continue
        pname = str(pin.get("name") or "")
        if not _matches(UNUSED_PIN_RE, pname):
            continue
        if not pin.get("nc"):
            _add(findings, "R20-unused-nc", "warn",
                 "unused pin %s:%s (%s) not marked NC explicitly (connect it or "
                 "mark no-connect)" % (_ref(comp), pin.get("number"), pname),
                 [_ref(comp)])


def rule_usb_pair_esd(snapshot, findings):
    """R21: USB data lines at a connector need a series resistor or ESD device."""
    nets = _nets(snapshot)
    for net in sorted(nets):
        if not _is_usb_data_net(net):
            continue
        if not _net_on_connector(snapshot, net):
            continue
        has_series = False
        has_esd = False
        for ref, _ in nets.get(net, set()):
            part = _comp(snapshot, ref)
            if not part:
                continue
            if designator_kind(ref) == "resistor":
                for other in _other_nets(part, net):
                    if other and not _net_on_connector(snapshot, other):
                        has_series = True
            if designator_kind(ref) == "diode":
                if any(_is_ground(n) for n in _other_nets(part, net)):
                    has_esd = True
        if not (has_series or has_esd):
            _add(findings, "R21-usb-esd", "warn",
                 "USB data net %r has no series resistor or ESD device" % net,
                 sorted({r for r, _ in nets.get(net, set())})[:6])


def rule_diff_pair_naming(snapshot, findings):
    """R22: differential nets must come in explicit _P/_N pairs."""
    nets = set(_nets(snapshot))
    groups = {}
    for net in nets:
        key = _diff_pair_key(net)
        if key is None:
            continue
        base, polarity = key
        groups.setdefault(base, {})[polarity] = net
    for base, pair in sorted(groups.items()):
        if "P" not in pair or "N" not in pair:
            missing = "N" if "P" in pair else "P"
            present = pair.get("P") or pair.get("N")
            _add(findings, "R22-diff-pair-name", "warn",
                 "differential net %r has no _%s counterpart (pair base %r)"
                 % (present, missing, base), [present])
    # Legacy +/- naming is only reported when BOTH polarities are present; a
    # lone "D+" net is not enough evidence to call it a differential pair.
    for net in sorted(nets):
        if not net.endswith("+"):
            continue
        counterpart = net[:-1] + "-"
        if counterpart in nets:
            _add(findings, "R22-diff-pair-name", "warn",
                 "differential pair %r/%r uses +/- naming; prefer explicit _P/_N"
                 % (net, counterpart), [net, counterpart])


def rule_spi_cs_pullup(snapshot, findings):
    """R23: chip-select nets need a pull-up so the device stays deselected."""
    for comp, pin in _pins_iter(snapshot):
        if designator_kind(_ref(comp)) != "ic":
            continue
        pname = str(pin.get("name") or "")
        if not _matches(CS_PIN_RE, pname):
            continue
        net = _net_str(pin.get("net"))
        if not net:
            _add(findings, "R23-spi-cs-pullup", "warn",
                 "chip-select pin %s:%s (%s) is floating"
                 % (_ref(comp), pin.get("number"), pname), [_ref(comp)])
            continue
        if _is_ground(net) or _is_power(net):
            continue  # hard-strapped select is a deliberate configuration
        has_pull = False
        for ref, _ in _members(snapshot, net):
            part = _comp(snapshot, ref)
            if part and designator_kind(ref) == "resistor" and \
                    any(_is_power(n) for n in _other_nets(part, net)):
                has_pull = True
        if not has_pull:
            _add(findings, "R23-spi-cs-pullup", "warn",
                 "chip-select net %r has no pull-up to a power rail" % net,
                 [_ref(comp)])


def rule_i2c_address_strap(snapshot, findings):
    """R24: I2C address strap pins must be tied and the address documented."""
    for comp in _components(snapshot):
        if designator_kind(_ref(comp)) != "ic":
            continue
        strap_pins = [pin for pin in _comp_pins(comp)
                      if _matches(ADDR_PIN_RE, pin.get("name"))]
        if not strap_pins:
            continue
        for pin in strap_pins:
            if _net_str(pin.get("net")) is None:
                _add(findings, "R24-i2c-address", "warn",
                     "address/strap pin %s:%s (%s) is unconnected; device address "
                     "unknown" % (_ref(comp), pin.get("number"), pin.get("name")),
                     [_ref(comp)])
        params = comp.get("params") if isinstance(comp.get("params"), dict) else {}
        documented = (comp.get("i2c_address") or comp.get("address")
                      or params.get("i2c_address") or params.get("address"))
        if not str(documented or "").strip():
            _add(findings, "R24-i2c-address", "warn",
                 "I2C address strap for %s not documented (unknown address; add an "
                 "i2c_address field)" % _ref(comp), [_ref(comp)])


def rule_connector_reverse_protection(snapshot, findings):
    """R25: connector power pins need reverse-polarity protection or keying."""
    nets = _nets(snapshot)
    for comp in _components(snapshot):
        if designator_kind(_ref(comp)) != "connector":
            continue
        keyed = comp.get("keyed")
        polarity = str(comp.get("polarity") or "").lower()
        if keyed is True or polarity in ("keyed", "reverse-protected", "protected"):
            continue
        for pin in _comp_pins(comp):
            net = _net_str(pin.get("net"))
            if not net or _is_ground(net) or not _is_power(net):
                continue
            protected = any(designator_kind(ref) in ("diode", "transistor", "fuse")
                            for ref, _ in nets.get(net, set()))
            if not protected:
                _add(findings, "R25-reverse-protection", "warn",
                     "connector %s power pin %s net %r has no reverse-polarity "
                     "protection (diode/fuse/keyed)" % (_ref(comp),
                                                        pin.get("number"), net),
                     [_ref(comp)])


def rule_input_fuse(snapshot, findings):
    """R26: input rails need a fuse or reverse-protection element."""
    nets = _nets(snapshot)
    for net in sorted(nets):
        if not _matches(INPUT_RAIL_RE, net):
            continue
        protected = False
        for ref, _ in nets.get(net, set()):
            part = _comp(snapshot, ref)
            if not part:
                continue
            kind = designator_kind(ref)
            if kind == "fuse":
                protected = True
            elif kind in ("diode", "transistor"):
                protected = True
            elif any(key in _text(part) for key in FUSE_TEXT):
                protected = True
        if not protected:
            _add(findings, "R26-input-fuse", "warn",
                 "input rail %r has no fuse/reverse-protection element" % net,
                 sorted({r for r, _ in nets.get(net, set())})[:6])


def rule_connector_tvs(snapshot, findings):
    """R27: external connector nets need a TVS/ESD device."""
    nets = _nets(snapshot)
    for comp in _components(snapshot):
        if designator_kind(_ref(comp)) != "connector":
            continue
        seen = set()
        for pin in _comp_pins(comp):
            net = _net_str(pin.get("net"))
            if not net or _is_ground(net) or net in seen:
                continue
            seen.add(net)
            has_tvs = False
            for ref, _ in nets.get(net, set()):
                part = _comp(snapshot, ref)
                if part and designator_kind(ref) == "diode" and \
                        any(key in _text(part) for key in TVS_TEXT):
                    has_tvs = True
            if not has_tvs:
                _add(findings, "R27-connector-tvs", "warn",
                     "connector %s pin %s net %r has no TVS/ESD device"
                     % (_ref(comp), pin.get("number"), net), [_ref(comp)])


def rule_cross_page_nets(snapshot, findings):
    """R28: nets appearing on several pages must be declared cross-page."""
    pages = snapshot.get("nets_by_page") if isinstance(snapshot, dict) else None
    declared_raw = snapshot.get("cross_page_nets") if isinstance(snapshot, dict) else None
    if not isinstance(pages, dict) or not pages:
        if isinstance(declared_raw, (list, tuple, set)) and declared_raw:
            _add(findings, "R28-cross-page", "warn",
                 "cross-page net data unknown (no nets_by_page); %d declared net(s) "
                 "not verified" % len(declared_raw))
        return
    if not isinstance(declared_raw, (list, tuple, set)):
        declared_raw = []
    declared = {str(n) for n in declared_raw}
    where = {}
    for page, names in pages.items():
        if not isinstance(names, list):
            continue
        for name in names:
            key = _net_str(name)
            if key:
                where.setdefault(key, set()).add(str(page))
    for name, page_set in sorted(where.items()):
        if len(page_set) > 1 and name not in declared:
            _add(findings, "R28-cross-page", "warn",
                 "net %r spans pages %s but is not declared cross-page"
                 % (name, ", ".join(sorted(page_set))))
    for name in sorted(declared):
        if name in where and len(where[name]) <= 1:
            _add(findings, "R28-cross-page", "warn",
                 "declared cross-page net %r appears on one page only (check the "
                 "declaration)" % name)


def rule_bom_completeness(snapshot, findings):
    """R29: BOM values must be real (no {Value}-style placeholders)."""
    for comp in _components(snapshot):
        ref = _ref(comp)
        value = str(comp.get("value") or "").strip()
        mpn = str(comp.get("mpn") or "").strip()
        if PLACEHOLDER_RE.search(value) or PLACEHOLDER_RE.search(mpn):
            _add(findings, "R29-bom-value", "warn",
                 "BOM placeholder value %r on %s (set a real value/MPN)"
                 % (value or mpn, ref), [ref])
        elif not value and not mpn:
            _add(findings, "R29-bom-value", "warn",
                 "BOM value/MPN unknown for %s; procurement not verifiable" % ref,
                 [ref])


def rule_decoupling_count(snapshot, findings):
    """R30: one nearby decoupling cap per IC power pin (at least)."""
    nets = _nets(snapshot)
    for comp in _components(snapshot):
        if designator_kind(_ref(comp)) != "ic":
            continue
        power_pins = [pin for pin in _comp_pins(comp)
                      if str(pin.get("name") or "").upper() in POWER_PIN_NAMES]
        if not power_pins:
            continue
        center = _bbox_center(comp)
        if not center:
            _add(findings, "R30-decoupling-count", "warn",
                 "IC %s bbox unknown; decoupling count not verified (unknown)"
                 % _ref(comp), [_ref(comp)])
            continue
        power_nets = {_net_str(pin.get("net")) for pin in power_pins}
        power_nets = {n for n in power_nets if n and _is_power(n)}
        caps = set()
        for net in power_nets:
            for ref, _ in nets.get(net, set()):
                if designator_kind(ref) != "capacitor":
                    continue
                cap = _comp(snapshot, ref)
                cap_center = _bbox_center(cap) if cap else None
                if cap_center and _dist(center, cap_center) <= DECOUPLING_MAX_DIST \
                        and _cap_on_ground(cap):
                    caps.add(ref)
        if len(caps) < len(power_pins):
            _add(findings, "R30-decoupling-count", "warn",
                 "IC %s has %d power pin(s) but only %d nearby decoupling cap(s) "
                 "(need >= %d)" % (_ref(comp), len(power_pins), len(caps),
                                   len(power_pins)),
                 sorted({_ref(comp)} | caps))


# ---------------------------------------------------------------------------
# Rule registry: stable ids, single source of truth for review()
# ---------------------------------------------------------------------------

RULES = (
    {"id": "R01-floating-pin", "severity": "warn",
     "check": rule_floating_pins},
    {"id": "R02-i2c-pullup", "severity": "error",
     "check": rule_i2c_pullups},
    {"id": "R03-decoupling", "severity": "error",
     "check": rule_decoupling},
    {"id": "R04-ground-tie", "severity": "error",
     "check": rule_ground_tie},
    {"id": "R05-feedback-cap", "severity": "warn",
     "check": rule_feedback_after_cap},
    {"id": "R06-enable-net", "severity": "error",
     "check": rule_enable_pull},
    {"id": "R07-esd-series", "severity": "warn",
     "check": rule_esd_connector},
    {"id": "R08-power-testpoint", "severity": "warn",
     "check": rule_power_testpoint},
    {"id": "R09-auto-net-name", "severity": "warn",
     "check": rule_net_naming},
    {"id": "R10-titleblock", "severity": "warn",
     "check": rule_titleblock},
    {"id": "R11-bulk-ceramic", "severity": "warn",
     "check": rule_bulk_ceramic_per_rail},
    {"id": "R12-pol-cap-polarity", "severity": "warn",
     "check": rule_polarized_polarity},
    {"id": "R13-cap-derating", "severity": "warn",
     "check": rule_cap_voltage_derating},
    {"id": "R14-ldo-dropout", "severity": "warn",
     "check": rule_ldo_dropout},
    {"id": "R15-fb-divider", "severity": "warn",
     "check": rule_feedback_divider},
    {"id": "R16-xtal-load-cap", "severity": "warn",
     "check": rule_crystal_load_caps},
    {"id": "R17-reset-boot", "severity": "warn",
     "check": rule_reset_boot_tie},
    {"id": "R18-led-series", "severity": "warn",
     "check": rule_led_series_resistor},
    {"id": "R19-button", "severity": "warn",
     "check": rule_button_pullup_debounce},
    {"id": "R20-unused-nc", "severity": "warn",
     "check": rule_unused_pin_nc},
    {"id": "R21-usb-esd", "severity": "warn",
     "check": rule_usb_pair_esd},
    {"id": "R22-diff-pair-name", "severity": "warn",
     "check": rule_diff_pair_naming},
    {"id": "R23-spi-cs-pullup", "severity": "warn",
     "check": rule_spi_cs_pullup},
    {"id": "R24-i2c-address", "severity": "warn",
     "check": rule_i2c_address_strap},
    {"id": "R25-reverse-protection", "severity": "warn",
     "check": rule_connector_reverse_protection},
    {"id": "R26-input-fuse", "severity": "warn",
     "check": rule_input_fuse},
    {"id": "R27-connector-tvs", "severity": "warn",
     "check": rule_connector_tvs},
    {"id": "R28-cross-page", "severity": "warn",
     "check": rule_cross_page_nets},
    {"id": "R29-bom-value", "severity": "warn",
     "check": rule_bom_completeness},
    {"id": "R30-decoupling-count", "severity": "warn",
     "check": rule_decoupling_count},
)


def rule_ids():
    return [spec["id"] for spec in RULES]


def review(snapshot):
    findings = []
    for spec in RULES:
        spec["check"](snapshot, findings)
    errors = [f for f in findings if f["severity"] == "error"]
    return {
        "schema": REVIEW_SCHEMA,
        "verdict": "pass" if not errors else "blocked",
        "findings": findings,
        "metrics": {
            "errors": len(errors),
            "warnings": len(findings) - len(errors),
            "rules": sorted({f["rule"] for f in findings}),
            "rules_checked": len(RULES),
        },
    }
