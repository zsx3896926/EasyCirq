"""Block placement templates: extract relative part geometry, instantiate it.

A placement template freezes the measured relative layout of one block instance
(offsets from a semantic origin, rotations, relative part bboxes, and the net
topology) so later placements translate the *same* geometry to a new page
origin instead of letting an LLM invent coordinates.  Everything is offline and
pure data: no EDA call, no randomness.

Template document (``easycirq-block-template/v1``)::

    {"schema": "easycirq-block-template/v1",
     "block": "block.aw8737_classd_spk",
     "origin": {"role": "U", "ref": "U2", "x": 300.0, "y": 300.0},
     "parts": [{"role": "U", "designator": "U2", "dx": 0.0, "dy": 0.0,
                "rotation": 0,
                "bbox": {"minX": -8.0, "minY": -6.0,
                         "maxX": 8.0, "maxY": 6.0}}, ...],
     "pins": [{"role": "U", "pin": "INP", "net": "DAC_L_P"}, ...],
     "bbox": {"minX": -12.0, "minY": -10.0, "maxX": 240.0, "maxY": 160.0}}

* ``origin`` is the anchor part (first ``U`` role, else the first manifest
  role); ``dx``/``dy`` are part **bbox-center** offsets from that anchor.
* ``parts[].bbox`` is relative to the origin point (not absolute), so an
  instance is exactly ``bbox + origin_xy``.
* ``pins[].pin`` keeps the manifest token (a trailing ``*`` still means "all
  same-name pins of that role are on this net"), and ``net`` is the net name:
  a ``PORT:`` net resolves to the port's ``default_net`` (or the port name),
  while a purely internal net gets ``<block-id>_N<index>`` (1-based).
* Ports whose pin is not covered by any ``internal_nets`` entry get a
  single-pin net too (boundary pins can be block-local islands), mirroring
  ``easycirq sch block-apply``.

``instantiate_template(template, page, origin_xy)`` performs a pure
translation: part centres and bboxes move by ``origin_xy - (0, 0)`` relative to
the stored origin, net names and membership are copied verbatim, and the
``zone_union`` is the union of the absolute part bboxes.  The caller passes
``origin_xy`` as the absolute position of the template origin.

Both functions are deterministic: identical input documents produce identical
output documents (part/pin order follows the manifest, natural designator
order, no dict/set iteration leaks into output).

Public API
----------
``extract_template(block_id, manifest, snapshot, role_map)``
``instantiate_template(template, page, origin_xy)``
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

try:  # normal package import: from tools.layout2 import templates
    from . import role_resolver as _rr
except ImportError:  # pragma: no cover - defensive for direct execution
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.layout2 import role_resolver as _rr  # type: ignore[no-redef]

TEMPLATE_SCHEMA = "easycirq-block-template/v1"

__all__ = [
    "TEMPLATE_SCHEMA",
    "BlockTemplateError",
    "extract_template",
    "instantiate_template",
]


class BlockTemplateError(ValueError):
    """A block template cannot be extracted or instantiated from the input."""


def _fail(message: str) -> "BlockTemplateError":
    raise BlockTemplateError(message)


# ---------------------------------------------------------------------------
# rectangles
# ---------------------------------------------------------------------------


class _BBox(NamedTuple):
    minX: float
    minY: float
    maxX: float
    maxY: float

    @property
    def width(self) -> float:
        return self.maxX - self.minX

    @property
    def height(self) -> float:
        return self.maxY - self.minY

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.minX + self.maxX) / 2.0, (self.minY + self.maxY) / 2.0)

    def to_dict(self) -> Dict[str, Union[int, float]]:
        return {
            "minX": _rr._clean_number(self.minX),
            "minY": _rr._clean_number(self.minY),
            "maxX": _rr._clean_number(self.maxX),
            "maxY": _rr._clean_number(self.maxY),
        }


def _parse_bbox(value: Any, field: str, *, positive: bool = True) -> _BBox:
    try:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 4:
            numbers = [_rr._number(item, "%s[%d]" % (field, index)) for index, item in enumerate(value)]
            bbox = _BBox(*numbers)
        else:
            mapping = _rr._mapping(value, field)
            missing = [key for key in ("minX", "minY", "maxX", "maxY") if key not in mapping]
            if missing:
                _fail("%s: missing %s" % (field, ", ".join(missing)))
            bbox = _BBox(
                _rr._number(mapping["minX"], "%s.minX" % field),
                _rr._number(mapping["minY"], "%s.minY" % field),
                _rr._number(mapping["maxX"], "%s.maxX" % field),
                _rr._number(mapping["maxY"], "%s.maxY" % field),
            )
    except _rr.RoleResolutionError as exc:
        _fail(str(exc))
    if positive and (bbox.width <= 1e-9 or bbox.height <= 1e-9):
        _fail("%s: bbox must have positive width and height, got %s" % (field, bbox.to_dict()))
    return bbox


def _translate_bbox(bbox: _BBox, dx: float, dy: float) -> _BBox:
    return _BBox(bbox.minX + dx, bbox.minY + dy, bbox.maxX + dx, bbox.maxY + dy)


def _union_bboxes(bboxes: List[_BBox], field: str) -> _BBox:
    if not bboxes:
        _fail("%s: cannot take the union of zero bboxes" % field)
    return _BBox(
        min(bbox.minX for bbox in bboxes),
        min(bbox.minY for bbox in bboxes),
        max(bbox.maxX for bbox in bboxes),
        max(bbox.maxY for bbox in bboxes),
    )


def _origin_xy(value: Any, field: str) -> Tuple[float, float]:
    if isinstance(value, Mapping):
        return (
            _rr._number(value.get("x"), "%s.x" % field),
            _rr._number(value.get("y"), "%s.y" % field),
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 2:
        return (
            _rr._number(value[0], "%s[0]" % field),
            _rr._number(value[1], "%s[1]" % field),
        )
    _fail("%s: expected [x, y] or {\"x\": ..., \"y\": ...}, got %r" % (field, value))
    raise AssertionError("unreachable")


# ---------------------------------------------------------------------------
# role map and port helpers
# ---------------------------------------------------------------------------


def _validate_role_map(block_manifest_roles: Sequence[_rr._RoleSpec], role_map: Any) -> Dict[str, str]:
    mapping = _rr._mapping(role_map, "role_map")
    roles = [role_spec.role for role_spec in block_manifest_roles]
    missing = [role for role in roles if role not in mapping]
    extra = sorted((key for key in mapping.keys() if key not in roles), key=str)
    if missing:
        _fail("role_map: missing designator(s) for role(s) %s" % ", ".join(repr(role) for role in missing))
    if extra:
        _fail("role_map: unknown role(s) %s (manifest roles: %s)"
              % (", ".join(repr(role) for role in extra), ", ".join(roles)))
    designators: Dict[str, str] = {}
    for role in roles:
        designator = _rr._string(mapping[role], "role_map[%r]" % role).strip()
        designators[role] = designator
    if len(set(designators.values())) != len(designators):
        duplicates = sorted(
            designator for designator in set(designators.values())
            if list(designators.values()).count(designator) > 1
        )
        _fail("role_map: designator(s) %s bound to more than one role" % ", ".join(duplicates))
    return designators


def _port_default_net(ports: Mapping, port_name: str, field: str) -> str:
    port = ports.get(port_name)
    if port is None:
        return port_name
    port_map = _rr._mapping(port, "%s[%r]" % (field, port_name))
    default_net = port_map.get("default_net")
    if isinstance(default_net, str) and default_net.strip():
        return default_net.strip()
    return port_name


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


def extract_template(
    block_id: Any,
    manifest: Any,
    snapshot: Any,
    role_map: Any,
    *,
    origin_role: Optional[str] = None,
) -> Dict[str, Any]:
    """Freeze one block instance from a snapshot into a placement template.

    ``role_map`` is the ``{role: designator}`` mapping from
    :func:`tools.layout2.role_resolver.resolve_roles` (or a hand-checked one).
    ``origin_role`` overrides the default anchor (first ``U`` role, else the
    first manifest role).  Raises :class:`BlockTemplateError` for malformed
    manifests/snapshots or role maps.
    """
    try:
        return _extract_template_impl(
            block_id, manifest, snapshot, role_map, origin_role=origin_role
        )
    except _rr.RoleResolutionError as exc:
        raise BlockTemplateError(str(exc)) from exc


def _extract_template_impl(
    block_id: Any,
    manifest: Any,
    snapshot: Any,
    role_map: Any,
    *,
    origin_role: Optional[str] = None,
) -> Dict[str, Any]:
    block = _rr._string(block_id, "block_id").strip()
    manifest_map = _rr._mapping(manifest, "block_manifest")
    roles, nets = _rr._parse_manifest(manifest_map)
    components = _rr._parse_snapshot(snapshot)
    components_by_ref = {component.ref: component for component in components}
    designators = _validate_role_map(roles, role_map)

    # Every role must exist in the snapshot with a measured bbox.
    resolved: Dict[str, _rr._Component] = {}
    bboxes: Dict[str, _BBox] = {}
    for role_spec in roles:
        role = role_spec.role
        designator = designators[role]
        component = components_by_ref.get(designator)
        if component is None:
            _fail("role %r: designator %r is not present in snapshot.components" % (role, designator))
        resolved[role] = component
        bboxes[role] = _parse_bbox(
            component.raw.get("bbox"), "snapshot component %r bbox" % designator
        )

    role_names = [role_spec.role for role_spec in roles]
    if origin_role is None:
        origin_role = "U" if "U" in role_names else role_names[0]
    if origin_role not in role_names:
        _fail("origin_role %r is not a manifest role (roles: %s)" % (origin_role, ", ".join(role_names)))
    origin_x, origin_y = bboxes[origin_role].center

    parts: List[Dict[str, Any]] = []
    for role in role_names:
        component = resolved[role]
        center_x, center_y = bboxes[role].center
        parts.append(
            {
                "role": role,
                "designator": designators[role],
                "dx": _rr._clean_number(center_x - origin_x),
                "dy": _rr._clean_number(center_y - origin_y),
                "rotation": _rr._rotation(component),
                "bbox": _translate_bbox(bboxes[role], -origin_x, -origin_y).to_dict(),
            }
        )

    # -- nets / pins --------------------------------------------------------
    ports = manifest_map.get("ports") or {}
    ports = _rr._mapping(ports, "block_manifest.ports")
    pin_entries: List[Dict[str, str]] = []
    net_of_pin: Dict[Tuple[str, str], str] = {}

    def add_pin(role: str, raw_pin: str, net_name: str) -> None:
        if role not in resolved:
            _fail("net member role %r is not part of the role map" % role)
        member = _rr._PinRef("%s.%s" % (role, raw_pin), role, _star_stripped(raw_pin), raw_pin, False)
        if _rr._match_pin(resolved[role], member) is None:
            _fail(
                "pin ref %r: component %r has no matching pin"
                % (member.token, designators[role])
            )
        key = (role, raw_pin)
        previous = net_of_pin.get(key)
        if previous is not None and previous != net_name:
            _fail(
                "pin %s.%s appears on two nets (%r and %r)"
                % (role, raw_pin, previous, net_name)
            )
        if previous is not None:
            return
        net_of_pin[key] = net_name
        pin_entries.append({"role": role, "pin": raw_pin, "net": net_name})

    for index, net in enumerate(nets, start=1):
        port_name = next((member.token[len("PORT:"):] for member in net if member.is_port), None)
        pin_members = [member for member in net if not member.is_port]
        if not pin_members:
            _fail(
                "block_manifest.internal_nets[%d]: no pin members (only PORT markers)"
                % (index - 1)
            )
        if port_name is not None:
            net_name = _port_default_net(ports, port_name, "block_manifest.ports")
        else:
            net_name = "%s_N%d" % (block, index)
        for member in pin_members:
            assert member.role is not None and member.raw_pin is not None
            add_pin(member.role, member.raw_pin, net_name)

    # Ports whose at-pin is not covered by any internal net still need a net
    # (a boundary port may point at a block-local island pin).  Mirrors
    # `easycirq sch block-apply` so the template never drops a block pin.
    covered_ports = {
        member.token[len("PORT:"):] for net in nets for member in net if member.is_port
    }
    for port_name in sorted(ports.keys()):
        if port_name in covered_ports:
            continue
        port_map = _rr._mapping(ports[port_name], "block_manifest.ports[%r]" % port_name)
        at = _rr._string(port_map.get("at"), "block_manifest.ports[%r].at" % port_name).strip()
        member = _rr._parse_pin_ref(at, "block_manifest.ports[%r].at" % port_name)
        if member.is_port or member.role is None or member.raw_pin is None:
            _fail("block_manifest.ports[%r].at: expected ROLE.PIN, got %r" % (port_name, at))
        add_pin(
            member.role,
            member.raw_pin,
            _port_default_net(ports, port_name, "block_manifest.ports"),
        )

    relative_bboxes = [_parse_bbox(part["bbox"], "parts[%r].bbox" % part["role"]) for part in parts]
    return {
        "schema": TEMPLATE_SCHEMA,
        "block": block,
        "origin": {
            "role": origin_role,
            "ref": designators[origin_role],
            "x": _rr._clean_number(origin_x),
            "y": _rr._clean_number(origin_y),
        },
        "parts": parts,
        "pins": pin_entries,
        "bbox": _union_bboxes(relative_bboxes, "template bbox").to_dict(),
    }


def _star_stripped(raw_pin: str) -> str:
    base = raw_pin[:-1].strip() if raw_pin.endswith("*") else raw_pin
    return base


# ---------------------------------------------------------------------------
# instantiate
# ---------------------------------------------------------------------------


def _validate_template(template: Any) -> Mapping:
    data = _rr._mapping(template, "template")
    allowed = {"schema", "block", "origin", "parts", "pins", "bbox"}
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        _fail("template: unknown field(s) %s" % ", ".join(repr(key) for key in unknown))
    schema = data.get("schema")
    if schema is not None and schema != TEMPLATE_SCHEMA:
        _fail("template.schema: expected %r, got %r" % (TEMPLATE_SCHEMA, schema))
    _rr._string(data.get("block"), "template.block")
    origin = _rr._mapping(data.get("origin"), "template.origin")
    _rr._string(origin.get("role"), "template.origin.role")
    _rr._string(origin.get("ref"), "template.origin.ref")
    _rr._number(origin.get("x"), "template.origin.x")
    _rr._number(origin.get("y"), "template.origin.y")
    parts = data.get("parts")
    if not isinstance(parts, Sequence) or isinstance(parts, (str, bytes)) or not parts:
        _fail("template.parts: expected a non-empty list")
    roles = set()
    designators = set()
    for index, raw_part in enumerate(parts):
        field = "template.parts[%d]" % index
        part = _rr._mapping(raw_part, field)
        part_unknown = sorted(set(part.keys()) - {"role", "designator", "dx", "dy", "rotation", "bbox"})
        if part_unknown:
            _fail("%s: unknown field(s) %s" % (field, ", ".join(repr(key) for key in part_unknown)))
        role = _rr._string(part.get("role"), "%s.role" % field)
        designator = _rr._string(part.get("designator"), "%s.designator" % field)
        if role in roles:
            _fail("%s: duplicate role %r" % (field, role))
        if designator in designators:
            _fail("%s: duplicate designator %r" % (field, designator))
        roles.add(role)
        designators.add(designator)
        _rr._number(part.get("dx"), "%s.dx" % field)
        _rr._number(part.get("dy"), "%s.dy" % field)
        rotation = part.get("rotation")
        if rotation is not None:
            _rr._number(rotation, "%s.rotation" % field)
        _parse_bbox(part.get("bbox"), "%s.bbox" % field)
    pins = data.get("pins")
    if not isinstance(pins, Sequence) or isinstance(pins, (str, bytes)):
        _fail("template.pins: expected a list")
    for index, raw_pin in enumerate(pins):
        field = "template.pins[%d]" % index
        pin = _rr._mapping(raw_pin, field)
        pin_unknown = sorted(set(pin.keys()) - {"role", "pin", "net"})
        if pin_unknown:
            _fail("%s: unknown field(s) %s" % (field, ", ".join(repr(key) for key in pin_unknown)))
        role = _rr._string(pin.get("role"), "%s.role" % field)
        if role not in roles:
            _fail("%s: role %r is not in template.parts" % (field, role))
        _rr._string(pin.get("pin"), "%s.pin" % field)
        _rr._string(pin.get("net"), "%s.net" % field)
    _parse_bbox(data.get("bbox"), "template.bbox")
    return data


def instantiate_template(template: Any, page: Any, origin_xy: Any) -> Dict[str, Any]:
    """Translate a template to ``origin_xy`` and return absolute geometry + nets.

    ``page`` is carried through to the result as ``"page"`` (page id / plan
    slot, opaque here); ``origin_xy`` is the absolute position of the template
    origin as ``[x, y]`` or ``{"x": ..., "y": ...}``.  Raises
    :class:`BlockTemplateError` for a malformed template or origin.
    """
    try:
        return _instantiate_template_impl(template, page, origin_xy)
    except _rr.RoleResolutionError as exc:
        raise BlockTemplateError(str(exc)) from exc


def _instantiate_template_impl(template: Any, page: Any, origin_xy: Any) -> Dict[str, Any]:
    data = _validate_template(template)
    origin_x, origin_y = _origin_xy(origin_xy, "origin_xy")

    absolute_parts: List[Dict[str, Any]] = []
    designator_by_role: Dict[str, str] = {}
    part_bboxes: List[_BBox] = []
    for raw_part in data["parts"]:
        role = raw_part["role"]
        designator = raw_part["designator"]
        dx = _rr._number(raw_part.get("dx"), "template part %r.dx" % role)
        dy = _rr._number(raw_part.get("dy"), "template part %r.dy" % role)
        rotation = raw_part.get("rotation")
        rotation = 0 if rotation is None else _rr._number(rotation, "template part %r.rotation" % role)
        relative_bbox = _parse_bbox(raw_part.get("bbox"), "template part %r.bbox" % role)
        absolute_bbox = _translate_bbox(relative_bbox, origin_x, origin_y)
        part_bboxes.append(absolute_bbox)
        designator_by_role[role] = designator
        absolute_parts.append(
            {
                "ref": designator,
                "role": role,
                "x": _rr._clean_number(origin_x + dx),
                "y": _rr._clean_number(origin_y + dy),
                "rotation": _rr._clean_number(rotation),
                "bbox": absolute_bbox.to_dict(),
            }
        )

    nets: List[Dict[str, Any]] = []
    net_members: Dict[str, List[List[str]]] = {}
    for raw_pin in data["pins"]:
        role = raw_pin["role"]
        pin = raw_pin["pin"]
        net = raw_pin["net"]
        designator = designator_by_role.get(role)
        if designator is None:  # pragma: no cover - _validate_template already checks
            _fail("template.pins: role %r is not in template.parts" % role)
        if net not in net_members:
            net_members[net] = []
            nets.append({"name": net, "members": net_members[net]})
        net_members[net].append([designator, pin])

    return {
        "page": page,
        "parts": absolute_parts,
        "nets": nets,
        "zone_union": _union_bboxes(part_bboxes, "zone_union").to_dict(),
    }
