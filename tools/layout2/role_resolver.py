"""Deterministic role -> designator resolver for EasyCirq block manifests.

Placement drift comes from free-form LLM guesses about which existing part is
"the U" or "the 22uF cap #2".  This module binds a block manifest's semantic
roles to the designators already present in an ACE snapshot, using only data:
MPNs from the resolved standard-parts table plus the block's internal net
topology.  The search is a deterministic backtracking 1-1 assignment; no LLM
and no EDA call is involved.

Inputs
------
``block_manifest``
    ``easycirq blocks show <block-id>`` JSON.  Only ``parts`` and
    ``internal_nets`` are used (plus ``id`` for error messages):

    * ``parts``: ``{role: {"part": "<standard-parts key>", "qty": 1, ...}}``
    * ``internal_nets``: list of nets, each a list of ``"ROLE.PIN"`` members
      and/or ``"PORT:NAME"`` boundary markers.  A trailing ``*`` on a pin means
      "every same-name pin of that role is on this net" (parallel pads); it is
      stripped for pin lookup.

``snapshot``
    ``easycirq-ace-snapshot/v1`` JSON captured by ``tools/ace_snapshot.py``:
    ``components[].ref`` + ``components[].mpn`` + ``components[].pins[]`` where
    each pin is ``{"number", "name", "net"}``.

``resolved_parts_path``
    Optional path to ``standard-parts.resolved.json`` (the file the demo
    artifacts provide).  Its ``parts`` object maps a standard-parts key to
    ``{"mpn": "<manufacturer part number>", ...}``.  When omitted, the manifest
    part key itself is treated as the MPN (or a snapshot ``value``) for
    candidate matching.

Resolution rules
----------------
1. **Candidates by MPN**: a role whose manifest part key maps to MPN ``M`` can
   bind to any snapshot component whose ``mpn`` is ``M`` (or, without a
   resolved table, whose ``mpn``/``value`` equals the part key).
2. **Prune by net topology**: for every ``internal_nets`` net with at least two
   non-``PORT`` members, all matched snapshot pins must sit on one and the same
   snapshot net.  ``PORT:`` members are boundary markers and are ignored here.
   Every referenced pin must exist on the candidate component, and a pin may
   not resolve to two different nets.
3. **Search**: deterministic MRV backtracking assigns each role one distinct
   designator.  Candidate order is role order (manifest order) and natural
   designator order, so identical inputs always produce the identical mapping.

Errors (all :class:`RoleResolutionError`, a ``ValueError``) are explicit:
unknown MPN (no candidate), missing resolved part key, inconsistent topology
(no assignment), and genuine ambiguity (two-plus valid assignments) — the
resolver never silently picks one of several equally valid bindings.

Public API
----------
``resolve_roles(block_manifest, snapshot, resolved_parts_path=None) -> {role: designator}``
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple, Union

SNAPSHOT_SCHEMA = "easycirq-ace-snapshot/v1"

#: Cap on how many complete solutions are enumerated (we only need to know
#: whether a second one exists; two is enough for the ambiguity error).
_MAX_SOLUTIONS = 2

__all__ = [
    "SNAPSHOT_SCHEMA",
    "RoleResolutionError",
    "resolve_roles",
]


class RoleResolutionError(ValueError):
    """The block roles cannot be bound to snapshot designators."""


# ---------------------------------------------------------------------------
# generic validation helpers
# ---------------------------------------------------------------------------


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _number(value: Any, field: str) -> float:
    if not _is_number(value):
        raise RoleResolutionError("%s: expected a finite number, got %r" % (field, value))
    return float(value)


def _mapping(value: Any, field: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise RoleResolutionError("%s: expected an object, got %r" % (field, type(value).__name__))
    return value


def _string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise RoleResolutionError("%s: expected a string, got %r" % (field, type(value).__name__))
    if not allow_empty and not value.strip():
        raise RoleResolutionError("%s: must not be empty" % field)
    return value


def _optional_string(value: Any, field: str) -> Optional[str]:
    if value is None:
        return None
    return _string(value, field)


def _natural_key(text: str) -> Tuple[Tuple[int, Any], ...]:
    """Sort ``C2`` before ``C10`` (and keep ties fully ordered)."""
    chunks = re.split(r"(\d+)", text)
    key: List[Tuple[int, Any]] = []
    for chunk in chunks:
        if chunk.isdigit():
            key.append((0, int(chunk)))
        else:
            key.append((1, chunk.lower()))
    return tuple(key)


def _clean_number(value: float) -> Union[int, float]:
    number = float(value)
    if number.is_integer():
        return int(number)
    return number


# ---------------------------------------------------------------------------
# block manifest
# ---------------------------------------------------------------------------


class _PinRef(NamedTuple):
    """One parsed ``internal_nets`` member."""

    token: str
    role: Optional[str]
    pin: Optional[str]  # stripped of the trailing '*' convention marker
    raw_pin: Optional[str]  # exactly as declared (may end with '*')
    is_port: bool


class _RoleSpec(NamedTuple):
    role: str
    part_key: str
    explicit_mpn: Optional[str]


def _parse_pin_ref(token: Any, field: str) -> _PinRef:
    text = _string(token, field).strip()
    if text.startswith("PORT:"):
        port = text[len("PORT:"):].strip()
        if not port:
            raise RoleResolutionError("%s: PORT marker needs a port name: %r" % (field, token))
        return _PinRef(text, None, None, None, True)
    role, dot, raw_pin = text.partition(".")
    role = role.strip()
    raw_pin = raw_pin.strip()
    if not dot or not role or not raw_pin:
        raise RoleResolutionError(
            "%s: bad pin ref %r (expected ROLE.PIN or PORT:NAME)" % (field, token)
        )
    base = raw_pin[:-1].strip() if raw_pin.endswith("*") else raw_pin
    if not base:
        raise RoleResolutionError("%s: pin ref %r has no pin name after '*'" % (field, token))
    return _PinRef(text, role, base, raw_pin, False)


def _parse_manifest(block_manifest: Any) -> Tuple[Tuple[_RoleSpec, ...], Tuple[Tuple[_PinRef, ...], ...]]:
    """Validate the manifest and return ``(roles, internal_nets)``."""
    manifest = _mapping(block_manifest, "block_manifest")
    parts = _mapping(manifest.get("parts"), "block_manifest.parts")
    if not parts:
        raise RoleResolutionError("block_manifest.parts: must not be empty")
    roles: List[_RoleSpec] = []
    for role, spec in parts.items():
        role_name = _string(role, "block_manifest.parts key")
        field = "block_manifest.parts[%r]" % role_name
        spec_map = _mapping(spec, field)
        part_key = _string(spec_map.get("part"), "%s.part" % field)
        qty = spec_map.get("qty", 1)
        if isinstance(qty, bool) or not isinstance(qty, int) or qty != 1:
            raise RoleResolutionError(
                "%s.qty: 1-1 role resolution requires exactly 1 per role, got %r "
                "(split repeated parts into distinct roles)" % (field, qty)
            )
        explicit_mpn = _optional_string(spec_map.get("mpn"), "%s.mpn" % field)
        roles.append(_RoleSpec(role_name, part_key, explicit_mpn))

    raw_nets = manifest.get("internal_nets")
    if not isinstance(raw_nets, (list, tuple)):
        raise RoleResolutionError(
            "block_manifest.internal_nets: expected a list, got %r" % (type(raw_nets).__name__,)
        )
    known_roles = {role.role for role in roles}
    nets: List[Tuple[_PinRef, ...]] = []
    for index, raw_net in enumerate(raw_nets):
        field = "block_manifest.internal_nets[%d]" % index
        if not isinstance(raw_net, (list, tuple)) or not raw_net:
            raise RoleResolutionError("%s: expected a non-empty list of members" % field)
        members: List[_PinRef] = []
        for member_index, token in enumerate(raw_net):
            member = _parse_pin_ref(token, "%s[%d]" % (field, member_index))
            if member.role is not None and member.role not in known_roles:
                raise RoleResolutionError(
                    "%s[%d]: unknown role %r (manifest roles: %s)"
                    % (field, member_index, member.role, ", ".join(role.role for role in roles))
                )
            members.append(member)
        nets.append(tuple(members))
    return tuple(roles), tuple(nets)


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------


class _Pin(NamedTuple):
    number: Optional[str]
    name: Optional[str]
    net: Optional[str]


class _Component(NamedTuple):
    ref: str
    mpn: Optional[str]
    value: Optional[str]
    pins: Tuple[_Pin, ...]
    raw: Mapping


def _parse_snapshot(snapshot: Any) -> Tuple[_Component, ...]:
    data = _mapping(snapshot, "snapshot")
    schema = data.get("schema")
    if schema != SNAPSHOT_SCHEMA:
        raise RoleResolutionError(
            "snapshot.schema: expected %r, got %r" % (SNAPSHOT_SCHEMA, schema)
        )
    components = data.get("components")
    if not isinstance(components, (list, tuple)) or not components:
        raise RoleResolutionError("snapshot.components: expected a non-empty list")
    parsed: List[_Component] = []
    seen_refs = set()
    for index, raw in enumerate(components):
        field = "snapshot.components[%d]" % index
        component = _mapping(raw, field)
        ref = _string(component.get("ref"), "%s.ref" % field)
        if ref in seen_refs:
            raise RoleResolutionError("snapshot.components: duplicate ref %r" % ref)
        seen_refs.add(ref)
        raw_pins = component.get("pins") or []
        if not isinstance(raw_pins, (list, tuple)):
            raise RoleResolutionError("%s.pins: expected a list" % field)
        pins: List[_Pin] = []
        for pin_index, raw_pin in enumerate(raw_pins):
            pin_field = "%s.pins[%d]" % (field, pin_index)
            pin_map = _mapping(raw_pin, pin_field)
            number = pin_map.get("number")
            name = pin_map.get("name")
            net = pin_map.get("net")
            if number is None and name is None:
                raise RoleResolutionError("%s: pin needs a number or a name" % pin_field)
            pins.append(
                _Pin(
                    None if number is None else str(number),
                    None if name is None else str(name),
                    None if net is None else str(net),
                )
            )
        parsed.append(
            _Component(
                ref,
                _optional_string(component.get("mpn"), "%s.mpn" % field),
                _optional_string(component.get("value"), "%s.value" % field),
                tuple(pins),
                component,
            )
        )
    return tuple(parsed)


def _match_pin(component: _Component, member: _PinRef) -> Optional[Tuple[_Pin, ...]]:
    """Resolve a manifest pin ref against one snapshot component.

    * non-star ref: exactly one pin, matched by number first then name;
      several same-name matches are ambiguous and raise;
    * star ref (``VDD*``): every same-name pin (plus exact-number hits) is
      returned — "all parallel pads are on this net".
    """
    assert member.pin is not None
    token = member.pin
    star = bool(member.raw_pin and member.raw_pin.endswith("*"))
    by_number = [pin for pin in component.pins if pin.number == token]
    by_name = [
        pin for pin in component.pins
        if pin.name is not None and pin.name.strip().lower() == token.strip().lower()
    ]
    if star:
        hits: List[_Pin] = []
        for pin in by_name + by_number:
            if pin not in hits:
                hits.append(pin)
        return tuple(hits) if hits else None
    hits = by_number if by_number else by_name
    if len(hits) == 1:
        return (hits[0],)
    if len(hits) > 1:
        raise RoleResolutionError(
            "pin ref %r matches %d pins on component %r; use a trailing '*' "
            "to mean all same-name pins" % (member.raw_pin or member.token, len(hits), component.ref)
        )
    return None


def _rotation(component: _Component) -> Union[int, float]:
    raw = component.raw
    for key in ("rotation", "angle", "rot"):
        if key in raw and raw[key] is not None:
            return _clean_number(_number(raw[key], "snapshot component %r.%s" % (component.ref, key)))
    return 0


# ---------------------------------------------------------------------------
# resolved standard parts
# ---------------------------------------------------------------------------


def _load_resolved_parts(path: Union[str, Path]) -> Dict[str, Optional[str]]:
    resolved_path = Path(path)
    try:
        text = resolved_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RoleResolutionError(
            "cannot read resolved parts file %s: %s" % (resolved_path, exc)
        ) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RoleResolutionError(
            "%s: invalid JSON at line %s column %s: %s"
            % (resolved_path, exc.lineno, exc.colno, exc.msg)
        ) from exc
    document = _mapping(data, "resolved parts file %s" % resolved_path)
    parts = _mapping(
        document.get("parts"), "resolved parts file %s: parts" % resolved_path
    )
    table: Dict[str, Optional[str]] = {}
    for key, entry in parts.items():
        part_key = _string(key, "resolved parts key")
        entry_map = _mapping(entry, "resolved parts[%r]" % part_key)
        mpn = entry_map.get("mpn")
        if mpn is None:
            # The shipped standard-parts.resolved.json still has rows whose
            # MPN lookup did not resolve; they are only fatal when a block
            # actually needs them (see resolve_roles).
            table[part_key] = None
        else:
            table[part_key] = _string(mpn, "resolved parts[%r].mpn" % part_key).strip()
    return table


# ---------------------------------------------------------------------------
# resolver
# ---------------------------------------------------------------------------


def _candidate_refs(
    expected_mpn: str,
    components: Sequence[_Component],
    *,
    match_value: bool,
) -> List[str]:
    expected = expected_mpn.strip()
    refs: List[str] = []
    for component in components:
        if component.mpn is not None and component.mpn.strip() == expected:
            refs.append(component.ref)
        elif match_value and component.value is not None and component.value.strip() == expected:
            refs.append(component.ref)
    return sorted(refs, key=_natural_key)


def _block_label(block_manifest: Mapping) -> str:
    block_id = block_manifest.get("id")
    if isinstance(block_id, str) and block_id.strip():
        return block_id.strip()
    return "<block>"


def resolve_roles(
    block_manifest: Any,
    snapshot: Any,
    resolved_parts_path: Optional[Union[str, Path]] = None,
) -> Dict[str, str]:
    """Bind every manifest role to exactly one snapshot designator.

    Returns ``{role: designator}`` in manifest role order.  Raises
    :class:`RoleResolutionError` when a role has no MPN candidate, the net
    topology is inconsistent, the input JSON is malformed, or the mapping is
    ambiguous (more than one 1-1 assignment satisfies MPN + topology).
    """
    manifest = _mapping(block_manifest, "block_manifest")
    roles, nets = _parse_manifest(manifest)
    components = _parse_snapshot(snapshot)
    label = _block_label(manifest)

    resolved_table: Optional[Dict[str, Optional[str]]] = None
    if resolved_parts_path is not None:
        resolved_table = _load_resolved_parts(resolved_parts_path)

    components_by_ref = {component.ref: component for component in components}

    # -- candidates per role (MPN only; independent of topology) ------------
    candidates: Dict[str, List[str]] = {}
    for role_spec in roles:
        role = role_spec.role
        if role_spec.explicit_mpn is not None:
            expected_mpn = role_spec.explicit_mpn
            match_value = False
        elif resolved_table is not None:
            if role_spec.part_key not in resolved_table:
                raise RoleResolutionError(
                    "%s: role %r part key %r is missing from the resolved parts "
                    "file; cannot match an MPN"
                    % (label, role, role_spec.part_key)
                )
            expected_mpn = resolved_table[role_spec.part_key]
            if expected_mpn is None:
                raise RoleResolutionError(
                    "%s: role %r part key %r has no resolved MPN in the resolved "
                    "parts file (unresolved row); resolve the part before placing "
                    "the block" % (label, role, role_spec.part_key)
                )
            match_value = False
        else:
            expected_mpn = role_spec.part_key
            match_value = True
        refs = _candidate_refs(expected_mpn, components, match_value=match_value)
        if not refs:
            raise RoleResolutionError(
                "%s: role %r has no snapshot candidate for MPN %r (part key %r); "
                "snapshot has %d components"
                % (label, role, expected_mpn, role_spec.part_key, len(components))
            )
        candidates[role] = refs

    # -- topology model -----------------------------------------------------
    role_names = [role_spec.role for role_spec in roles]
    members_by_role: Dict[str, List[_PinRef]] = {role: [] for role in role_names}
    for net in nets:
        for member in net:
            if member.role is not None:
                members_by_role[member.role].append(member)
    joint_nets = [tuple(member for member in net if not member.is_port) for net in nets]
    joint_nets = [net for net in joint_nets if len(net) >= 2]

    pin_cache: Dict[Tuple[str, str], Optional[Tuple[_Pin, ...]]] = {}

    def pin_matches(role: str, ref: str, member: _PinRef) -> Optional[Tuple[_Pin, ...]]:
        key = (ref, member.token)
        if key not in pin_cache:
            pin_cache[key] = _match_pin(components_by_ref[ref], member)
        return pin_cache[key]

    def candidate_is_valid(role: str, ref: str) -> bool:
        for member in members_by_role[role]:
            if pin_matches(role, ref, member) is None:
                return False
        return True

    usable: Dict[str, List[str]] = {}
    for role in role_names:
        usable[role] = [ref for ref in candidates[role] if candidate_is_valid(role, ref)]
        if not usable[role]:
            raise RoleResolutionError(
                "%s: role %r has MPN candidates %s but none exposes the pins "
                "required by internal_nets (%s)"
                % (
                    label,
                    role,
                    candidates[role],
                    ", ".join(sorted({member.token for member in members_by_role[role]})),
                )
            )

    def nets_consistent(assignment: Mapping[str, str]) -> bool:
        for net in joint_nets:
            if any(member.role not in assignment for member in net):
                continue  # wait until the whole net is bound
            common_net: Optional[str] = None
            for member in net:
                matches = pin_matches(member.role, assignment[member.role], member)
                if not matches:
                    return False
                net_names = {pin.net for pin in matches}
                if len(net_names) != 1:
                    return False
                net_name = next(iter(net_names))
                if net_name is None:
                    return False
                if common_net is None:
                    common_net = net_name
                elif common_net != net_name:
                    return False
        return True

    # -- deterministic MRV backtracking ------------------------------------
    solutions: List[Dict[str, str]] = []
    assignment: Dict[str, str] = {}
    used_designators: set = set()

    def search() -> None:
        if len(solutions) >= _MAX_SOLUTIONS:
            return
        if len(assignment) == len(role_names):
            solutions.append(dict(assignment))
            return
        best_role: Optional[str] = None
        best_domain: Optional[List[str]] = None
        for role in role_names:
            if role in assignment:
                continue
            domain = [ref for ref in usable[role] if ref not in used_designators]
            if best_domain is None or len(domain) < len(best_domain):
                best_role = role
                best_domain = domain
                if not domain:
                    break
        if best_role is None or not best_domain:
            return
        for ref in best_domain:
            assignment[best_role] = ref
            used_designators.add(ref)
            if nets_consistent(assignment):
                search()
            used_designators.discard(ref)
            del assignment[best_role]
            if len(solutions) >= _MAX_SOLUTIONS:
                return

    search()

    if not solutions:
        summary = "; ".join(
            "%s=%s" % (role, candidates[role]) for role in role_names
        )
        raise RoleResolutionError(
            "%s: no 1-1 role->designator assignment satisfies MPN + internal_nets "
            "topology (candidates: %s)" % (label, summary)
        )
    if len(solutions) > 1:
        first, second = solutions[0], solutions[1]
        differing = [role for role in role_names if first[role] != second[role]]
        detail = ", ".join(
            "%r -> %r vs %r" % (role, first[role], second[role]) for role in differing[:4]
        )
        raise RoleResolutionError(
            "%s: ambiguous role assignment: %d+ consistent 1-1 mappings exist "
            "(%s); add distinguishing internal_nets or bind roles explicitly"
            % (label, len(solutions), detail)
        )
    solution = solutions[0]
    return {role: solution[role] for role in role_names}
