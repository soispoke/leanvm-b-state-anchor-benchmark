"""Shared native runner setup, output parsing and malformed-witness targets.

python -m real_state.run setup
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VM = ROOT / 'vendor/leanVM-b'
RUNS = ROOT / 'local-runs/real-state'
PIN = '8494c5d5df323f2b97ed89272942a4bee6247078'
LOCK_SHA256 = '0c60e536366da5198d5536c3fdade9a7f20d48d070ee3093758f4b73712a2bf6'
PATCH_SHA256 = '365a65f9554c2c326752df19752f7df3661a074ae5220b101f1a774e2b9682b1'
PATCH = ROOT / 'real_state/leanvm-witness-api.patch'
WRAPPER = '#[path = "../../../real_state/real_state_bench.rs"]\nmod real_state_bench;\n'
MODES = ('direct', 'rlp', 'ssz')
SOURCES = (
    'real_state/run.py', 'real_state/real_state_bench.rs',
    'real_state/leanvm-witness-api.patch', 'real_state/circuit.py',
    'real_state/hashes.py', 'real_state/statement.py',
    'real_state/profile.json', 'real_state/ssz-reference.json',
    'analyze_fixtures.py', 'fixtures/mainnet-0x18bd000.json',
)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_identity():
    return {name: digest(ROOT / name) for name in SOURCES}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def command(args, *, cwd=ROOT, check=True):
    return subprocess.run([str(arg) for arg in args], cwd=cwd, check=check,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def git(*args, check=True):
    return command(['git', *args], cwd=VM, check=check)


def tracked_changes():
    return git('diff', '--name-only', 'HEAD', '--').stdout.splitlines()


def validate_checkout():
    if git('rev-parse', 'HEAD').stdout.strip() != PIN:
        raise ValueError('leanVM-b is not at the pinned commit; run setup')
    if digest(VM / 'Cargo.lock') != LOCK_SHA256:
        raise ValueError('pinned Cargo.lock hash mismatch')
    if digest(PATCH) != PATCH_SHA256:
        raise ValueError('unexpected witness API patch contents')
    if tracked_changes() != ['src/cpu/mod.rs']:
        raise ValueError('leanVM-b must contain only the known witness API change')
    actual = git('diff', '--no-ext-diff', '--no-color', '--unified=3', '--abbrev=8',
                 '--src-prefix=a/', '--dst-prefix=b/', 'HEAD', '--', 'src/cpu/mod.rs').stdout
    if actual != PATCH.read_text():
        raise ValueError('tracked leanVM-b changes do not exactly match the known API patch')
    if (VM / 'tests/real_state_bench.rs').read_text() != WRAPPER:
        raise ValueError('unexpected real_state_bench test wrapper contents')


def setup():
    if digest(PATCH) != PATCH_SHA256:
        raise ValueError('unexpected witness API patch contents')
    if not VM.exists():
        VM.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', 'https://github.com/leanEthereum/leanVM-b.git', str(VM)], check=True)
    if not (VM / '.git').exists():
        raise ValueError('vendor/leanVM-b exists but is not a Git checkout')
    if git('rev-parse', 'HEAD').stdout.strip() != PIN:
        if tracked_changes():
            raise ValueError('refusing to change the upstream revision with tracked local edits')
        git('checkout', '--detach', PIN)
    if digest(VM / 'Cargo.lock') != LOCK_SHA256:
        raise ValueError('pinned Cargo.lock hash mismatch')
    if set(tracked_changes()) - {'src/cpu/mod.rs'}:
        raise ValueError('unexpected tracked upstream changes')
    if git('apply', '--reverse', '--check', str(PATCH), check=False).returncode:
        if tracked_changes():
            raise ValueError('upstream edits are not the known witness API patch')
        git('apply', '--check', str(PATCH))
        git('apply', str(PATCH))
    wrapper = VM / 'tests/real_state_bench.rs'
    if wrapper.exists() and wrapper.read_text() != WRAPPER:
        raise ValueError('refusing to overwrite a different test wrapper')
    if not wrapper.exists():
        wrapper.write_text(WRAPPER)
    validate_checkout()
    target = os.environ.get('CARGO_TARGET_DIR')
    if target and (VM / target).resolve() != VM / 'target':
        raise ValueError('setup uses the checkout target directory; unset CARGO_TARGET_DIR')
    build = command(['cargo', 'test', '--release', '--locked', '--test',
                     'real_state_bench', '--no-run', '--message-format=json'], cwd=VM, check=False)
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / 'build.jsonl').write_text(build.stdout)
    (RUNS / 'build.stderr.txt').write_text(build.stderr)
    if build.returncode:
        raise ValueError('Cargo build failed; see local-runs/real-state/build.jsonl and build.stderr.txt')
    executables = []
    for line in build.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get('reason') == 'compiler-artifact' and event.get('executable'):
            if event.get('target', {}).get('name') == 'real_state_bench':
                executables.append(Path(event['executable']).resolve())
    if not executables:
        raise ValueError('Cargo did not report the real_state_bench executable')
    binary = executables[-1]
    if not binary.is_relative_to(VM / 'target'):
        raise ValueError('build must use the checkout target directory; unset CARGO_TARGET_DIR')
    validate_checkout()
    manifest = {
        'schema': 'leanvm-real-state-runner-v1', 'upstream_commit': PIN,
        'cargo_lock_sha256': LOCK_SHA256, 'source_sha256': source_identity(),
        'vm_cpu_sha256': digest(VM / 'src/cpu/mod.rs'),
        'wrapper_sha256': digest(wrapper), 'binary': str(binary.relative_to(ROOT)),
        'binary_sha256': digest(binary),
        'rustc': command(['rustc', '-Vv']).stdout.strip(),
        'cargo': command(['cargo', '-V']).stdout.strip(),
        'built_at': datetime.now(timezone.utc).isoformat(),
    }
    write_json(RUNS / 'runner.json', manifest)
    print(json.dumps(manifest, indent=2))


def parse_output(text):
    # libtest can print the test name and our first message on the same line.
    prefix = r'^(?:test real_state_bench::real_state_benchmark \.\.\. )?'
    records = re.findall(prefix + r'RESULT (\{[^\r\n]*\})$', text, re.MULTILINE)
    if len(records) > 1:
        raise ValueError('multiple VM result records in one process')
    rejected = re.findall(prefix + r'(REJECTED [^\r\n]*)$', text, re.MULTILINE)
    return (json.loads(records[0]) if records else None,
            rejected[0] if rejected else None)


def targets(meta, profile):
    """Select explicit byte/bit mutations; these test interpreter rejection."""
    ranges = {entry['name']: entry for entry in meta['witness_ranges']}
    result = []

    def add(name, tag, byte=0, bit=0, replacement=None):
        entry = ranges[name]
        offset = 8 * byte + bit
        if not 0 <= bit < 8 or not 0 <= offset < entry['length']:
            raise ValueError(f'mutation offset outside {name}')
        result.append({'tag': tag, 'range': name, 'cell': entry['base'] + offset,
                       'byte_offset': byte, 'bit_offset': bit, 'replacement': replacement})

    def prefix_length(length):
        return 1 if length < 56 else 1 + (length.bit_length() + 7) // 8

    def size(layout):
        if layout['kind'] == 'bytes':
            length = layout['length']
            return length + (0 if layout['bare'] else prefix_length(length))
        length = sum(size(child) for child in layout['children'])
        return prefix_length(length) + length

    def payload_offset(layout):
        if layout['kind'] == 'bytes':
            return 0 if layout['bare'] else prefix_length(layout['length'])
        return prefix_length(sum(size(child) for child in layout['children']))

    def child_payload(layout, index):
        return payload_offset(layout) + sum(size(x) for x in layout['children'][:index]) + payload_offset(layout['children'][index])

    add('address', 'nonboolean-input', replacement=2)
    for name in ('address', 'slot', 'value', 'state_root'):
        add(name, f'{name}-bit')
    for kind in ('account', 'storage'):
        layouts = profile[kind]['nodes']
        for i in range(len(layouts)):
            add(f'{kind}_node_{i:02}', f'{kind}-node-{i:02}-rlp-prefix')
        last = layouts[-1]
        if len(last['children']) == 2:
            name = f'{kind}_node_{len(layouts) - 1:02}'
            start = child_payload(last, 0)
            add(name, f'{kind}-compact-flags', start, 4)
            add(name, f'{kind}-compact-suffix', start + last['children'][0]['length'] - 1)
    account_leaf = profile['account']['nodes'][-1]
    if len(account_leaf['children']) == 2:
        start = child_payload(account_leaf, 1) + child_payload(profile['account_value'], 2)
        add(f"account_node_{len(profile['account']['nodes']) - 1:02}", 'account-storage-root', start)
    storage_last = f"storage_node_{len(profile['storage']['nodes']) - 1:02}"
    add(storage_last, 'storage-leaf-last-byte', ranges[storage_last]['length'] // 8 - 1)
    if 'header' in ranges:
        add('header', 'header-rlp-prefix')
        add('header', 'header-state-root', child_payload(profile['header'], 3))
    for name in ranges:
        if name.startswith('ssz_sibling_'):
            add(name, name.replace('_', '-') + '-bit')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('setup',))
    parser.parse_args()
    setup()


if __name__ == '__main__':
    main()
