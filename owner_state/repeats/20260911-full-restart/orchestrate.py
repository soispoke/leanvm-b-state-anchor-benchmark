from pathlib import Path
import datetime,json,re,subprocess,sys,time
root=Path('/private/tmp/leanvm-b-state-anchor-benchmark-publish-20260910')
folder=root/'owner_state/repeats/20260911-full-restart'
python=root/'.venv/bin/python'
state={'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'running','stages':[]}
def save():
 (folder/'restart.json').write_text(json.dumps(state,indent=2)+'\n')
def stage(name,args):
 print('START '+name,flush=True)
 entry={'name':name,'command':[str(a) for a in args],'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 state['stages'].append(entry);save()
 with (folder/(name+'.log')).open('w') as out:
  result=subprocess.run([str(a) for a in args],cwd=root,stdout=out,stderr=subprocess.STDOUT)
 entry.update(exit_code=result.returncode,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());save()
 if result.returncode:raise RuntimeError(name+' failed; inspect its log')
 print('DONE '+name,flush=True)
def report(kind):
 dirs=sorted((root/'owner_state/results').glob(kind+'-*'))
 p=dirs[-1]
 info=json.loads((p/'report.json').read_text())
 if info['status']!='complete':raise RuntimeError(kind+' did not complete')
 return str(p.relative_to(root))
def preflight(name):
 print('START '+name+' (three consecutive >=90% CPU-idle snapshots)',flush=True)
 observed=[];consecutive=0
 for attempt in range(12):
  time.sleep(20)
  probes={}
  for key,args in {'cpu':['top','-l','2','-s','1','-n','0'],'load':['sysctl','-n','vm.loadavg'],'power':['pmset','-g','batt'],'thermal':['pmset','-g','therm']}.items():
   p=subprocess.run(args,capture_output=True,text=True,check=True)
   probes[key]=p.stdout
  values=re.findall(r'CPU usage:.*?([\d.]+)% idle',probes['cpu'])
  idle=float(values[-1]) if values else 0
  ac="'AC Power'" in probes['power']
  observed.append({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'idle_percent':idle,**probes})
  (folder/(name+'.json')).write_text(json.dumps(observed,indent=2)+'\n')
  consecutive=consecutive+1 if idle>=90 and ac else 0
  print(f'PREFLIGHT {name}: CPU idle {idle:.1f}%, AC {ac}, quiet samples {consecutive}/3',flush=True)
  if consecutive>=3:return
 raise RuntimeError('Machine did not meet the quiet AC preflight; no timing batch started')
try:
 setup=json.loads((folder/'setup.json').read_text())
 state['runner']=setup
 stage('generate',[python,'-m','owner_state.run','generate','--variants','baseline','cse_dce'])
 state['generate']=report('generate');save()
 stage('native-tests',[python,'-m','unittest','discover','-s','owner_state','-p','test_*.py','-v'])
 stage('negative',[python,'-m','owner_state.run','negative','--variant','cse_dce'])
 state['negative']=report('negative');save()
 preflight('before-diagnostics')
 diagnostics='owner_state/diagnostics/20260911-full-restart'
 stage('diagnostics',[python,'-m','owner_state.microbench','--binary',root/setup['binary'],'--output',diagnostics])
 state['diagnostics']=diagnostics;save()
 preflight('before-proofs')
 stage('collect',[python,'-m','owner_state.run','collect','--blocks','8','--warmups','1','--variants','baseline','cse_dce','--seed','20260910'])
 state['collect']=report('collect');save()
 stage('verify',[python,'-m','owner_state.run','verify','--run',state['collect']])
 state['verify']=report('verify');save()
 state.update(status='complete',finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());save()
 print(json.dumps(state),flush=True)
except BaseException as exc:
 state.update(status='failed',error=repr(exc));save();raise
