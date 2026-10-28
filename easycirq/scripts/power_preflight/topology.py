"""Layer-aware track topology. Copper regions are deliberately not inferred."""
import math


def components(node_count, groups, skip=()):
    parent = list(range(node_count))
    def root(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for si, group in enumerate(groups):
        if si in skip or not group:
            continue
        for b in group[1:]:
            parent[root(b)] = root(group[0])
    roots = {i: root(i) for i in range(node_count)}
    return roots, len(set(roots.values()))


def net_graph(board, net, tol=0.0):
    try:
        from . import pcbgeom as G
    except ImportError:
        import pcbgeom as G
    if isinstance(tol,bool) or not math.isfinite(tol) or tol < 0:
        raise ValueError('tol must be finite and nonnegative')
    nodes, index, groups = [], {}, []
    segs = [dict(s) for s in board.lines if s['net'] == net]
    def node(x, y, layer):
        key = (round(x, 9), round(y, 9), layer)
        if key not in index:
            index[key] = len(nodes)
            nodes.append(key)
        return index[key]
    for s in segs:
        groups.append([node(s['x1'], s['y1'], s['layer']), node(s['x2'], s['y2'], s['layer'])])
    def attach(x, y, layer, radius=0):
        n = node(x, y, layer)
        for i, s in enumerate(segs):
            if s['layer'] == layer and G.d_pt_seg(x,y,s['x1'],s['y1'],s['x2'],s['y2']) <= radius+s['w']/2+tol:
                groups[i].append(n)
        return n
    # Crossing centre lines join only on their actual copper layer.
    for i, a in enumerate(segs):
        for j in range(i):
            b=segs[j]
            if a['layer'] != b['layer']:
                continue
            ax,ay=a['x2']-a['x1'],a['y2']-a['y1']
            bx,by=b['x2']-b['x1'],b['y2']-b['y1']
            det=ax*by-ay*bx
            if abs(det)>1e-12:
                dx,dy=b['x1']-a['x1'],b['y1']-a['y1']
                t=(dx*by-dy*bx)/det; u=(dx*ay-dy*ax)/det
                if 0<=t<=1 and 0<=u<=1:
                    n=node(a['x1']+t*ax,a['y1']+t*ay,a['layer'])
                    groups[i].append(n); groups[j].append(n)
            for s,k in ((a,j),(b,i)):
                for x,y in ((s['x1'],s['y1']),(s['x2'],s['y2'])):
                    other=segs[k]
                    if G.d_pt_seg(x,y,other['x1'],other['y1'],other['x2'],other['y2']) <= (s['w']+other['w'])/2+tol:
                        groups[k].append(node(x,y,s['layer']))
    links=[]
    for pad in board.pads:
        if pad['net'] != net: continue
        layers=pad.get('layers') if pad.get('plated') is True else None
        if not layers: layers=[pad['layer']] if pad.get('layer') != 12 else []
        padnodes=[]
        for layer in layers:
            n=node(pad['x'],pad['y'],layer); padnodes.append(n)
            for i,s in enumerate(segs):
                if s['layer']==layer and not pad.get('approx') and G.pad_gap_seg(s['x1'],s['y1'],s['x2'],s['y2'],pad)<=s['w']/2+tol:
                    groups[i].append(n)
        if len(padnodes)>1: links.append(padnodes)
    for via in board.vias:
        if via['net'] != net or not via.get('span_known') or via.get('plated') is not True or not via.get('layers'): continue
        links.append([attach(via['x'],via['y'],l,via['d']/2) for l in via['layers']])
    for link in links:
        if len(link)>1:
            p=nodes[link[0]]
            segs.append({'id':'interlayer-contact','net':net,'layer':p[2],'x1':p[0],'y1':p[1],'x2':p[0],'y2':p[1],'w':0,'contact':True})
            groups.append(link)
    return nodes,index,segs,[list(dict.fromkeys(g)) for g in groups]
