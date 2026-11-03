from pathlib import Path, PurePosixPath
import hashlib,json,sys
if len(sys.argv)!=2:raise SystemExit('Usage: python restore.py NEW_EMPTY_DIRECTORY')
src=Path(__file__).resolve().parent
out=Path(sys.argv[1]).resolve()
if out.exists():raise SystemExit('Please specify a new directory')
m=json.loads((src/'index.json').read_text(encoding='utf8'))
def safe(base,s):
 p=(base/PurePosixPath(s)).resolve()
 if p==base or not p.is_relative_to(base):raise ValueError(s)
 return p
for n,r in m['paths'].items():
 p=safe(out,n);b=safe(src,r['stored']).read_bytes()
 if hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError(n)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
print('Verified and restored',len(m['paths']),'paths to',out)
