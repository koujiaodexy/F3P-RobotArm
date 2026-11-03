"""Open the independent camera viewer using the enrolled, pinned SSH identity."""
import argparse,importlib.util,json,time,urllib.request,webbrowser
from pathlib import Path
spec=importlib.util.spec_from_file_location('desktop',Path(__file__).with_name('reconnect-desktop-mirror.py'))
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
URL='http://127.0.0.1:5903/'
def health():
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URL+'status',timeout=2) as r:value=json.loads(r.read(4096))
        if value.get('service')=='f3p-camera-stream-v1':return value
    except (OSError,ValueError):pass
    return None
def main():
    p=argparse.ArgumentParser();p.add_argument('--no-browser',action='store_true');a=p.parse_args()
    key=d.STATE/'desktop_ed25519';trust=d.STATE/'known_hosts';alias=d.STATE/'known_hosts_desktop'
    expected=d.pinned_alias(trust.read_text(encoding='utf-8-sig'))
    if alias.read_text(encoding='ascii')!=expected:raise RuntimeError('Board host key mismatch')
    command=d.ssh_command(d.discover_address(),alias,key)
    command[command.index('-L')+1]='127.0.0.1:5903:127.0.0.1:5902'
    statefile=d.STATE/'camera-preview-state.json'
    record=json.loads(statefile.read_text()) if statefile.exists() else {}
    if d.same_identity(record) and record['argv']!=command:
        d.stop_owned(record);record={}
    if not d.same_identity(record):
        if d.listening(5903):raise RuntimeError('Port 5903 belongs to an unmanaged process; it was not stopped')
        record=d.start_hidden(command,d.STATE/'camera-preview-tunnel.log')
        statefile.write_text(json.dumps(record,indent=2))
    deadline=time.monotonic()+12;value=health()
    while not value and time.monotonic()<deadline:time.sleep(.3);value=health()
    if not value:raise RuntimeError('Camera viewer unavailable; check board power and hotspot')
    print(json.dumps(dict(ready=True,url='http://127.0.0.1:6080/control.html',status=value)))
    if not a.no_browser:webbrowser.open('http://127.0.0.1:6080/control.html')
if __name__=='__main__':main()
