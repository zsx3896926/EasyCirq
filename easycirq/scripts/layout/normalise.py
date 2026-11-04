#!/usr/bin/env python3
"""Shift a captured board into a positive coordinate frame (GAPS D1).

Captures are not required to start at the origin: one real board in this workspace has **all-negative Y**
(outline −2278 … −92 mil, parts likewise).  The toolchain's frame assumes a non-negative board, so that
capture produced "26 parts outside the board, 0 tracks" - a silent, spectacularly wrong result.

`normalise(dump, placement)` shifts geometry (parts, pads, outline) and the placement by the same offset
and returns it, so the caller can print it.  Boards that are already positive are returned untouched -
that matters because RetroCam-02's recorded numbers must stay comparable.

Usage
-----
    import normalise
    dump, place, offset = normalise.apply(dump, place)
"""
import copy


def _collect(r):
    xs, ys = [], []
    for c in r.get("components") or []:
        xs.append(float(c.get("x") or 0.0))
        ys.append(float(c.get("y") or 0.0))
        for p in c.get("pads") or []:
            xs.append(float(p.get("x") or 0.0))
            ys.append(float(p.get("y") or 0.0))
    return xs, ys


def offset_for(dump):
    """(ox, oy) needed to make every part/pad coordinate positive; (0, 0) when none is negative."""
    r = dump.get("result") or dump
    xs, ys = _collect(r)
    if not xs or not ys:
        return 0.0, 0.0
    ox = -min(xs) + 1.0 if min(xs) < 0 else 0.0
    oy = -min(ys) + 1.0 if min(ys) < 0 else 0.0
    return ox, oy


def apply(dump, placement=None):
    """Return (dump, placement, offset), shifted when needed.  Inputs are not modified."""
    ox, oy = offset_for(dump)
    if not ox and not oy:
        return dump, placement, (0.0, 0.0)
    out = copy.deepcopy(dump)
    r = out.get("result") or out
    for c in r.get("components") or []:
        c["x"] = float(c.get("x") or 0.0) + ox
        c["y"] = float(c.get("y") or 0.0) + oy
        b = c.get("bbox")
        if b:
            for key, delta in (("minX", ox), ("maxX", ox), ("minY", oy), ("maxY", oy)):
                if key in b:
                    b[key] = float(b[key]) + delta
        for p in c.get("pads") or []:
            p["x"] = float(p.get("x") or 0.0) + ox
            p["y"] = float(p.get("y") or 0.0) + oy
    outl = r.get("outline") or {}
    b = outl.get("bbox")
    if b:
        for key, delta in (("minX", ox), ("maxX", ox), ("minY", oy), ("maxY", oy)):
            if key in b:
                b[key] = float(b[key]) + delta
    pts = outl.get("points")
    if pts:
        outl["points"] = [[float(p[0]) + ox, float(p[1]) + oy] for p in pts]
    place = None
    if placement:
        place = {des: dict(pos) for des, pos in placement.items()}
        for des in place:
            place[des]["x"] = float(place[des]["x"]) + ox
            place[des]["y"] = float(place[des]["y"]) + oy
    return out, place, (ox, oy)
