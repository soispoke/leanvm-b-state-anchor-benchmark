"""Run the predeclared 80-round optimized-anchor collection, then verify proofs."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

BASE_FOLDER = Path(__file__).resolve().parent
FOLDER = BASE_FOLDER
ROOT = BASE_FOLDER.parents[2]
PYTHON = Path(sys.executable)
sys.path.insert(0, str(ROOT))
from owner_state import run

STATE = {'status': 'preparing', 'started_at': run.utc(), 'stages': []}


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


def main():
    global FOLDER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='new attempt directory; defaults to a timestamped subdirectory')
    args = parser.parse_args()
    FOLDER = (args.output or BASE_FOLDER/('attempt-'+run.stamp())).resolve()
    FOLDER.mkdir(parents=True, exist_ok=False)
    script = Path(__file__).read_bytes()
    (FOLDER/'orchestrate.py').write_bytes(script)
    STATE['orchestrator_sha256'] = hashlib.sha256(script).hexdigest()
    keep_awake = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(os.getpid())])
    try:
        binary, runner = run.load_runner()
        previous = json.loads((ROOT/'owner_state/results/collect-20260911T074413358669Z/report.json').read_text())
        if runner['binary_sha256'] != previous['runner']['binary_sha256']:
            raise RuntimeError('Native executable differs from the earlier recorded setup')
        cases = {}
        for mode in run.MODES:
            directory, meta, profile, hashes = run.case_metadata('cse_dce', mode)
            if hashes != previous['cases']['cse_dce/'+mode]['sha256']:
                raise RuntimeError('Generated program, public input, witness or metadata changed')
            cases['cse_dce/'+mode] = hashes
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
        keep_awake.terminate()
        keep_awake.wait()


if __name__=='__main__':
    main()
