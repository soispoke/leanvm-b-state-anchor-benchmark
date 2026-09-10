"""Separate hash-circuit execution diagnostics; never subtracted from prove time."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from eth_utils import keccak
from owner_state.circuit import Circuit
from owner_state import hashes
from real_state.run import parse_output

ROOT=Path(__file__).resolve().parent.parent

def generate(destination, kind, length, variant):
    message=bytes((i*73+19)%256 for i in range(length))
    c=Circuit(cse=variant!='baseline',dce=variant!='baseline')
    f=hashes.keccak256 if kind=='keccak256' else (hashes.sha256_hybrid if variant=='hybrid' else hashes.sha256_ripple)
    result=f(c,c.witness('message',message))
    expected=keccak(message) if kind=='keccak256' else hashlib.sha256(message).digest()
    if c.read_bytes(result)!=expected:raise ValueError('independent hash mismatch')
    c.pack_public(result)
    metadata={'kind':kind,'length':length,'variant':variant,'input_hex':message.hex(),'expected_digest':expected.hex()}
    c.export(destination,metadata)
    return json.loads((destination/'program.json').read_text())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--repeats',type=int,default=8)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    binary=a.binary.resolve()
    out=a.output or ROOT/'owner_state/diagnostics'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True,exist_ok=False)
    data={'scope':'standalone hash circuit including Boolean inputs/public output; execute only',
          'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'repeats':a.repeats,'cases':{},'runs':[]}
    # Exact lengths used by any of the three owner-state programs.
    lengths=Counter()
    for mode in ('direct','rlp','ssz'):
        m=json.loads((ROOT/'local-runs/owner-state/cse_dce'/mode/'program.json').read_text())
        for section in m['optimization']['sections']:
            if section['kind']!='relation':lengths[(section['kind'],section['length_bytes'])]+=1
    for kind,length in sorted(lengths):
        for variant in ('baseline','cse_dce')+ (('hybrid',) if kind=='sha256' else ()):
            key=f'{kind}-{length}-{variant}'
            directory=ROOT/'local-runs/owner-hash-diagnostics'/key
            data['cases'][key]=generate(directory,kind,length,variant)
    env=dict(os.environ,RAYON_NUM_THREADS='11')
    for key in list(env):
        if key=='LEANVM_PROFILE' or key=='LEANVM_PHASE_PROFILE' or (key.startswith('FLOCK_') and key.endswith('_TIMING')):
            env.pop(key)
    # Alternate case order for diagnostics; separate from main proving dataset.
    for repetition in range(a.repeats):
        keys=sorted(data['cases'],reverse=bool(repetition%2))
        for key in keys:
            directory=ROOT/'local-runs/owner-hash-diagnostics'/key
            env.update(REAL_STATE_ACTION='execute',REAL_STATE_DIR=str(directory))
            started=time.perf_counter()
            proc=subprocess.run([str(binary),'real_state_benchmark','--nocapture','--test-threads=1'],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            name=f'{key}-{repetition+1:02}.txt';(out/name).write_text(proc.stdout)
            result,_=parse_output(proc.stdout)
            if proc.returncode or result is None or result['action']!='execute':raise RuntimeError(f'failed {name}')
            data['runs'].append({'case':key,'repetition':repetition+1,'log':name,'result':result,'process_s':time.perf_counter()-started})
    (out/'report.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'output':str(out),'cases':len(data['cases']),'runs':len(data['runs'])}))

if __name__=='__main__':main()
