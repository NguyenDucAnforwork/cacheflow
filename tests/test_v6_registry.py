import csv
import hashlib
import json
from importlib.util import spec_from_file_location,module_from_spec


def test_canonical_registry_preserves_legacy_and_blanks_invalid_latency(tmp_path):
    spec=spec_from_file_location('v6_normalize_registry','scripts/v6_normalize_registry.py');m=module_from_spec(spec);spec.loader.exec_module(m)
    raw=tmp_path/'raw';raw.mkdir();legacy=tmp_path/'registry.csv';legacy.write_text('run_id,requests\nold,1\nnew,1,180\n');original=legacy.read_bytes()
    a=raw/'old.summary.json';a.write_text(json.dumps(dict(run_id='old',requests=1,errors=0,arrival_ttft_p95_ms=10)))
    b=raw/'new.summary.json';b.write_text(json.dumps(dict(run_id='new',requests=1,errors=1,arrival_ttft_p95_ms=5,request_read_timeout_s=180)))
    report=m.normalize(tmp_path,raw)
    assert legacy.read_bytes()==original and report['legacy_mixed_width']
    with (tmp_path/'registry_normalized.csv').open() as f:rows={r['run_id']:r for r in csv.DictReader(f)}
    assert rows['old']['arrival_ttft_p95_ms']=='10' and rows['old']['request_read_timeout_s']==''
    assert rows['new']['arrival_ttft_p95_ms']=='' and rows['new']['request_read_timeout_s']=='180'
    assert rows['new']['summary_file_sha256']==hashlib.sha256(b.read_bytes()).hexdigest()


def test_canonical_registry_indexes_gzip_without_expanding_raw(tmp_path):
    import gzip
    spec=spec_from_file_location('v6_normalize_registry','scripts/v6_normalize_registry.py');m=module_from_spec(spec);spec.loader.exec_module(m)
    raw=tmp_path/'raw';raw.mkdir();blob=json.dumps(dict(run_id='archived',requests=1986,errors=0,arrival_ttft_p95_ms=100)).encode()
    path=raw/'archived.summary.json.gz';path.write_bytes(gzip.compress(blob,mtime=0));stored=path.read_bytes()
    audit=m.normalize(tmp_path,raw);assert audit['records']==1 and path.read_bytes()==stored and not path.with_suffix('').exists()
    with (tmp_path/'registry_normalized.csv').open() as f:row=next(csv.DictReader(f))
    assert row['summary_storage']=='gzip' and row['arrival_ttft_p95_ms']=='100'
    assert row['summary_file_sha256']==hashlib.sha256(stored).hexdigest()
    assert row['summary_uncompressed_sha256']==hashlib.sha256(blob).hexdigest()
