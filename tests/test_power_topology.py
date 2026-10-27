import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'design-hardware'/'scripts'/'power_preflight'))
import pcbgeom as G
import topology as T
import power_path_audit as P

def board(lines,vias=None,pads=None):
    native={'rules':dict(zip(G.RULE_KEYS,[6,4,5,24,12,10])),'copper':{k:[] for k in ('lines','vias','fills','pours','poured','planes','arcs','regions')},'components':[],'outline':{'points':[[-1000,-1000],[1000,-1000],[1000,1000],[-1000,1000]]}}
    native['copper']['lines']=[{'primitiveId':s['id'],'net':s['net'],'layer':s['layer'],'startX':s['x1'],'startY':s['y1'],'endX':s['x2'],'endY':s['y2'],'lineWidth':s['w']} for s in lines]
    return SimpleNamespace(lines=lines,vias=vias or [],pads=pads or [],fills=[],native=native,coverage={})
def line(a,b,layer=1,w=100):
    return dict(id=str((a,b,layer)),net='P',layer=layer,x1=a[0],y1=a[1],x2=b[0],y2=b[1],w=w)
class TopologyTests(unittest.TestCase):
    def test_layers_do_not_merge(self):
        b=board([line((0,0),(100,0),1),line((100,0),(200,0),2)])
        n,i,s,g=T.net_graph(b,'P',0)
        roots,_=T.components(len(n),g)
        self.assertNotEqual(roots[i[(100,0,1)]],roots[i[(100,0,2)]])
    def test_unknown_span_does_not_merge(self):
        b=board([line((0,0),(100,0),1),line((100,0),(200,0),2)],[dict(net='P',x=100,y=0,d=20,span_known=False)])
        n,i,s,g=T.net_graph(b,'P',0)
        r,_=T.components(len(n),g)
        self.assertNotEqual(r[i[(100,0,1)]],r[i[(100,0,2)]])
    def test_same_layer_pass(self):
        b=board([line((0,0),(100,0))])
        self.assertEqual(P.audit(b,'P',.1,(0,0),(100,0),1,0,10,layer_class='external')['verdict'],'pass')
    def test_nonfinite_rejected(self):
        b=board([line((0,0),(100,0))])
        for value in (float('nan'),float('inf'),-1,True):
            with self.assertRaises(ValueError): P.audit(b,'P',value,(0,0),(100,0),1,0,10)
    def test_endpoints_required_and_bounded(self):
        b=board([line((0,0),(100,0))])
        for start,end in ((None,None),((9999,0),(100,0)),((0,0),(0,0))):
            with self.assertRaises(ValueError): P.audit(b,'P',1,start,end,1,0,10)
    def test_unknown_layers_incomplete(self):
        self.assertEqual(P.audit(board([line((0,0),(100,0))]),'P',.1,(0,0),(100,0),1,0,10)['verdict'],'incomplete')
    def test_split_length_not_whole_segment(self):
        b=board([line((0,0),(100,0)),line((40,-100),(40,100),w=1),line((60,-100),(60,100),w=1)])
        n,i,s,g=T.net_graph(b,'P',0)
        length,_=P.shortest_path(s,g,i[(40,0,1)],i[(60,0,1)],n)
        self.assertEqual(length,20)
    def test_pour_is_incomplete(self):
        b=board([line((0,0),(100,0))]); b.native={'copper':{'pours':[{}]}}
        self.assertEqual(P.audit(b,'P',.1,(0,0),(100,0),1,0,10,layer_class='external')['verdict'],'incomplete')
    def test_missing_inventory_cannot_pass(self):
        b=board([line((0,0),(100,0))]); b.native={}
        self.assertEqual(P.audit(b,'P',.1,(0,0),(100,0),1,0,10,layer_class='external')['verdict'],'incomplete')
    def test_positive_tolerance_cannot_pass(self):
        self.assertEqual(P.audit(board([line((0,0),(100,0))]),'P',.1,(0,0),(100,0),1,2,10,layer_class='external')['verdict'],'incomplete')
    def test_unplated_via_does_not_merge(self):
        b=board([line((0,0),(100,0),1),line((100,0),(200,0),2)],[dict(net='P',x=100,y=0,d=20,span_known=True,layers=[1,2],plated=False)])
        n,i,s,g=T.net_graph(b,'P',0); r,_=T.components(len(n),g)
        self.assertNotEqual(r[i[(100,0,1)]],r[i[(100,0,2)]])
if __name__=='__main__': unittest.main()
