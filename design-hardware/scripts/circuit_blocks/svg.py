"""Analysis-only SVG rendering.

The SVG is a readable projection of the *connectivity table* — component boxes
and net rows.  It deliberately contains no schematic coordinates, no library
symbols and no wire routing, so nobody can mistake it for an EDA schematic or a
manufacturable drawing.  The connection source of truth stays the JSON
``connectivity`` section.
"""
from __future__ import annotations

from fractions import Fraction
from html import escape

DISCLAIMER = ('ANALYSIS VIEW ONLY - generated from the abstract connectivity contract. '
              'Not an EDA schematic, not library symbol geometry, not a manufacturable drawing.')

_FONT = 'font-family="Consolas, Menlo, monospace"'


def _fmt(value, unit):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value)
    return '%s%s' % (text, unit or '')


def result_svg(result, *, width=980):
    """Render a module result as an analysis SVG string."""
    components = result.get('components') or []
    nets = (result.get('connectivity') or {}).get('nets') or []
    connections = (result.get('connectivity') or {}).get('connections') or []
    ports = result.get('ports') or []
    by_net = {}
    for connection in connections:
        if connection.get('state') == 'connected':
            by_net.setdefault(connection['net'], []).append(
                '%s.%s' % (connection['component'], connection['pin']))
    row_height = 22
    top = 76
    component_height = 26 + len(components) * row_height
    net_height = 26 + len(nets) * row_height
    port_height = 26 + len(ports) * row_height
    height = top + component_height + 18 + net_height + 18 + port_height + 54
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
        % (width, height, width, height),
        '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (width, height),
        '<text x="16" y="28" %s font-size="18" font-weight="bold">%s - analysis view</text>'
        % (_FONT, escape('%s [%s]' % (result.get('module_type', '?'), result.get('instance_id', '?')))),
        '<text x="16" y="48" %s font-size="12" fill="#444">status: %s   content: %s</text>'
        % (_FONT, escape(str(result.get('status'))), escape(str(result.get('content_hash')))),
    ]
    y = top
    parts.append(_section('#f2f6fb', 12, y - 18, width - 24, component_height, 'components (abstract roles, no bound parts)'))
    y += 10
    for component in components:
        value = component.get('value') or {}
        label = '%s  %s  %s' % (component.get('ref'), component.get('role'),
                                _fmt(value.get('value'), value.get('unit')))
        parts.append('<text x="24" y="%d" %s font-size="13">%s</text>' % (y, _FONT, escape(label)))
        parts.append('<text x="560" y="%d" %s font-size="12" fill="#666">%s</text>'
                     % (y, _FONT, escape('binding=%s' % component.get('binding'))))
        y += row_height
    y += 18
    parts.append(_section('#f7f2fb', 12, y - 18, width - 24, net_height, 'nets and endpoints'))
    y += 10
    for net in nets:
        endpoints = ', '.join(by_net.get(net['id'], [])) or '(no connected endpoint)'
        parts.append('<text x="24" y="%d" %s font-size="13">%s [%s] %s</text>'
                     % (y, _FONT, escape(net['name']), escape(net.get('role') or ''),
                        escape(endpoints)))
        y += row_height
    y += 18
    parts.append(_section('#f2fbf4', 12, y - 18, width - 24, port_height, 'external ports'))
    y += 10
    for port in ports:
        parts.append('<text x="24" y="%d" %s font-size="13">%s  %s/%s  net=%s</text>'
                     % (y, _FONT, escape(port['id']), escape(port['direction']),
                        escape(port['role']), escape(str(port.get('net')))))
        y += row_height
    parts.append('<text x="16" y="%d" %s font-size="11" fill="#a00">%s</text>'
                 % (height - 22, _FONT, escape(DISCLAIMER)))
    parts.append('</svg>')
    return '\n'.join(parts) + '\n'


def design_svg(design, *, width=980):
    """Render a composed design as an analysis SVG string."""
    blocks = design.get('blocks') or []
    nets = design.get('nets') or []
    ports = design.get('ports') or []
    connections = design.get('connections') or []
    row_height = 22
    top = 76
    block_height = 26 + len(blocks) * row_height
    net_height = 26 + max(len(nets), 1) * row_height
    port_height = 26 + max(len(ports), 1) * row_height
    conn_height = 26 + max(len(connections), 1) * row_height
    height = top + block_height + 18 + net_height + 18 + port_height + 18 + conn_height + 54
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
        % (width, height, width, height),
        '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (width, height),
        '<text x="16" y="28" %s font-size="18" font-weight="bold">%s - analysis view</text>'
        % (_FONT, escape('%s (composed design)' % design.get('design_name', '?'))),
        '<text x="16" y="48" %s font-size="12" fill="#444">status: %s   content: %s</text>'
        % (_FONT, escape(str(design.get('status'))), escape(str(design.get('content_hash')))),
    ]
    y = top
    parts.append(_section('#f2f6fb', 12, y - 18, width - 24, block_height, 'module instances'))
    y += 10
    for block in blocks:
        parts.append('<text x="24" y="%d" %s font-size="13">%s  %s  -> %s</text>'
                     % (y, _FONT, escape(str(block.get('instance_id'))),
                        escape(str(block.get('module_type'))), escape(str(block.get('status')))))
        y += row_height
    y += 18
    parts.append(_section('#f7f2fb', 12, y - 18, width - 24, net_height, 'design nets'))
    y += 10
    for net in nets or [{'id': '(none)', 'name': ''}]:
        parts.append('<text x="24" y="%d" %s font-size="13">%s</text>'
                     % (y, _FONT, escape(str(net.get('id')))))
        y += row_height
    y += 18
    parts.append(_section('#f2fbf4', 12, y - 18, width - 24, port_height, 'design ports'))
    y += 10
    for port in ports or [{'id': '(none)', 'direction': '', 'role': '', 'net': ''}]:
        parts.append('<text x="24" y="%d" %s font-size="13">%s  %s/%s  net=%s</text>'
                     % (y, _FONT, escape(str(port.get('id'))), escape(str(port.get('direction'))),
                        escape(str(port.get('role'))), escape(str(port.get('net')))))
        y += row_height
    y += 18
    parts.append(_section('#fdf7f2', 12, y - 18, width - 24, conn_height, 'declared connections'))
    y += 10
    for connection in connections or [{'a': '', 'b': ''}]:
        a, b = connection.get('a'), connection.get('b')
        parts.append('<text x="24" y="%d" %s font-size="13">%s  &lt;-&gt;  %s</text>'
                     % (y, _FONT, escape(str(a)), escape(str(b))))
        y += row_height
    parts.append('<text x="16" y="%d" %s font-size="11" fill="#a00">%s</text>'
                 % (height - 22, _FONT, escape(DISCLAIMER)))
    parts.append('</svg>')
    return '\n'.join(parts) + '\n'


def _section(fill, x, y, width, height, title):
    return ('<g><rect x="%d" y="%d" width="%d" height="%d" fill="%s" stroke="#d0d7e2"/>'
            '<text x="%d" y="%d" font-size="12" font-weight="bold" fill="#334">%s</text></g>'
            % (x, y, width, height, fill, x + 8, y + 16, escape(title)))
