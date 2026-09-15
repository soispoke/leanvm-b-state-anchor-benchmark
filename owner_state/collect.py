"""Collect 240 owner-binding proofs after quiet-load checks on macOS."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

from owner_state import run

ROOT = run.ROOT
BASE_FOLDER = ROOT / "local-runs/collections"
FOLDER = BASE_FOLDER
PYTHON = Path(sys.executable)

STATE = {}


def save():
    run.write_json(FOLDER/'experiment.json', STATE)


def stage(name, argv):
    print('START '+name, flush=True)
    before = set(run.RESULTS.glob(name+'-*'))
    entry = {'name': name, 'command': [str(x) for x in argv], 'started_at': run.utc()}
    STATE['stages'].append(entry)
    save()
    with (FOLDER/(name+'.log')).open('x') as stream:
        result = subprocess.run([str(x) for x in argv], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    entry.update(exit_code=result.returncode, finished_at=run.utc())
    reports = set(run.RESULTS.glob(name+'-*'))-before
    if len(reports)==1:
        report = reports.pop()
        entry['report'] = str(report.relative_to(ROOT))
        STATE[name] = entry['report']
    save()
    if result.returncode:
        raise RuntimeError(name+' failed; all recorded observations are retained')
    print('DONE '+name, flush=True)


def preflight():
    print('Waiting for three consecutive CPU-idle snapshots >=90% on AC power', flush=True)
    STATE['status'] = 'waiting-for-quiet-load'
    save()
    readings, quiet = [], 0
    for attempt in range(12):
        time.sleep(20)
        probes = {}
        for key, argv in {
            'cpu': ['top', '-l', '2', '-s', '1', '-n', '0'],
            'load': ['sysctl', '-n', 'vm.loadavg'],
            'power': ['pmset', '-g', 'batt'],
            'thermal': ['pmset', '-g', 'therm'],
            'memory': ['vm_stat'],
            'swap': ['sysctl', '-n', 'vm.swapusage'],
        }.items():
            result = subprocess.run(argv, capture_output=True, text=True, check=True)
            probes[key] = result.stdout
        values = re.findall(r'CPU usage:.*?([\d.]+)% idle', probes['cpu'])
        idle = float(values[-1]) if values else 0
        ac = "'AC Power'" in probes['power']
        quiet = quiet+1 if idle>=90 and ac else 0
        readings.append({'at': run.utc(), 'cpu_idle_percent': idle, 'quiet_streak': quiet, **probes})
        run.write_json(FOLDER/'preflight.json', readings)
        print(f'CPU idle {idle:.1f}%, AC {ac}, quiet snapshots {quiet}/3', flush=True)
        if quiet>=3:
            STATE['status'] = 'collecting'
            save()
            return
    raise RuntimeError('Quiet AC preflight not met; no timing batch started')


def measured_inputs():
    """Require the selected guest programs and inputs, independent of native build."""
    manifest = json.loads((ROOT/'owner_state/evidence.json').read_text())
    previous = json.loads((run.inside(ROOT, manifest['reports']['collect'])/'report.json').read_text())
    cases = {}
    for mode in run.MODES:
        _, _, _, hashes = run.case_metadata('cse_dce', mode)
        if hashes != previous['cases']['cse_dce/'+mode]['sha256']:
            raise RuntimeError('Generated program, public input, witness or metadata changed')
        cases['cse_dce/'+mode] = hashes
    return cases


def main():
    global FOLDER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='new attempt directory; defaults to a timestamped subdirectory')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('timing collection requires macOS resource counters and AC power probes')
    STATE.clear()
    STATE.update(status='preparing', started_at=run.utc(), stages=[])
    FOLDER = (args.output or BASE_FOLDER/('attempt-'+run.stamp())).resolve()
    FOLDER.mkdir(parents=True, exist_ok=False)
    script = Path(__file__).read_bytes()
    (FOLDER/'collector.py.txt').write_bytes(script)
    STATE['collector_sha256'] = hashlib.sha256(script).hexdigest()
    keep_awake = None
    try:
        keep_awake = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(os.getpid())])
        binary, runner = run.load_runner()
        cases = measured_inputs()
        conditions = ['cse_dce/'+mode for mode in run.MODES]
        warmups, orders = run.balanced_orders(conditions, 80, 1, 20260911)
        snapshot_names = ('owner_state/CONTRACT.md', 'owner_state/analyze.py', 'owner_state/run.py',
                          'owner_state/test_run.py', 'owner_state/test_analyze.py')
        snapshot_hashes = {}
        for name in snapshot_names:
            data = (ROOT/name).read_bytes()
            target = FOLDER/'plan-sources'/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            snapshot_hashes[name] = hashlib.sha256(data).hexdigest()
        STATE.update(runner=runner, cases=cases, seed=20260911, blocks=80,
                     expected_measured_proofs=240, expected_warmup_proofs=3,
                     warmup_orders=warmups, measured_orders=orders,
                     plan_source_sha256=snapshot_hashes,
                     git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())
        save()
        preflight()
        stage('collect', [PYTHON, '-m', 'owner_state.run', 'collect', '--variants', 'cse_dce',
                          '--blocks', '80', '--warmups', '1', '--seed', '20260911'])
        STATE['status'] = 'verifying'
        save()
        stage('verify', [PYTHON, '-m', 'owner_state.run', 'verify', '--run', STATE['collect']])
        STATE.update(status='complete', finished_at=run.utc())
        save()
        print('Complete: '+str(FOLDER/'experiment.json'), flush=True)
    except BaseException as error:
        STATE.update(status='failed', error=repr(error), finished_at=run.utc())
        save()
        raise
    finally:
        if keep_awake is not None:
            keep_awake.terminate()
            keep_awake.wait()


if __name__=='__main__':
    main()
