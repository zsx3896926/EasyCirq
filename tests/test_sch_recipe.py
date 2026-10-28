import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'easycirq/scripts/sch_recipe.py'
spec=importlib.util.spec_from_file_location('sch_recipe',SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
RECIPES=json.loads(mod.CATALOG.read_text(encoding='utf-8'))['recipes']


def fixture(recipe,scale=1):
    # Deliberately synthetic measured geometry, never a library acceptance fixture.
    nets={f'{r}.{p}':f'{r}.{p}' for r,ps in recipe['roles'].items() for p in ps}
    for a,b in recipe['connections']:
        old,new=nets[b],nets[a]
        nets={k:(new if v==old else v) for k,v in nets.items()}
    components,bindings=[],{}
    for i,(role,pins) in enumerate(recipe['roles'].items()):
        x,y=100+i*100,200
        width,height=20*scale,10*scale
        geom=[dict(number=str(j+1),name=p,net=nets[f'{role}.{p}'],
                   x=x+(-width if j%2==0 else width),y=y+j*5,rotation=0)
              for j,p in enumerate(pins)]
        m=dict(designator=f'X{i}',primitiveId=f'primitive-{i}',x=x,y=y,
               rotation=90,mirror=True,
               bbox=dict(minX=x-width,minY=y-height,maxX=x+width,maxY=y+height),
               textBboxes=[dict(minX=x-width,minY=y+height+5,maxX=x+width+10,maxY=y+height+15)],
               pins=geom)
        components.append(dict(id=f'cmp-{i}',measurement=m,allowedRotations=[0,90]))
        bindings[role]=dict(componentId=f'cmp-{i}',pins={p:str(j+1) for j,p in enumerate(pins)})
    return dict(schemaVersion=1,components=components),bindings


class RecipeTests(unittest.TestCase):
    def test_fixed_obstacle_moves_candidate_outward_without_changing_alignment(self):
        recipe = RECIPES[0]
        source, bindings = fixture(recipe)
        initial = mod.instantiate(source, bindings, recipe)
        lower = next(p for p in initial['placements'] if p['role'] == 'lower')
        obstacle = copy.deepcopy(source['components'][1])
        obstacle['id'] = 'fixed-obstacle'
        obstacle['measurement'] = copy.deepcopy(lower['measurement'])
        source['components'].append(obstacle)
        before = copy.deepcopy(source)
        result = mod.instantiate(source, bindings, recipe)
        moved = next(p for p in result['placements'] if p['role'] == 'lower')
        self.assertTrue(mod.separated(mod.envelope(moved['measurement']), mod.envelope(obstacle['measurement']), 20))
        self.assertEqual(moved['measurement']['x'], lower['measurement']['x'])
        self.assertLess(moved['measurement']['y'], lower['measurement']['y'])
        self.assertGreater(result['placementSearch'][0]['steps'], 0)
        self.assertEqual(source, before)
        self.assertEqual(result, mod.instantiate(source, bindings, recipe))
        exhausted = mod.instantiate(source, bindings, recipe, max_steps=0)
        self.assertEqual(exhausted['status'], 'needs_review')
        self.assertIn('placement_search_exhausted', [w['code'] for w in exhausted['warnings']])
        self.assertEqual(exhausted['routingStatus'], 'NOT RUN')

    def test_invalid_search_budget(self):
        recipe = RECIPES[0]
        source, bindings = fixture(recipe)
        for budget in (-1, 1.5, True, 10001):
            with self.assertRaises(ValueError):
                mod.instantiate(source, bindings, recipe, max_steps=budget)


    def test_all_recipes_two_measured_sizes_preserve_geometry_and_nets(self):
        for recipe in RECIPES:
            for scale in (1,3):
                with self.subTest(recipe=recipe['id'],scale=scale):
                    source,bindings=fixture(recipe,scale)
                    baseline=copy.deepcopy(source)
                    result=mod.instantiate(source,bindings,recipe)
                    self.assertEqual(source,baseline)
                    self.assertEqual(result['liveApplyStatus'],'NOT RUN')
                    self.assertEqual(result,mod.instantiate(source,bindings,recipe))
                    before={c['id']:c['measurement'] for c in source['components']}
                    after={p['role']:p['measurement'] for p in result['placements']}
                    for row in result['placements']:
                        old,new=before[row['componentId']],row['measurement']
                        dx,dy=row['delta']
                        self.assertEqual((new['rotation'],new['mirror']),(old['rotation'],old['mirror']))
                        for p,q in zip(old['pins'],new['pins']):
                            self.assertEqual((p['number'],p['net']),(q['number'],q['net']))
                            self.assertEqual((q['x']-p['x'],q['y']-p['y']),(dx,dy))
                    for rule in recipe['placements']:
                        own,other=mod.envelope(after[rule['role']]),mod.envelope(after[rule['relativeTo']])
                        side=rule['side']
                        distance={'left':other[0]-own[2],'right':own[0]-other[2],
                                  'above':own[1]-other[3],'below':other[1]-own[3]}[side]
                        self.assertGreaterEqual(distance,20)
                        p=next(p for p in after[rule['role']]['pins'] if p['number']==bindings[rule['role']]['pins'][rule['pin']])
                        q=next(p for p in after[rule['relativeTo']]['pins'] if p['number']==bindings[rule['relativeTo']]['pins'][rule['targetPin']])
                        axis='y' if side in ('left','right') else 'x'
                        self.assertEqual(p[axis],q[axis])
                    ET.fromstring(mod.render(result))

    def test_wrong_net_and_physical_pin_refused(self):
        source,bindings=fixture(RECIPES[0])
        source['components'][1]['measurement']['pins'][0]['net']='WRONG'
        with self.assertRaisesRegex(ValueError,'topology mismatch'):
            mod.instantiate(source,bindings,RECIPES[0])
        source,bindings=fixture(RECIPES[0])
        bindings['lower']['pins']['tap']='999'
        with self.assertRaises(KeyError):
            mod.instantiate(source,bindings,RECIPES[0])

    def test_missing_text_is_not_pass_and_bad_grid_refused(self):
        source,bindings=fixture(RECIPES[0])
        del source['components'][0]['measurement']['textBboxes']
        self.assertEqual(mod.instantiate(source,bindings,RECIPES[0])['status'],'needs_review')
        source['components'][0]['measurement']['pins'][0]['x']+=1
        with self.assertRaisesRegex(ValueError,'5-raw'):
            mod.instantiate(source,bindings,RECIPES[0])

    def test_cli_real_entry_outputs_candidate_and_parseable_svg(self):
        source,bindings=fixture(RECIPES[0])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'source.json').write_text(json.dumps(source),encoding='utf-8')
            (root/'bindings.json').write_text(json.dumps(bindings),encoding='utf-8')
            proc=subprocess.run([sys.executable,str(SCRIPT),'--recipe','divider',
                                 '--source',str(root/'source.json'),'--bindings',str(root/'bindings.json'),
                                 '--out-dir',str(root/'out')],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
            candidate=json.loads((root/'out/recipe-candidate.json').read_text(encoding='utf-8'))
            self.assertEqual(len(candidate['provenance']['source']),64)
            ET.parse(root/'out/recipe-preview.svg')


if __name__=='__main__':
    unittest.main()

