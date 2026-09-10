"""Check preserved evidence and, optionally, regenerated program bytes.

This checks integrity and recorded outcomes. Use real_state.run verify for live
cryptographic verification of the saved proofs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from eth_utils import keccak
from real_state.run import MODES, digest, parse_output, targets
from real_state.summarize import summarize

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / 'real_state'
RESULTS = HERE / 'results'
LEGACY_VERIFY = 'verify-20260910T084013381207Z'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def check_sources(source_hashes):
    for name, expected in source_hashes.items():
        path = ROOT / name
        # Preserve the original collector, whose sole later change handles
        # libtest's same-line prefix. No guest or Rust runner source changed.
        if name == 'real_state/run.py' and expected != digest(path):
            path = RESULTS / 'measurement-run.py.txt'
        require(digest(path) == expected, f'recorded source differs: {name}')


def verify(generated=False):
    manifest = HERE / 'evidence-sha256.txt'
    names = set()
    for line in manifest.read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = ROOT / name
        require(path.resolve().is_relative_to(HERE), 'manifest path outside real_state')
        require(name not in names, 'duplicate manifest entry')
        names.add(name)
        require(digest(path) == expected, f'evidence hash mismatch: {name}')
    actual = {str(path.relative_to(ROOT)) for path in HERE.rglob('*')
              if path.is_file() and '__pycache__' not in path.parts and path != manifest}
    require(names == actual, 'evidence manifest must cover all real_state files')

    environment = read(RESULTS / 'environment.json')
    check_sources(environment['source_sha256'])
    programs = read(HERE / 'programs.json')
    profile = read(HERE / 'profile.json')
    profile_hash = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
    fixture = read(ROOT / 'fixtures/mainnet-0x18bd000.json')
    account = fixture['cases']['safe_authorization']['proof']
    storage = next(item for item in account['storageProof'] if int(item['key'], 16) == 0)
    anchors = (fixture['block']['stateRoot'], fixture['block']['hash'],
               read(HERE / 'ssz-reference.json')['ssz_root'])
    require(set(programs) == set(MODES), 'expected exactly three programs')
    for index, mode in enumerate(MODES):
        program = programs[mode]
        meta = program['metadata']
        expected = keccak(b'LVMSTATE1' + bytes([index]) + bytes.fromhex(anchors[index][2:])
                          + bytes.fromhex(account['address'][2:])
                          + int(storage['key'], 16).to_bytes(32, 'big')
                          + int(storage['value'], 16).to_bytes(32, 'big'))
        require(meta['public_digest'] == '0x' + expected.hex(), f'{mode}: public statement')
        require(meta['profile_sha256'] == profile_hash, f'{mode}: profile hash')
        require(hashlib.sha256(expected).hexdigest() == program['sha256']['public.bin'],
                f'{mode}: public input bytes')
        proof = HERE / 'proofs' / f'{mode}.bin'
        require(digest(proof) == program['saved_proof_sha256'], f'{mode}: saved proof hash')
        for repetition in (1, 2, 3):
            log = (RESULTS / f'{mode}-prove-{repetition}.txt').read_text()
            result, _ = parse_output(log)
            counts = meta['op_counts']
            expected_counts = [counts['xor'], counts['mul'], counts['set'] + 3, 0, 1, 0]
            require(result is not None and result['action'] == 'prove', f'{mode}: proof record')
            require(result['counts'] == expected_counts and result['cycles'] == sum(expected_counts),
                    f'{mode}: instruction counts')
            require(result['cells'] == meta['memory_cells'] + 3, f'{mode}: memory cells')
            require(result['proof_bytes'] == proof.stat().st_size, f'{mode}: proof size')
            require(result['wrong_public_rejected'] and result['mutated_proof_rejected'],
                    f'{mode}: proof tamper checks')
            require('test result: ok. 1 passed; 0 failed;' in log, f'{mode}: process test outcome')
        if generated:
            directory = ROOT / 'local-runs/real-state' / mode
            require(read(directory / 'program.json') == meta, f'{mode}: generated metadata')
            for name, expected_hash in program['sha256'].items():
                require(digest(directory / name) == expected_hash, f'{mode}: generated {name}')
    require(summarize() == (RESULTS / 'summary.csv').read_text(), 'timing summary differs')

    verified = []
    negatives = {mode: [] for mode in MODES}
    for path in sorted(RESULTS.glob('*/report.json')):
        report = read(path)
        check_sources(report['source_sha256'])
        check_sources(report['runner']['source_sha256'])
        require(report['runner']['binary_sha256'] == environment['binary_sha256'],
                'recorded validation binary changed')
        for mode, case in report['cases'].items():
            require(case['metadata'] == programs[mode]['metadata'], 'validation metadata changed')
            for name, value in case['sha256'].items():
                if name in programs[mode]['sha256']:
                    require(value == programs[mode]['sha256'][name], 'validation input changed')
        for run in report['runs']:
            log = (path.parent / run['log']).read_text()
            result, rejection = parse_output(log)
            require(run['exit_code'] == 0 and 'test result: ok. 1 passed; 0 failed;' in log,
                    'unsuccessful validation process')
            if path.parent.name == LEGACY_VERIFY:
                require(run['passed'] is False and run['result'] is None
                        and result['action'] == 'verify' and result['witness_loaded'] is False,
                        'unexpected initial collector failure')
                continue
            require(run['passed'] is True and result == run['result'] and rejection == run['rejection'],
                    'validation report disagrees with log')
            mode = run['mode']
            if report['command'] == 'verify':
                require(result['action'] == 'verify' and result['witness_loaded'] is False,
                        'verifier loaded witness')
                require(run['verifier_files'] == ['program.bin', 'proof.bin', 'public.bin'],
                        'unexpected verifier files')
                require(run['proof_sha256'] == programs[mode]['saved_proof_sha256'],
                        'verifier used a different proof')
                verified.append(mode)
            elif report['command'] == 'negative':
                require(rejection is not None and 'write-once conflict' in rejection,
                        'missing constraint rejection')
                negatives[mode].append(run['mutation'])
            else:
                raise ValueError('unexpected validation report command')
    require(sorted(verified) == sorted(MODES), 'expected three independent verifications')
    for mode in MODES:
        require(negatives[mode] == targets(programs[mode]['metadata'], profile),
                f'{mode}: incomplete or changed negative cases')
    require(sum(map(len, negatives.values())) == 76, 'expected 76 negative cases')
    print(f'PASS: {len(names)} file hashes, nine proof runs, three witness-free verifications, '
          '76 VM rejections, public statements and timing summary'
          + (', regenerated program/public/witness bytes' if generated else ''))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generated', action='store_true')
    args = parser.parse_args()
    verify(args.generated)
