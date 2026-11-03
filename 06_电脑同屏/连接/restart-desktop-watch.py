"""Replace only this project's existing watcher; its lock prevents duplicates."""
import importlib.util,json,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('desktop',Path(__file__).with_name('reconnect-desktop-mirror.py'))
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
watch=Path(__file__).with_name('watch-desktop-connection.py').resolve()
matches=[]
for p in d.psutil.process_iter(['pid','cmdline']):
    try:
        argv=p.info['cmdline'] or []
        if any(str(watch).lower()==str(v).lower() for v in argv):matches.append(d.process_identity(p.pid))
    except d.psutil.Error:pass
for identity in matches:
    if d.same_identity(identity):d.stop_owned(identity)
record=d.start_hidden([sys.executable,'-B','-X','utf8',str(watch)],d.STATE/'watchdog-run.log')
(d.STATE/'watchdog-launch.json').write_text(json.dumps(record,indent=2))
print(json.dumps({'started':True,'pid':record['pid'],'replaced':len(matches)}))
