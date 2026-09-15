"""Owner commitment and authenticated account/storage relation.

H = Keccak256(owner_addr:20 || secret:32).
Public digest = Keccak256("LVMOWNER1" || mode:1 || anchor:32 || H:32 || slot:32).
The address, secret and authenticated stored word are witnesses. This pinned
backend is not a zero-knowledge prover; witness inputs do not imply privacy.
The MPT relation below is copied unchanged from the preserved real_state code,
with Keccak routed through the hash profiling/compiler scope.
"""
import hashlib
import json
from pathlib import Path

from eth_utils import keccak
import analyze_fixtures as reference
from real_state.statement import (unhex, decode, byte_string, integer, nibbles,
    compact_path, check_child_shape, child_matches, load_fixture)
from owner_state.circuit import Circuit
from owner_state.hashes import keccak256, sha256, sha256_ripple, sha256_hybrid

ROOT=Path(__file__).resolve().parent.parent
DOMAIN=b'LVMOWNER1'
SECRET=bytes(range(32))  # Public synthetic benchmark fixture; never real secret material.
MODES={'direct':0,'rlp':1,'ssz':2}
VARIANTS={
    'baseline': {'cse':False,'dce':False,'sha':sha256_ripple},
    'dce': {'cse':False,'dce':True,'sha':sha256_ripple},
    'cse_dce': {'cse':True,'dce':True,'sha':sha256_ripple},
    'hybrid': {'cse':True,'dce':True,'sha':sha256_hybrid},
    'one_mul': {'cse':True,'dce':True,'sha':sha256},
}

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


def build(mode, profile, *, variant="baseline", check_witness=True, secret=SECRET):
    if len(secret)!=32:
        raise ValueError("note secret must be exactly 32 bytes")
    f,a,s=load_fixture()
    if len(unhex(a["address"]))!=20:
        raise ValueError("account address must be exactly 20 bytes")
    if variant not in VARIANTS:
        raise ValueError("unknown compiler variant")
    settings=VARIANTS[variant]
    c=Circuit(cse=settings["cse"], dce=settings["dce"])
    sha256=settings["sha"]
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
    secret_wires=c.witness('secret',secret)
    note=keccak256(c,account+secret_wires)
    statement=c.literal(DOMAIN+bytes([MODES[mode]]))+anchor+note+slot
    digest=keccak256(c,statement)
    c.pack_public(digest)
    note_commitment=keccak(unhex(a['address'])+secret)
    expected=keccak(DOMAIN+bytes([MODES[mode]])+anchor_bytes+note_commitment+int(s['key'],16).to_bytes(32,'big'))
    if c.read_bytes(digest)!=expected:
        raise ValueError('guest digest disagrees with independent public statement')
    return c,{'relation':'owner-v1','variant':variant,'note_commitment':'0x'+note_commitment.hex(),
              'secret_fixture':'0x'+secret.hex(),'mode':mode,'anchor':'0x'+anchor_bytes.hex(),'account':a['address'],
              'slot':s['key'],'value':'0x'+int(s['value'],16).to_bytes(32,'big').hex(),
              'public_digest':'0x'+expected.hex(),
              'profile_sha256':hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()}

