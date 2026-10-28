import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "easycirq/scripts/power_preflight"
sys.path.insert(0, str(ROOT))
import pcbgeom as G
from clearance import Obstacles


def dump():
    return {"rules": dict(zip(G.RULE_KEYS, (6,4,5,24,12,10))), "copper": {}, "components": []}


class GeometryTests(unittest.TestCase):
    def test_segment_inside(self):
        self.assertLessEqual(G.d_seg_rect(2,2,3,3,(0,0,10,10)),0)

    def test_rectangle_symmetry(self):
        a,b=(0,0,10,10),(3,20,5,22)
        self.assertEqual(G.d_rect_rect(a,b),10)
        self.assertEqual(G.d_rect_rect(a,b),G.d_rect_rect(b,a))

    def test_nonround_ellipse_conservative(self):
        p={"shape":"ELLIPSE","x":0,"y":0,"w":20,"h":2}
        self.assertLessEqual(G.pad_gap_pt(9,0,p),0)
        self.assertLessEqual(G.pad_gap_seg(8,0,9,0,p),0)

    def test_readback_rotation_dimensions_are_preserved(self):
        d=dump()
        d["components"]=[{"designator":"J1","pads":[{
            "x":0,"y":0,"width":106.3,"height":64.4,"layer":1,
            "shape":["RECT"],"angle":90}]}]
        b=G.Board(d)
        self.assertEqual((b.pads[0]["w"],b.pads[0]["h"]),(106.3,64.4))
        self.assertFalse(b.pads[0]["approx"])
        self.assertFalse(b.limitations)
        d["components"][0]["pads"][0]["angle"]=45
        b=G.Board(d)
        self.assertEqual((b.pads[0]["w"],b.pads[0]["h"]),(106.3,64.4))
        self.assertTrue(b.pads[0]["approx"])
        self.assertTrue(b.coverage["unsupported"])

    def test_strict_rules_and_bool(self):
        with self.assertRaises(ValueError): G.Board({})
        d=dump();d["rules"]["clearanceMil"]=True
        with self.assertRaises(ValueError): G.Board(d)
        d=dump();d["copper"]["lines"]=[{"layer":1,"startX":0,"startY":0,"endX":1,"endY":1,"lineWidth":float("nan")}]
        with self.assertRaises(ValueError): G.Board(d)

    def test_layers_fills_body_and_width(self):
        d=dump();d["components"]=[{"designator":"U1","bbox":{"minX":0,"minY":0,"maxX":10,"maxY":10},"pads":[{"x":5,"y":5,"width":2,"height":2,"layer":2,"net":"a"}]}]
        b=G.Board(d);o=Obstacles(b)
        self.assertFalse(b.hard_body("U1"))
        self.assertFalse(any(c["kind"]=="pad" for c in o.check_pad("b",1,5,5,2,2)[2]))
        self.assertTrue(any(c["kind"]=="pad" for c in o.check_pad("b",12,5,5,2,2)[2]))
        b.rules["hard_body_designators"]=("U1",)
        self.assertTrue(any(c["kind"]=="body" and c["gap"]<0 for c in Obstacles(b).check_line("a",1,4,1,1,2,2)[2]))
        b.fills=[{"id":"f","net":None,"layer":1,"rect":(0,0,10,10)}]
        self.assertTrue(any(c["kind"]=="fill" and c["gap"]<0 for c in Obstacles(b).check_line("a",1,4,1,1,2,2)[2]))

if __name__ == "__main__": unittest.main()
