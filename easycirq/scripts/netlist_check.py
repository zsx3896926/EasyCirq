#!/usr/bin/env python3
"""Read-only topology sanity check. No EDA/network/file writes. Exit 0/1/2.
See references/connectivity.md. A clear report never verifies a real board.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys


def text(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f'{label}: require nonblank string without edge whitespace')
    return value


def string_list(value, label):
    if not isinstance(value, list):
        raise ValueError(f'{label}: require array')
    values=[text(v,label) for v in value]
    if len(set(values)) != len(values):
        raise ValueError(f'{label}: duplicate values')
    return values


def validate(data):
    if not isinstance(data,dict) or not isinstance(data.get('components'),list):
        raise ValueError('require object with components array')
    for key in ('power_nets','ground_nets','external_nets'):
        string_list(data.get(key,[]),key)
    for i,c in enumerate(data['components']):
        label=f'components[{i}]'
        if not isinstance(c,dict):raise ValueError(f'{label}: require object')
        text(c.get('ref'),label+'.ref')
        if not isinstance(c.get('pins'),dict):raise ValueError(f'{label}.pins: require object')
        for pin,net in c['pins'].items():
            text(pin,label+'.pin')
            # Empty or null networks are reported as semantic conflicts, not silently NC.
            if net is not None and not isinstance(net,str):raise ValueError(f'{label}.{pin}: net must be string/null')
            if isinstance(net,str) and net and net != net.strip():raise ValueError(f'{label}.{pin}: whitespace in net')
        string_list(c.get('nc',[]),label+'.nc')
        if 'physical_pins' in c:string_list(c['physical_pins'],label+'.physical_pins')
        if 'pin_count' in c and (type(c['pin_count']) is not int or c['pin_count']<=0):
            raise ValueError(f'{label}.pin_count: require positive integer')
        if 'fitted' in c and type(c['fitted']) is not bool:raise ValueError(f'{label}.fitted: require boolean')
        if 'kind' in c:text(c['kind'],label+'.kind')
    rules=data.get('net_rules',{})
    if not isinstance(rules,dict):raise ValueError('net_rules: require object')
    for net,r in rules.items():
        text(net,'net_rules.net')
        if not isinstance(r,dict):raise ValueError('net rule: require object')
        if set(r)-{'pullup','power_net'}:raise ValueError('unknown net-rule field')
        if type(r.get('pullup')) is not bool:raise ValueError('net rule pullup: require boolean')
        if r['pullup']:text(r.get('power_net'),'net rule power_net')
    return data


def check(data):
    validate(data)
    issues=[]
    def add(level,code,where,description):
        issues.append(dict(level=level,code=code,where=where,issue=description))
    comps=data['components'];refs=defaultdict(int);nets=defaultdict(list);missing=[]
    for c in comps:
        ref=c['ref'];refs[ref]+=1
        if '?' in ref:add('阻断','placeholder_ref',ref,'位号仍含占位符')
        pins=c['pins'];nc=set(c.get('nc',[]))
        for pin,net in pins.items():
            if pin in nc:add('阻断','connected_and_nc',f'{ref}.{pin}','同脚同时出现在连接与NC数据中')
            if net is None or not net.strip():
                add('阻断','empty_net',f'{ref}.{pin}','网络为空，不能自动当NC')
            elif c.get('fitted',True):nets[net].append((ref,pin))
        inventory=c.get('physical_pins')
        if not inventory:
            missing.append(ref)
            add('待核','missing_inventory',ref,'缺少完整物理引脚ID表，无法证明无遗漏或脚号正确')
        else:
            expected=set(inventory);declared=set(pins)|nc
            if expected-declared:add('阻断','missing_pins',ref,'遗漏物理引脚: '+', '.join(sorted(expected-declared)))
            if declared-expected:add('阻断','unknown_pins',ref,'不在给定引脚表内: '+', '.join(sorted(declared-expected)))
            if 'pin_count' in c and c['pin_count']!=len(expected):
                add('阻断','inventory_count_conflict',ref,'pin_count与所给物理引脚ID表不一致')
    for ref,n in refs.items():
        if n>1:add('阻断','duplicate_ref',ref,f'位号重复{n}次')
    power=set(data.get('power_nets',[]));ground=set(data.get('ground_nets',[]))
    for net in sorted(power&ground):add('阻断','net_class_conflict',net,'被同时声明为电源和地；这是输入分类冲突，不代表已测出铜短路')
    external=set(data.get('external_nets',[]))
    for net,members in nets.items():
        if len(members)==1 and net not in external:
            add('建议','singleton_net',net,'当前装配数据中仅一个引脚；核查范围/外部延续/设计意图，不自动认定错误')
    variants=defaultdict(set)
    for net in nets:variants[re.sub(r'[_\-\s]','',net).casefold()].add(net)
    for names in variants.values():
        if len(names)>1:add('建议','similar_names',' / '.join(sorted(names)),'名称近似，需核查意图；保持原网名，不自动合并')
    for net,rule in data.get('net_rules',{}).items():
        if not rule['pullup']:continue
        target=rule['power_net']
        if target==net:
            add('阻断','invalid_pullup_rule',net,'上拉目标不能与信号网相同');continue
        candidates=[]
        for c in comps:
            values=list(c['pins'].values())
            if c.get('fitted',True) and c.get('kind')=='resistor' and len(values)==2 and set(values)=={net,target}:
                candidates.append(c['ref'])
        if not candidates:
            add('阻断','explicit_pullup_missing',net,f'当前装配数据中没有满足显式要求的两脚电阻到{target}；外部/内置上拉须另据实审查')
        elif len(candidates)>1:
            add('建议','parallel_pullups',net,'存在并联上拉: '+', '.join(candidates)+'；核算等效阻值与电压域，不自动认定不允许')
    for c in comps:
        values=list(c['pins'].values())
        if c.get('fitted',True) and c.get('kind') in {'resistor','capacitor','inductor','ferrite'} and len(values)==2 and all(isinstance(v,str) and v for v in values) and values[0]==values[1]:
            add('建议','same_net_passive',c['ref'],'两端同网，核查设计/测试意图；不能由此推断电源地短路')
    blocked=any(i['level']=='阻断' for i in issues)
    status='blocked' if blocked else 'incomplete' if missing or not comps else 'needs_review' if issues else 'no_structural_issues'
    return dict(status=status,board_verified=False,scope='supplied_components_and_selected_assembly_variant_only',
        stats=dict(components=len(comps),fitted_components=sum(c.get('fitted',True) for c in comps),nets=len(nets)),
        coverage=dict(missing_pin_inventory=missing,pin_inventory_source_verified=False,full_project_verified=False),
        issues=issues,not_checked=['原厂/库引脚表真实性','数据是否覆盖整个工程','电气额定/阻值/电压域','实际跨页与PCB铜连接','去耦充分性/稳定性/热/SI/EMC','EDA检查/保存/仿真/实测'])


def unique_object(pairs):
    obj={}
    for key,value in pairs:
        if key in obj:raise ValueError(f'duplicate JSON key: {key}')
        obj[key]=value
    return obj


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('design');ap.add_argument('--json',action='store_true');a=ap.parse_args()
    try:
        raw=Path(a.design).read_text(encoding='utf-8')
        data=json.loads(raw,object_pairs_hook=unique_object,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('non-finite JSON')))
        result=check(data)
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        print(json.dumps({'status':'invalid_input','board_verified':False,'error':str(exc)},ensure_ascii=False));return 2
    if a.json:print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        print('连接表自检: '+result['status']+'（不代表真实工程通过）')
        for i in result['issues']:print(f"[{i['level']}] {i['where']}: {i['issue']}")
        print('未覆盖: '+'、'.join(result['not_checked']))
    return 1 if result['status']=='blocked' else 0

if __name__=='__main__':sys.exit(main())
