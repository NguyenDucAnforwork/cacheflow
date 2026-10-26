"""Download the pinned second model; verify every shard before recording adoption."""
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

source=Path('results/v3/qwen3_4b_source.json')
meta=json.loads(source.read_text());revision=meta['sha'];repo=meta['id']
target=Path('/workspace/.hf_home/hub/models--Qwen--Qwen3-4B/snapshots')/revision
target.mkdir(parents=True,exist_ok=True)
weights=[];small=[]
for f in meta['siblings']:
 name=f['rfilename']
 if name.endswith('.safetensors'):
  weights.append(f)
 elif name.endswith(('.json','.txt','.jinja')) and '/' not in name:
  small.append(f)
for f in small:
 name=f['rfilename'];p=target/name
 raw=urllib.request.urlopen(f'https://huggingface.co/{repo}/resolve/{revision}/{name}',timeout=60).read()
 p.write_bytes(raw)
inputs=Path('results/v3/raw/qwen3_4b_aria.input')
inputs.write_text(''.join(f'https://huggingface.co/{repo}/resolve/{revision}/{f["rfilename"]}?download=true\n  dir={target}\n  out={f["rfilename"]}\n' for f in weights))
subprocess.run(['aria2c','--continue=true','--auto-file-renaming=false','--file-allocation=none',
 '--allow-overwrite=false','-x','8','-s','8','-j','3','--min-split-size=16M','--summary-interval=60',
 '--console-log-level=warn','--download-result=hide','--timeout=60','--retry-wait=5','--max-tries=20',
 '--input-file='+str(inputs)],check=True)
verified=[]
for f in weights:
 p=target/f['rfilename'];assert p.stat().st_size==f['lfs']['size']
 digest=hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
 assert digest==f['lfs']['sha256'],p.name
 verified.append(dict(file=p.name,size=p.stat().st_size,sha256=digest))
Path('results/v3/qwen3_4b_adoption.json').write_text(json.dumps(dict(repo=repo,revision=revision,path=str(target),weights=verified),indent=2)+'\n')
print('VERIFIED MODEL',repo,revision,flush=True)
