"""Check installed native bytes against their own distribution RECORD entries."""
import base64
import hashlib
import importlib.metadata
import json
from pathlib import Path
from v6_raw_archive import sha


def main():
    base=Path('results/v3');out=base/'v9_native_distribution_integrity.json';assert not out.exists()
    reg_path=base/'v9repair2_registration.json';reg=json.loads(reg_path.read_text());remaining=set(reg['native_source_sha256']);packages=[]
    for name in ['vllm','lmcache']:
        distribution=importlib.metadata.distribution(name);root=Path(distribution.locate_file(name)).resolve()
        indexed={Path(distribution.locate_file(f)).resolve():f for f in distribution.files or []};records=[]
        for source in sorted(remaining.copy()):
            path=Path(source).resolve()
            if not path.is_relative_to(root):continue
            f=indexed.get(path);recorded=getattr(f,'hash',None);actual=sha(path);assert actual==reg['native_source_sha256'][source]
            encoded=base64.urlsafe_b64encode(bytes.fromhex(actual)).decode().rstrip('=')
            matches=bool(recorded and recorded.mode=='sha256' and recorded.value==encoded)
            records.append(dict(source_path=source,distribution_file=str(f),sha256=actual,recorded_hash_mode=recorded.mode if recorded else None,
                recorded_hash_value=recorded.value if recorded else None,matches_installed_record=matches));remaining.remove(source)
        assert records and all(r['matches_installed_record'] for r in records)
        artifacts={}
        for filename in ['METADATA','WHEEL','RECORD','direct_url.json']:
            text=distribution.read_text(filename)
            if text is not None:artifacts[filename]=hashlib.sha256(text.encode()).hexdigest()
        packages.append(dict(name=name,version=distribution.version,distribution_metadata_text_sha256=artifacts,files=records))
    assert not remaining
    result=dict(all_selected_native_files_match_installed_record=True,selected_files=sum(len(p['files']) for p in packages),packages=packages,
        registration_sha256=sha(reg_path),source_sha256=sha(__file__),
        scope='Read-only installed-distribution RECORD consistency for the6selected native files; all match. RECORD/METADATA/WHEEL text identities retained. No independently downloaded/published wheel verification, complete dependency lock/fresh-host reproduction or claim that installed-file identity alone proves runtime implementation. V9 effective method differs in memory and is verified separately by constructor proof.')
    out.write_text(json.dumps(result,indent=2)+'\n');print('Selected native files match installed RECORD:',result['selected_files'],flush=True)


if __name__=='__main__':main()
