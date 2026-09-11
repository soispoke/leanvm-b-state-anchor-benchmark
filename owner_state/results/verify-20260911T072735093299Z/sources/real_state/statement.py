"""A bounded-shape Ethereum inclusion relation, enforced by leanVM instructions.

Canonical RLP parsing is checked by re-encoding a public structural layout and
constraining every prefix and payload boundary. Layouts contain lengths/types,
never node contents, roots, account keys, or values. Trie routing is selected by
computed key nibbles. The same bytecode accepts any valid witness of this shape.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import analyze_fixtures as reference
from eth_utils import keccak
from real_state.circuit import Circuit
from real_state.hashes import keccak256, sha256

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = b'LVMSTATE1'
MODES = {'direct': 0, 'rlp': 1, 'ssz': 2}


def unhex(value):
    return bytes.fromhex(value.removeprefix('0x'))


def shape(value):
    if isinstance(value, list):
        return {'kind':'list', 'children':[shape(x) for x in value]}
    return {'kind':'bytes', 'length':len(value), 'bare':len(value)==1 and value[0]<128}


def prefix(kind, length):
    if length < 56:
        return bytes([(0xc0 if kind=='list' else 0x80)+length])
    encoded = length.to_bytes((length.bit_length()+7)//8, 'big')
    return bytes([(0xf7 if kind=='list' else 0xb7)+len(encoded)])+encoded


def size(layout):
    if layout['kind']=='bytes':
        length=layout['length']
        return length if layout['bare'] else len(prefix('bytes',length))+length
    length=sum(size(child) for child in layout['children'])
    return len(prefix('list',length))+length


@dataclass
class Item:
    kind: str
    raw: list
    payload: list
    children: list


def decode(c, raw, layout):
    if len(raw)!=size(layout):
        raise ValueError('RLP encoding does not fit public layout')
    if layout['kind']=='bytes':
        length=layout['length']
        if layout['bare']:
            if length!=1:
                raise ValueError('bare RLP must have one byte')
            c.assert_eq(raw[0][7],c.zero)
            return Item('bytes',raw,raw,[])
        p=prefix('bytes',length)
        c.assert_bytes(raw[:len(p)],c.literal(p))
        payload=raw[len(p):]
        if length==1:
            c.assert_eq(payload[0][7],c.one)
        return Item('bytes',raw,payload,[])
    layouts=layout['children']
    p=prefix('list',sum(size(x) for x in layouts))
    c.assert_bytes(raw[:len(p)],c.literal(p))
    children=[]
    cursor=len(p)
    for child in layouts:
        end=cursor+size(child)
        children.append(decode(c,raw[cursor:end],child))
        cursor=end
    if cursor!=len(raw):
        raise ValueError('RLP list did not consume every byte')
    return Item('list',raw,raw[len(p):],children)


def byte_string(item, length=None):
    if item.kind!='bytes' or (length is not None and len(item.payload)!=length):
        raise ValueError('wrong RLP field type or width in public layout')
    return item.payload


def integer(c, item, max_bytes):
    raw=byte_string(item)
    if len(raw)>max_bytes:
        raise ValueError('integer exceeds its protocol width')
    if raw:
        c.nonzero(raw[0])
    return raw


def nibbles(data):
    return [part for byte in data for part in (byte[4:],byte[:4])]


def compact_path(c, item, odd, leaf):
    data=byte_string(item)
    if not 1<=len(data)<=33:
        raise ValueError('invalid compact path length')
    flags=(2 if leaf else 0)+int(odd)
    for bit in range(4):
        c.assert_eq(data[0][bit+4],c.one if flags>>bit&1 else c.zero)
    if not odd:
        for bit in data[0][:4]:
            c.assert_eq(bit,c.zero)
    return ([data[0][:4]] if odd else [])+nibbles(data[1:])


def check_child_shape(item):
    if item.kind=='bytes':
        if len(item.payload) not in (0,32):
            raise ValueError('MPT child string must be empty or32-byte hash')
    elif len(item.raw)>=32 or len(item.children) not in (2,17):
        raise ValueError('embedded MPT child must be a short node list')


def child_matches(c, child, next_raw, next_hash):
    check_child_shape(child)
    if len(next_raw)>=32:
        c.assert_bytes(byte_string(child,32),next_hash)
    else:
        if child.kind!='list':
            raise ValueError('short MPT child must be embedded')
        c.assert_bytes(child.raw,next_raw)


def inclusion(c, key, root, raws, layouts, odd_paths):
    if not raws or len(raws)!=len(layouts):
        raise ValueError('empty or mismatched proof')
    nodes=[decode(c,raw,layout) for raw,layout in zip(raws,layouts)]
    if any(node.kind!='list' or len(node.children) not in (2,17) for node in nodes):
        raise ValueError('MPT node must have two or17 list items')
    hashes=[keccak256(c,raw) for raw in raws]
    c.assert_bytes(hashes[0],root)
    path=nibbles(key)
    pos=0
    for i,node in enumerate(nodes):
        last=i==len(nodes)-1
        parts=node.children
        if len(parts)==17:
            for child in parts[:16]:
                check_child_shape(child)
            value=byte_string(parts[16])
            occupied=sum(child.kind=='list' or bool(child.payload) for child in parts)
            if occupied<2:
                raise ValueError('noncanonical collapsible branch')
            if pos==64:
                if not last or not value:
                    raise ValueError('invalid terminal branch')
                return value
            if pos>64 or last:
                raise ValueError('branch proof ends before key')
            next_raw=raws[i+1]
            target=hashes[i+1] if len(next_raw)>=32 else next_raw
            selected=[[c.zero]*8 for _ in target]
            for index,child in enumerate(parts[:16]):
                chosen=c.one
                for bit,wire in enumerate(path[pos]):
                    chosen=c.and_(chosen,wire if index>>bit&1 else c.not_(wire))
                valid=(child.kind=='bytes' and len(child.payload)==32) if len(next_raw)>=32 else (child.kind=='list' and len(child.raw)==len(next_raw))
                if not valid:
                    c.assert_eq(chosen,c.zero)
                    continue
                candidate=child.payload if len(next_raw)>=32 else child.raw
                for j,byte in enumerate(candidate):
                    for k,wire in enumerate(byte):
                        selected[j][k]=c.xor(selected[j][k],c.and_(chosen,wire))
            c.assert_bytes(selected,target)
            pos+=1
        else:
            fragment=compact_path(c,parts[0],odd_paths[i],last)
            if pos+len(fragment)>64:
                raise ValueError('compact path exceeds secure key')
            for actual,expected in zip(fragment,path[pos:pos+len(fragment)]):
                for a,b in zip(actual,expected):
                    c.assert_eq(a,b)
            pos+=len(fragment)
            if last:
                if pos!=64:
                    raise ValueError('leaf does not consume the entire secure key')
                value=byte_string(parts[1])
                if not value:
                    raise ValueError('empty trie leaf value')
                return value
            if not fragment or len(nodes[i+1].children)!=17:
                raise ValueError('empty or noncanonical adjacent extension')
            child_matches(c,parts[1],raws[i+1],hashes[i+1])
    raise ValueError('proof has no terminal value')


def load_fixture():
    fixture=json.loads((ROOT/'fixtures/mainnet-0x18bd000.json').read_text())
    proof=fixture['cases']['safe_authorization']['proof']
    storage=next(x for x in proof['storageProof'] if int(x['key'],16)==0)
    return fixture,proof,storage


def public_profile():
    f,a,s=load_fixture()
    def trie_profile(nodes):
        decoded=[reference.rlp_decode(unhex(raw)) for raw in nodes]
        return {'nodes':[shape(x) for x in decoded],
                'odd_paths':[bool(x[0][0]&0x10) if len(x)==2 else False for x in decoded]}
    ap=trie_profile(a['accountProof'])
    sp=trie_profile(s['proof'])
    account_value=reference.rlp_decode(unhex(a['accountProof'][-1]))[1]
    storage_value=reference.rlp_decode(unhex(s['proof'][-1]))[1]
    header=reference.block_header(f['block'])
    return {'schema':'leanvm-account-storage-shape-v1',
            'account':ap,'storage':sp,
            'account_value':shape(reference.rlp_decode(account_value)),
            'storage_value':shape(reference.rlp_decode(storage_value)),
            'header':shape(reference.rlp_decode(header)),
            'ssz_gindex':41,'ssz_active_fields':18}


def build(mode, profile, check_witness=True):
    f,a,s=load_fixture()
    c=Circuit()
    c.check_witness=check_witness
    account=c.witness('address',unhex(a['address']))
    slot=c.witness('slot',int(s['key'],16).to_bytes(32,'big'))
    value=c.witness('value',int(s['value'],16).to_bytes(32,'big'))
    state=c.witness('state_root',unhex(f['block']['stateRoot']))
    account_nodes=[c.witness(f'account_node_{i:02}',unhex(raw)) for i,raw in enumerate(a['accountProof'])]
    storage_nodes=[c.witness(f'storage_node_{i:02}',unhex(raw)) for i,raw in enumerate(s['proof'])]
    if mode=='direct':
        anchor=state
        anchor_bytes=unhex(f['block']['stateRoot'])
    elif mode=='rlp':
        header=c.witness('header',reference.block_header(f['block']))
        decoded=decode(c,header,profile['header'])
        if decoded.kind!='list' or len(decoded.children)!=21:
            raise ValueError('this profile requires the21-field header')
        fixed={0:32,1:32,2:20,3:32,4:32,5:32,6:256,13:32,14:8,16:32,19:32,20:32}
        integers={7:32,8:8,9:8,10:8,11:8,15:32,17:8,18:8}
        for index,width in fixed.items():
            byte_string(decoded.children[index],width)
        for index,width in integers.items():
            integer(c,decoded.children[index],width)
        if len(byte_string(decoded.children[12]))>32:
            raise ValueError('extraData longer than32 bytes')
        c.assert_bytes(byte_string(decoded.children[3],32),state)
        anchor=keccak256(c,header)
        anchor_bytes=unhex(f['block']['hash'])
    elif mode=='ssz':
        branch=json.loads((ROOT/'real_state/ssz-reference.json').read_text())
        if profile['ssz_gindex']!=41 or profile['ssz_active_fields']!=18:
            raise ValueError('unsupported SSZ branch profile')
        anchor=state
        directions=[True,False,False,True,False]
        for i,left in enumerate(directions):
            sibling=c.witness(f'ssz_sibling_{i}',unhex(branch['siblings'][i]))
            if i==4:
                c.assert_bytes(sibling,c.literal(((1<<18)-1).to_bytes(32,'little')))
            anchor=sha256(c,sibling+anchor if left else anchor+sibling)
        anchor_bytes=unhex(branch['ssz_root'])
    else:
        raise ValueError('unknown anchor mode')
    account_key=keccak256(c,account)
    storage_key=keccak256(c,slot)
    ap=profile['account']
    account_value=inclusion(c,account_key,state,account_nodes,ap['nodes'],ap['odd_paths'])
    record=decode(c,account_value,profile['account_value'])
    if record.kind!='list' or len(record.children)!=4:
        raise ValueError('account must have nonce,balance,storageRoot,codeHash')
    integer(c,record.children[0],8)
    integer(c,record.children[1],32)
    storage_root=byte_string(record.children[2],32)
    byte_string(record.children[3],32)
    sp=profile['storage']
    storage_value=inclusion(c,storage_key,storage_root,storage_nodes,sp['nodes'],sp['odd_paths'])
    scalar=decode(c,storage_value,profile['storage_value'])
    result=integer(c,scalar,32)
    c.assert_bytes(c.literal(bytes(32-len(result)))+result,value)
    statement=c.literal(DOMAIN+bytes([MODES[mode]]))+anchor+account+slot+value
    digest=keccak256(c,statement)
    c.pack_public(digest)
    expected=keccak(DOMAIN+bytes([MODES[mode]])+anchor_bytes+unhex(a['address'])+int(s['key'],16).to_bytes(32,'big')+int(s['value'],16).to_bytes(32,'big'))
    if c.read_bytes(digest)!=expected:
        raise ValueError('guest digest disagrees with independent public statement')
    return c,{'mode':mode,'anchor':'0x'+anchor_bytes.hex(),'account':a['address'],
              'slot':s['key'],'value':'0x'+int(s['value'],16).to_bytes(32,'big').hex(),
              'public_digest':'0x'+expected.hex(),
              'profile_sha256':hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=MODES)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--write-profile',action='store_true')
    args=parser.parse_args()
    path=ROOT/'real_state/profile.json'
    if args.write_profile:
        if path.exists():
            raise SystemExit('profile already exists; do not silently replace the public relation')
        path.write_text(json.dumps(public_profile(),indent=2)+'\n')
    profile=json.loads(path.read_text())
    circuit,meta=build(args.mode,profile)
    circuit.export(args.output,meta)
    print(json.dumps(meta|{'op_counts':circuit.counts,'memory_cells':len(circuit.values)}))


if __name__=='__main__':
    main()
