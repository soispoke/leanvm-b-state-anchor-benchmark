"""Check the published owner-binding evidence, analysis and artifact manifest."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from owner_state.analyze import HERE, products
from owner_state.run import ROOT, LOCAL, digest, inside, targets, validate_evidence


def check(*, generated=False):
    manifest = json.loads((HERE/'evidence.json').read_text())
    if manifest['schema'] != 'leanvm-owner-evidence-v1':
        raise ValueError('unknown evidence manifest')
    for relative, expected in manifest['sha256'].items():
        if digest(inside(ROOT, relative)) != expected:
            raise ValueError(f'artifact changed: {relative}')
    reports = {kind: validate_evidence(inside(ROOT, relative)) for kind, relative in manifest['reports'].items()}
    if any(report['command'] != kind for kind, report in reports.items()):
        raise ValueError('report selection and command disagree')
    collection = reports['collect']
    if reports['verify']['source_report_sha256'] != digest(inside(ROOT, manifest['reports']['collect'])/'report.json'):
        raise ValueError('independent verification refers to a different collection')
    if len(reports['verify']['runs']) != 6 or len(reports['negative']['runs']) != 85:
        raise ValueError('expected six witness-free verifications and 85 altered-witness checks')
    if {row['condition'] for row in reports['verify']['runs']} != set(collection['cases']):
        raise ValueError('saved-proof verification has duplicate or missing conditions')
    for row in reports['verify']['runs']:
        case = collection['cases'][row['condition']]
        if row['proof_sha256'] != case['proof_sha256']:
            raise ValueError('independent verification used a different saved proof')
    negative=reports['negative']
    profile=json.loads((inside(ROOT,manifest['reports']['negative'])/'sources/real_state/profile.json').read_text())
    expected_mutations=set()
    for condition,case in negative['cases'].items():
        variant,mode=condition.split('/')
        if variant!='cse_dce' or case['sha256']['program.bin'] != collection['cases'][condition]['sha256']['program.bin']:
            raise ValueError('negative checks used a different optimized program')
        meta=case['metadata']
        secret=next(row for row in meta['witness_ranges'] if row['name']=='secret')
        mutations=targets(meta,profile)+[
            {'tag':'secret-first-bit','cell':secret['base'],'replacement':None},
            {'tag':'secret-nonboolean','cell':secret['base'],'replacement':2},
            {'tag':'secret-last-bit','cell':secret['base']+secret['length']-1,'replacement':None},
        ]
        expected_mutations.update((variant,mode,row['tag'],row['cell'],row.get('replacement')) for row in mutations)
    observed_mutations={(row['variant'],row['mode'],row['mutation']['tag'],row['mutation']['cell'],
                         row['mutation'].get('replacement')) for row in negative['runs']}
    if len(observed_mutations)!=85 or observed_mutations!=expected_mutations:
        raise ValueError('duplicate, missing or unexpected altered-witness checks')
    diagnostics = inside(ROOT, manifest['diagnostics'])
    for name, text in products(inside(ROOT, manifest['reports']['collect']),diagnostics).items():
        if (HERE/'analysis'/name).read_text() != text:
            raise ValueError(f'derived analysis differs: {name}')
    micro = json.loads((diagnostics/'report.json').read_text())
    if len(micro['runs']) != 200 or len(micro['cases']) != 25:
        raise ValueError('incomplete standalone hash diagnostics')
    for entry in micro['runs']:
        text = inside(diagnostics, entry['log']).read_text()
        found = re.findall(r'RESULT (\{[^\r\n]*\})', text)
        if len(found) != 1 or json.loads(found[0]) != entry['result']:
            raise ValueError('hash diagnostic differs from raw log')
    if generated:
        for condition, case in collection['cases'].items():
            for filename in ('program.bin', 'public.bin', 'witness.bin'):
                if digest(LOCAL/condition/filename) != case['sha256'][filename]:
                    raise ValueError(f'regenerated {condition}/{filename} differs from measured input')
    print(json.dumps({'validated': 'owner binding', 'measured_proofs': 48, 'warmup_proofs': 6,
                      'saved_proof_verifications': 6, 'altered_witness_checks': 85, 'hash_execution_diagnostics': 200,
                      'generated_inputs_checked': generated}))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generated', action='store_true')
    args = parser.parse_args()
    check(generated=args.generated)


if __name__ == '__main__':
    main()
