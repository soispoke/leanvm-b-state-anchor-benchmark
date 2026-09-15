"""Reproduce owner-binding proofs with exclusive phase and environment records.

  python -m owner_state.run setup
  python -m owner_state.run generate --variants baseline cse_dce
  python -m owner_state.run collect --blocks 8 --warmups 1
  python -m owner_state.run verify --run owner_state/results/collect-<UTC-id>
  python -m owner_state.run negative --variant cse_dce
  python -m owner_state.run validate --run owner_state/results/collect-<UTC-id>

Collection uses eleven Rayon workers and requires recorded AC power. All
processes run sequentially. A power-source or power-setting change stops the
batch, retains every result, and marks timing comparisons inconclusive.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from owner_state.instrumentation import BASE_SHA256, PATCH, check_or_apply, parse_phases
from real_state.run import LOCK_SHA256, PIN, PATCH_SHA256 as WITNESS_PATCH_SHA256, targets

ROOT = Path(__file__).resolve().parent.parent
VM = ROOT / 'vendor/leanVM-b-profiled'
LOCAL = ROOT / 'local-runs/owner-state'
RESULTS = ROOT / 'owner_state/results'
WITNESS_PATCH = ROOT / 'real_state/leanvm-witness-api.patch'
PROFILE_PATCH_SHA256 = '38a63917808288f5e720f79f1b1bad723710fe50a7db03f2098489e89626ac89'
CPU_SHA256 = 'e6264ca07d7ddb16c2b4a618dfd80dc65870dbebbb0f2c359c3f7b06bdaaff82'
WRAPPER = '#[path = "../../../real_state/real_state_bench.rs"]\nmod real_state_bench;\n'
MODES = ('direct', 'rlp', 'ssz')
DEFAULT_VARIANTS = ('baseline', 'cse_dce')
SOURCE_NAMES = (
    'owner_state/run.py', 'owner_state/relation.py', 'owner_state/circuit.py',
    'owner_state/hashes.py', 'owner_state/instrumentation.py', 'owner_state/profile.patch',
    'real_state/real_state_bench.rs', 'real_state/leanvm-witness-api.patch',
    'real_state/run.py', 'real_state/circuit.py', 'real_state/hashes.py',
    'real_state/statement.py', 'real_state/ssz_reference.py',
    'real_state/profile.json', 'real_state/ssz-reference.json',
    'analyze_fixtures.py', 'fixtures/mainnet-0x18bd000.json',
)
GENERATION_NAMES = tuple(name for name in SOURCE_NAMES if name.endswith('.py')
                         and name not in ('owner_state/run.py', 'owner_state/instrumentation.py', 'real_state/run.py'))


def utc():
    return datetime.now(timezone.utc).isoformat()


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def command(argv, *, cwd=ROOT, check=True, env=None):
    return subprocess.run([str(arg) for arg in argv], cwd=cwd, check=check, env=env,
                          text=True, capture_output=True)


def git(*args, check=True):
    return command(['git', *args], cwd=VM, check=check)


def sources(names=SOURCE_NAMES):
    return {name: digest(ROOT / name) for name in names}


def validate_patches():
    if digest(WITNESS_PATCH) != WITNESS_PATCH_SHA256 or digest(PATCH) != PROFILE_PATCH_SHA256:
        raise ValueError('unexpected witness API or profiling patch contents')


def validate_checkout():
    validate_patches()
    if git('rev-parse', 'HEAD').stdout.strip() != PIN:
        raise ValueError('profiled VM is not at the pinned commit')
    if digest(VM / 'Cargo.lock') != LOCK_SHA256:
        raise ValueError('profiled VM Cargo.lock changed')
    if git('diff', 'HEAD', '--name-only').stdout.splitlines() != ['src/cpu/mod.rs']:
        raise ValueError('profiled VM must contain only the recorded CPU changes')
    if digest(VM / 'src/cpu/mod.rs') != CPU_SHA256:
        raise ValueError('profiled CPU differs from the exact two recorded patches')
    if (VM / 'tests/owner_state_bench.rs').read_text() != WRAPPER:
        raise ValueError('unexpected owner_state_bench wrapper')


def setup():
    validate_patches()
    if not VM.exists():
        VM.parent.mkdir(parents=True, exist_ok=True)
        command(['git', 'clone', 'https://github.com/leanEthereum/leanVM-b.git', VM])
    if not (VM / '.git').exists():
        raise ValueError('profiled VM path exists without a Git checkout')
    if git('rev-parse', 'HEAD').stdout.strip() != PIN:
        if git('status', '--porcelain').stdout:
            raise ValueError('refusing to change a checkout with local edits')
        git('checkout', '--detach', PIN)
    changes = set(git('diff', 'HEAD', '--name-only').stdout.splitlines())
    if changes - {'src/cpu/mod.rs'}:
        raise ValueError('refusing to overwrite unrelated upstream edits')
    current = digest(VM / 'src/cpu/mod.rs')
    pristine = hashlib.sha256(git('show', f'{PIN}:src/cpu/mod.rs').stdout.encode()).hexdigest()
    if current == pristine:
        git('apply', '--check', WITNESS_PATCH)
        git('apply', WITNESS_PATCH)
        current = digest(VM / 'src/cpu/mod.rs')
    if current == BASE_SHA256:
        check_or_apply(VM, apply=True)
    elif current != CPU_SHA256:
        raise ValueError('CPU edits do not match the recognized patch stages')
    wrapper = VM / 'tests/owner_state_bench.rs'
    if wrapper.exists() and wrapper.read_text() != WRAPPER:
        raise ValueError('refusing to replace a different test wrapper')
    wrapper.write_text(WRAPPER)
    validate_checkout()
    if os.environ.get('CARGO_TARGET_DIR'):
        raise ValueError('unset CARGO_TARGET_DIR; setup records the profiled checkout target directory')
    build_dir = LOCAL / f'build-{stamp()}'
    build_dir.mkdir(parents=True, exist_ok=False)
    build = command(['cargo', 'test', '--release', '--locked', '--test', 'owner_state_bench',
                     '--no-run', '--message-format=json'], cwd=VM, check=False)
    (build_dir / 'stdout.jsonl').write_text(build.stdout)
    (build_dir / 'stderr.txt').write_text(build.stderr)
    if build.returncode:
        raise ValueError(f'Cargo build failed; see {build_dir}')
    executables = []
    for line in build.stdout.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (entry.get('reason') == 'compiler-artifact' and entry.get('executable')
                and entry.get('target', {}).get('name') == 'owner_state_bench'):
            executables.append(Path(entry['executable']).resolve())
    if not executables:
        raise ValueError('Cargo did not report the benchmark executable')
    binary = executables[-1]
    if not binary.is_relative_to(VM / 'target'):
        raise ValueError('unexpected executable location')
    manifest = {
        'schema': 'leanvm-owner-runner-v1', 'upstream_commit': PIN,
        'cargo_lock_sha256': LOCK_SHA256, 'vm_cpu_sha256': CPU_SHA256,
        'witness_patch_sha256': WITNESS_PATCH_SHA256, 'profile_patch_sha256': PROFILE_PATCH_SHA256,
        'wrapper_sha256': digest(wrapper), 'rust_runner_sha256': digest(ROOT / 'real_state/real_state_bench.rs'),
        'binary': str(binary.relative_to(ROOT)), 'binary_sha256': digest(binary),
        'rustc': command(['rustc', '-Vv']).stdout.strip(), 'cargo': command(['cargo', '-V']).stdout.strip(),
        'build_logs': str(build_dir.relative_to(ROOT)), 'built_at': utc(),
    }
    validate_checkout()
    write_json(LOCAL / 'runner.json', manifest)
    print(json.dumps(manifest), flush=True)
    return binary, manifest


def load_runner():
    path = LOCAL / 'runner.json'
    if not path.exists():
        raise ValueError('runner manifest is missing; run python -m owner_state.run setup')
    manifest = json.loads(path.read_text())
    validate_checkout()
    binary = (ROOT / manifest['binary']).resolve()
    expected = {
        'schema': 'leanvm-owner-runner-v1', 'upstream_commit': PIN,
        'cargo_lock_sha256': LOCK_SHA256, 'vm_cpu_sha256': CPU_SHA256,
        'witness_patch_sha256': WITNESS_PATCH_SHA256, 'profile_patch_sha256': PROFILE_PATCH_SHA256,
        'wrapper_sha256': digest(VM / 'tests/owner_state_bench.rs'),
        'rust_runner_sha256': digest(ROOT / 'real_state/real_state_bench.rs'),
    }
    if (any(manifest.get(key) != value for key, value in expected.items())
            or not binary.is_relative_to(VM / 'target') or not binary.is_file()
            or not os.access(binary, os.X_OK) or digest(binary) != manifest.get('binary_sha256')):
        raise ValueError('runner identity changed; rerun setup')
    return binary, manifest


def process_environment(directory, action, mutation=None):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('REAL_STATE_') and key not in ('LEANVM_PROFILE', 'LEANVM_PHASE_PROFILE')
           and not key.startswith('FLOCK_')}
    env.update(REAL_STATE_DIR=str(directory), REAL_STATE_ACTION=action,
               RAYON_NUM_THREADS='11', LEANVM_PHASE_PROFILE='1')
    if mutation:
        env['REAL_STATE_MUTATE_CELL'] = str(mutation['cell'])
        if mutation.get('replacement') is not None:
            env['REAL_STATE_MUTATE_VALUE'] = str(mutation['replacement'])
    return env


def probe(argv):
    try:
        run = subprocess.run(argv, text=True, capture_output=True, timeout=20)
        return {'returncode': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'returncode': None, 'error': str(error)}


def power_source(text):
    match = re.search(r"Now drawing from '([^']+)'", text)
    return match.group(1) if match else None


def environment():
    data = {'recorded_utc': utc(), 'platform': platform.platform(), 'python': sys.version,
            'rayon_num_threads': 11, 'rustc': probe(['rustc', '-Vv']), 'cargo': probe(['cargo', '-V']),
            'uptime': probe(['uptime']), 'frequency_temperature':
            'CPU frequency and temperature are not measured; pmset thermal status is not a sensor reading.'}
    if platform.system() == 'Darwin':
        data.update(power=probe(['pmset', '-g', 'batt']), power_settings=probe(['pmset', '-g', 'custom']),
                    thermal=probe(['pmset', '-g', 'therm']),
                    hardware=probe(['sysctl', 'hw.memsize', 'hw.ncpu', 'machdep.cpu.brand_string']),
                    os_version=probe(['sw_vers']), load=probe(['sysctl', 'vm.loadavg']))
    else:
        data.update(power={'returncode': None, 'error': 'AC-source probe is implemented for macOS only'},
                    power_settings={'returncode': None})
    data['power_source'] = power_source(data['power'].get('stdout', ''))
    return data


def check_environment(observed, reference=None):
    if observed.get('power_source') != 'AC Power' or observed['power'].get('returncode') != 0:
        raise ValueError('AC power is not confirmed; batch stopped and timing comparisons are inconclusive')
    settings = observed.get('power_settings', {})
    if settings.get('returncode') != 0:
        raise ValueError('power mode/settings could not be recorded; batch stopped')
    if reference:
        for key in ('power_settings', 'rustc', 'cargo', 'hardware', 'os_version'):
            if observed.get(key) != reference.get(key):
                raise ValueError(f'{key} changed during the batch; timing comparisons are inconclusive')


def balanced_orders(conditions, blocks, warmups, seed):
    """Randomized Williams rows; odd sizes include reversed rows for balance."""
    if blocks < 1 or warmups < 0 or not conditions or len(set(conditions)) != len(conditions):
        raise ValueError('positive blocks, nonnegative warmups, and distinct conditions required')
    rng = random.Random(seed)
    labels = list(conditions)
    rng.shuffle(labels)
    n = len(labels)
    pattern = [0]
    for i in range(1, n):
        pattern.append((i + 1) // 2 if i % 2 else n - i // 2)
    rows = [[labels[(value + shift) % n] for value in pattern] for shift in range(n)]
    if n > 1 and n % 2:
        rows += [list(reversed(row)) for row in rows]
    orders = []
    while len(orders) < blocks:
        indices = list(range(len(rows)))
        rng.shuffle(indices)
        orders.extend(rows[i] for i in indices[:blocks-len(orders)])
    warmup_orders = []
    for _ in range(warmups):
        row = list(conditions)
        rng.shuffle(row)
        warmup_orders.append(row)
    return warmup_orders, orders


def parse_output(text):
    records = re.findall(r'(?:^|\b)RESULT (\{[^\r\n]*\})', text, re.MULTILINE)
    rejected = re.findall(r'(?:^|\b)(REJECTED [^\r\n]*)', text, re.MULTILINE)
    if len(records) > 1 or len(rejected) > 1 or (records and rejected):
        raise ValueError('ambiguous result records from a VM process')
    return (json.loads(records[0]) if records else None, rejected[0] if rejected else None)


def parse_memory(text):
    result = {}
    for label, key in (('maximum resident set size', 'max_rss_bytes'),
                       ('peak memory footprint', 'peak_footprint_bytes')):
        matches = re.findall(r'^\s*(\d+)\s+' + re.escape(label) + r'\s*$', text, re.MULTILINE)
        if len(matches) == 1:
            result[key] = int(matches[0])
    return result


def run_process(binary, directory, action, log, *, mutation=None, measure_memory=True):
    argv = [str(binary), 'real_state_bench::real_state_benchmark', '--exact', '--nocapture', '--test-threads=1']
    measured = measure_memory and platform.system() == 'Darwin'
    if measured:
        argv = ['/usr/bin/time', '-l', *argv]
    start = time.perf_counter()
    with log.open('x') as stream:
        run = subprocess.run(argv, cwd=ROOT, env=process_environment(directory, action, mutation),
                             stdout=stream, stderr=subprocess.STDOUT)
    entry = {'exit_code': run.returncode, 'process_seconds': time.perf_counter() - start,
             'log': log.name, 'log_sha256': digest(log),
             'memory_measurement': 'macos-time-l' if measured else None}
    text = log.read_text()
    entry['memory'] = parse_memory(text) if measured else {}
    try:
        entry['result'], entry['rejection'] = parse_output(text)
        if action == 'prove' and entry['result']:
            outer = entry['result']['prove_including_execute_ms']
            # The unchanged Rust runner prints the outer timer to 0.001 ms.
            # Preserve its rounded value; allow only this known rounding error.
            phases = parse_phases(text)
            residual = outer - phases['internal_total_ms']
            if residual < -0.000500001:
                raise ValueError('internal timing exceeds outer prove timer beyond rounding precision')
            phases['outer_prove_residual_ms'] = residual
            phases['outer_timer_resolution_ms'] = 0.001
            entry['phases'] = phases
    except (ValueError, KeyError, TypeError) as error:
        entry['parse_error'] = str(error)
    return entry


def case_metadata(variant, mode):
    directory = LOCAL / variant / mode
    meta = json.loads((directory / 'program.json').read_text())
    profile = json.loads((ROOT / 'real_state/profile.json').read_text())
    expected_profile = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
    if (meta.get('relation') != 'owner-v1' or meta.get('variant') != variant or meta.get('mode') != mode
            or meta.get('profile_sha256') != expected_profile):
        raise ValueError(f'{variant}/{mode}: generated program does not match the relation/profile')
    if (directory / 'public.bin').read_bytes() != bytes.fromhex(meta['public_digest'][2:]):
        raise ValueError('public input bytes disagree with recorded digest')
    with (directory / 'program.bin').open('rb') as stream:
        header = stream.read(16)
    cells, count = struct.unpack('<II', header[8:])
    if header[:8] != b'LVMSTATE' or cells != meta['memory_cells'] or count != sum(meta['op_counts'].values()):
        raise ValueError('generated program header disagrees with metadata')
    files = {name: digest(directory / name) for name in ('program.bin', 'public.bin', 'witness.bin', 'program.json')}
    return directory, meta, profile, files


def expected_counts(meta):
    counts = meta['op_counts']
    return [counts['xor'], counts['mul'], counts['set'] + 3, 0, 1, 0]


def validate_result(entry, action, meta, mutation=None):
    if entry.get('parse_error') or entry.get('exit_code') != 0:
        return False
    if entry.get('memory_measurement') == 'macos-time-l':
        memory = entry.get('memory', {})
        if any(isinstance(memory.get(key), bool) or not isinstance(memory.get(key), int)
               or memory[key] <= 0 for key in ('max_rss_bytes', 'peak_footprint_bytes')):
            return False
    if mutation:
        rejection = entry.get('rejection') or ''
        return (f"mutation_cell={mutation['cell']} " in rejection
                and 'write-once conflict' in rejection and not entry.get('result'))
    result = entry.get('result') or {}
    if (result.get('action') != action or result.get('counts') != expected_counts(meta)
            or result.get('cycles') != sum(expected_counts(meta))
            or result.get('cells') != meta['memory_cells'] + 3):
        return False
    if action == 'prove':
        return (result.get('wrong_public_rejected') is True and result.get('mutated_proof_rejected') is True
                and 'phases' in entry)
    return action != 'verify' or result.get('witness_loaded') is False


def create_report(kind, *, runner=None, variants=None):
    destination = RESULTS / f'{kind}-{stamp()}'
    destination.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'leanvm-owner-run-v1', 'command': kind, 'status': 'running',
              'started_at': utc(), 'source_sha256': sources(), 'runner': runner,
              'variants': list(variants or ()), 'rayon_num_threads': 11,
              'cases': {}, 'runs': [], 'timing_scope': 'outer prove call includes execution, witness build and return cleanup',
              'temperature_frequency_measured': False, 'environment_checks_passed': False}
    # Small source snapshots make historical runs checkable after later edits.
    for name in report['source_sha256']:
        target = destination / 'sources' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    write_json(destination / 'report.json', report)
    return destination, report


def finish_report(destination, report, error=None):
    report['finished_at'] = utc()
    report['status'] = 'failed' if error else 'complete'
    if error:
        report['error'] = str(error)
    write_json(destination / 'report.json', report)
    print(f'Report: {destination / "report.json"}', flush=True)


def snapshot_case(destination, report, variant, mode):
    directory, meta, profile, files = case_metadata(variant, mode)
    key = f'{variant}/{mode}'
    if key not in report['cases']:
        folder = destination / 'cases' / variant / mode
        folder.mkdir(parents=True)
        for name in ('program.json', 'public.bin'):
            shutil.copyfile(directory / name, folder / name)
        report['cases'][key] = {'metadata': meta, 'sha256': files,
                               'generated_directory': str(directory.relative_to(ROOT))}
    elif report['cases'][key]['sha256'] != files:
        raise ValueError(f'{key}: generated inputs changed during run')
    return directory, meta, profile


def generate(variants, modes=MODES):
    from owner_state.relation import build
    destination, report = create_report('generate', variants=variants)
    error = None
    try:
        profile = json.loads((ROOT / 'real_state/profile.json').read_text())
        for variant in variants:
            for mode in modes:
                start = time.perf_counter()
                circuit, meta = build(mode, profile, variant=variant)
                meta['generation_source_sha256'] = sources(GENERATION_NAMES)
                circuit.export(LOCAL / variant / mode, meta)
                del circuit
                gc.collect()
                snapshot_case(destination, report, variant, mode)
                entry = {'variant': variant, 'mode': mode, 'generation_seconds': time.perf_counter()-start}
                report['runs'].append(entry)
                write_json(destination / 'report.json', report)
                print(json.dumps(entry), flush=True)
    except BaseException as caught:
        error = caught
        raise
    finally:
        finish_report(destination, report, error)
    return destination


def collect(variants=DEFAULT_VARIANTS, *, blocks=8, warmups=1, seed=20260910):
    binary, runner = load_runner()
    conditions = [f'{variant}/{mode}' for variant in variants for mode in MODES]
    warmup_orders, orders = balanced_orders(conditions, blocks, warmups, seed)
    destination, report = create_report('collect', runner=runner, variants=variants)
    report.update(seed=seed, blocks=blocks, warmups_per_condition=warmups,
                  warmup_orders=warmup_orders, measured_orders=orders,
                  order_method='randomized Williams rows, complete cycles balance positions and preceding conditions',
                  sample_policy='all measured samples retained; warmups explicitly labeled and excluded from estimates')
    error = None
    reference = None
    try:
        for variant in variants:
            for mode in MODES:
                snapshot_case(destination, report, variant, mode)
        for mode in MODES:
            inputs = {report['cases'][f'{variant}/{mode}']['sha256']['public.bin'] for variant in variants}
            if len(inputs) != 1:
                raise ValueError(f'{mode}: compiler variants do not prove identical public statements')
        schedule = [('warmup', i+1, order) for i, order in enumerate(warmup_orders)]
        schedule += [('measured', i+1, order) for i, order in enumerate(orders)]
        for kind, block, order in schedule:
            for position, condition in enumerate(order, 1):
                if sources() != report['source_sha256']:
                    raise ValueError('experiment source changed during collection')
                variant, mode = condition.split('/')
                directory = LOCAL / variant / mode
                meta = report['cases'][condition]['metadata']
                prefix = f'{len(report["runs"])+1:03}-{kind}-{block:02}-{variant}-{mode}'
                entry = {'condition': condition, 'variant': variant, 'mode': mode,
                         'kind': kind, 'block': block, 'position': position, 'started_at': utc(), 'passed': False}
                report['runs'].append(entry)
                before = environment()
                write_json(destination / f'{prefix}-before.json', before)
                entry['environment_before'] = f'{prefix}-before.json'
                entry['environment_before_sha256'] = digest(destination / entry['environment_before'])
                write_json(destination / 'report.json', report)
                check_environment(before, reference)
                if reference is None:
                    reference = before
                try:
                    entry.update(run_process(binary, directory, 'prove', destination / f'{prefix}.log'))
                finally:
                    after = environment()
                    write_json(destination / f'{prefix}-after.json', after)
                    entry['environment_after'] = f'{prefix}-after.json'
                    entry['environment_after_sha256'] = digest(destination / entry['environment_after'])
                    entry['finished_at'] = utc()
                    write_json(destination / 'report.json', report)
                entry['passed'] = validate_result(entry, 'prove', meta)
                check_environment(after, reference)
                entry['environment_valid'] = True
                if not entry['passed']:
                    raise ValueError(f'{condition} proof or phase validation failed; see {entry.get("log")}')
                proof = directory / 'proof.bin'
                entry['proof_sha256'] = digest(proof)
                if proof.stat().st_size != entry['result']['proof_bytes']:
                    raise ValueError('serialized proof size does not match the VM result')
                if kind == 'measured' and 'saved_proof' not in report['cases'][condition]:
                    target = destination / 'proofs' / f'{variant}-{mode}.bin'
                    target.parent.mkdir(exist_ok=True)
                    shutil.copyfile(proof, target)
                    report['cases'][condition].update(saved_proof=str(target.relative_to(destination)),
                                                     proof_sha256=digest(target))
                write_json(destination / 'report.json', report)
                print(json.dumps({'condition': condition, 'kind': kind, 'block': block,
                                  'prove_ms': entry['result']['prove_including_execute_ms'], 'passed': True}), flush=True)
        for variant in variants:
            for mode in MODES:
                snapshot_case(destination, report, variant, mode)
        if sources() != report['source_sha256']:
            raise ValueError('experiment source changed during collection')
        validate_checkout()
        if digest(binary) != runner['binary_sha256']:
            raise ValueError('runner binary changed during collection')
        report['environment_checks_passed'] = True
    except BaseException as caught:
        error = caught
        raise
    finally:
        finish_report(destination, report, error)
    return destination


def negative(variant='cse_dce', modes=MODES):
    binary, runner = load_runner()
    destination, report = create_report('negative', runner=runner, variants=[variant])
    report['negative_scope'] = 'interpreter witness rejection after compilation; not forged-proof verification'
    error = None
    try:
        write_json(destination / 'environment.json', environment())
        for mode in modes:
            directory, meta, profile = snapshot_case(destination, report, variant, mode)
            secret = next(value for value in meta['witness_ranges'] if value['name'] == 'secret')
            mutations = targets(meta, profile) + [
                {'tag': 'secret-first-bit', 'cell': secret['base'], 'replacement': None},
                {'tag': 'secret-nonboolean', 'cell': secret['base'], 'replacement': 2},
                {'tag': 'secret-last-bit', 'cell': secret['base'] + secret['length'] - 1, 'replacement': None},
            ]
            for mutation in mutations:
                log = destination / f'{mode}-{mutation["tag"]}.log'
                entry = run_process(binary, directory, 'execute', log, mutation=mutation, measure_memory=False)
                entry.update(variant=variant, mode=mode, mutation=mutation,
                             passed=validate_result(entry, 'execute', meta, mutation))
                report['runs'].append(entry)
                write_json(destination / 'report.json', report)
                print(json.dumps({'mode': mode, 'mutation': mutation['tag'], 'passed': entry['passed']}), flush=True)
        if not all(entry['passed'] for entry in report['runs']):
            raise ValueError('at least one malformed witness was not rejected')
    except BaseException as caught:
        error = caught
        raise
    finally:
        finish_report(destination, report, error)
    return destination


def inside(directory, relative):
    path = (directory / relative).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError('evidence path escapes its run directory')
    return path


def validate_evidence(directory):
    directory = directory.resolve()
    report = json.loads((directory / 'report.json').read_text())
    if report.get('schema') != 'leanvm-owner-run-v1' or report.get('status') != 'complete':
        raise ValueError('run is not a completed owner-binding evidence set')
    for name, expected in report['source_sha256'].items():
        if digest(inside(directory, 'sources/' + name)) != expected:
            raise ValueError(f'source snapshot changed: {name}')
    for condition, case in report['cases'].items():
        for name in ('program.json', 'public.bin'):
            path = inside(directory, f'cases/{condition}/{name}')
            if digest(path) != case['sha256'][name]:
                raise ValueError(f'case snapshot changed: {condition}/{name}')
        metadata = json.loads(inside(directory, f'cases/{condition}/program.json').read_text())
        if metadata != case['metadata']:
            raise ValueError(f'embedded metadata disagrees with case snapshot: {condition}')
        if case.get('saved_proof') and digest(inside(directory, case['saved_proof'])) != case['proof_sha256']:
            raise ValueError(f'saved proof changed: {condition}')
    if report['command'] == 'collect':
        conditions = [f'{variant}/{mode}' for variant in report['variants'] for mode in MODES]
        warmups, orders = balanced_orders(conditions, report['blocks'], report['warmups_per_condition'], report['seed'])
        if report['warmup_orders'] != warmups or report['measured_orders'] != orders or set(report['cases']) != set(conditions):
            raise ValueError('recorded conditions or schedule differ from the declared design')
        observed = [('warmup', index+1, condition) for index, order in enumerate(report['warmup_orders']) for condition in order]
        observed += [('measured', index+1, condition) for index, order in enumerate(report['measured_orders']) for condition in order]
        actual = [(entry['kind'], entry['block'], entry['condition']) for entry in report['runs']]
        if observed != actual or not report.get('environment_checks_passed'):
            raise ValueError('measurement schedule is incomplete or environmental comparison failed')
    reference = None
    for entry in report['runs']:
        if 'log' not in entry:
            continue
        log = inside(directory, entry['log'])
        if digest(log) != entry['log_sha256']:
            raise ValueError(f'raw log changed: {entry["log"]}')
        if report['command'] in ('collect', 'verify', 'negative'):
            result, rejected = parse_output(log.read_text())
            if result != entry.get('result') or rejected != entry.get('rejection'):
                raise ValueError('raw result and report disagree')
            condition = entry.get('condition') or f'{entry["variant"]}/{entry["mode"]}'
            meta = report['cases'][condition]['metadata']
            action = {'collect': 'prove', 'verify': 'verify', 'negative': 'execute'}[report['command']]
            mutation = entry.get('mutation') if report['command'] == 'negative' else None
            if report['command'] == 'negative' and mutation is None:
                raise ValueError('negative result lacks its witness mutation')
            if not entry.get('passed') or not validate_result(entry, action, meta, mutation):
                raise ValueError('failed semantic result in completed evidence')
            if report['command'] == 'verify' and entry.get('verifier_files') != ['program.bin', 'proof.bin', 'public.bin']:
                raise ValueError('independent verification did not use exactly the three allowed files')
        if report['command'] == 'collect':
            parsed = parse_phases(log.read_text())
            if any(entry['phases'].get(key) != value for key, value in parsed.items()):
                raise ValueError('raw phases and report disagree')
            for key in ('environment_before', 'environment_after'):
                path = inside(directory, entry[key])
                if digest(path) != entry[key + '_sha256']:
                    raise ValueError('environment record changed')
                env = json.loads(path.read_text())
                check_environment(env, reference)
                reference = reference or env
    return report


def verify(directory):
    source = directory.resolve()
    prior = validate_evidence(source)
    if prior['command'] != 'collect':
        raise ValueError('verify requires a completed collection with saved proofs')
    binary, runner = load_runner()
    destination, report = create_report('verify', runner=runner, variants=prior['variants'])
    report.update(source_run=str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
                  source_report_sha256=digest(source / 'report.json'))
    error = None
    try:
        for condition, case in prior['cases'].items():
            variant, mode = condition.split('/')
            directory, meta, _ = snapshot_case(destination, report, variant, mode)
            if digest(directory / 'program.bin') != case['sha256']['program.bin']:
                raise ValueError('regenerated program differs from the saved proof program')
            with tempfile.TemporaryDirectory(prefix='leanvm-owner-verify-') as temporary:
                clean = Path(temporary)
                shutil.copyfile(directory / 'program.bin', clean / 'program.bin')
                shutil.copyfile(inside(source, f'cases/{condition}/public.bin'), clean / 'public.bin')
                shutil.copyfile(inside(source, case['saved_proof']), clean / 'proof.bin')
                entry = run_process(binary, clean, 'verify', destination / f'{variant}-{mode}.log')
                entry.update(condition=condition, variant=variant, mode=mode,
                             verifier_files=sorted(path.name for path in clean.iterdir()),
                             proof_sha256=digest(clean / 'proof.bin'), passed=validate_result(entry, 'verify', meta))
            if entry['verifier_files'] != ['program.bin', 'proof.bin', 'public.bin']:
                raise ValueError('unexpected verifier input files')
            report['runs'].append(entry)
            write_json(destination / 'report.json', report)
            print(json.dumps(entry), flush=True)
            if not entry['passed']:
                raise ValueError(f'{condition}: independent proof verification failed')
    except BaseException as caught:
        error = caught
        raise
    finally:
        finish_report(destination, report, error)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('setup', 'generate', 'collect', 'verify', 'negative', 'validate', 'env'))
    parser.add_argument('--variants', nargs='+', default=list(DEFAULT_VARIANTS))
    parser.add_argument('--variant', default='cse_dce', help='compiler variant for negative checks')
    parser.add_argument('--mode', choices=(*MODES, 'all'), default='all')
    parser.add_argument('--blocks', type=int, default=8)
    parser.add_argument('--warmups', type=int, default=1)
    parser.add_argument('--seed', type=int, default=20260910)
    parser.add_argument('--run', type=Path)
    args = parser.parse_args()
    modes = MODES if args.mode == 'all' else (args.mode,)
    if args.blocks < 1 or args.warmups < 0:
        parser.error('--blocks must be positive and --warmups nonnegative')
    from owner_state.relation import VARIANTS
    if len(set(args.variants)) != len(args.variants) or any(value not in VARIANTS for value in args.variants):
        parser.error('--variants must be distinct known compiler variants')
    if args.variant not in VARIANTS:
        parser.error('unknown --variant')
    if args.command in ('verify', 'validate') and args.run is None:
        parser.error('--run is required')
    try:
        if args.command == 'setup':
            setup()
        elif args.command == 'generate':
            generate(args.variants, modes)
        elif args.command == 'collect':
            collect(args.variants, blocks=args.blocks, warmups=args.warmups, seed=args.seed)
        elif args.command == 'negative':
            negative(args.variant, modes)
        elif args.command == 'verify':
            verify(args.run)
        elif args.command == 'validate':
            report = validate_evidence(args.run)
            print(json.dumps({'validated': str(args.run), 'runs': len(report['runs'])}))
        else:
            print(json.dumps(environment(), indent=2))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == '__main__':
    main()
