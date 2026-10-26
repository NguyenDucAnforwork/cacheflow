"""Build separate canonical indexes from JSON ledgers; preserve legacy append CSVs."""
import argparse
import csv
import hashlib
import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path


def normalize(base,raw):
    legacy=base/'registry.csv';widths={};header=None
    if legacy.exists():
        with legacy.open() as f:
            rr=list(csv.reader(f))
        if rr:header=len(rr[0]);widths=dict(Counter(map(len,rr[1:])))
    records=[];skipped=[];ids=defaultdict(list)
    for path in sorted(raw.glob('*.summary.json')):
        blob=path.read_bytes()
        try:row=json.loads(blob)
        except json.JSONDecodeError:
            skipped.append(str(path));continue
        if 'run_id' not in row:skipped.append(str(path));continue
        row=dict(row);rid=row['run_id'];ids[rid].append(str(path))
        invalid=(base/f'{rid}.invalid').exists()
        row.update(summary_path=str(path.resolve()),summary_file_sha256=hashlib.sha256(blob).hexdigest(),invalid_marker_exists=invalid,
            index_scope='Request ledger locator only; use per-protocol audits for performance eligibility')
        redacted=invalid or bool(row.get('errors',0))
        row['latency_quantiles_hidden_for_invalid_or_failed']=redacted
        if redacted:
            for key in list(row):
                if key.startswith('arrival_ttft_p') or key.startswith('client_ttft_p'):row[key]=None
        records.append(row)
    fields=['run_id',*sorted({key for r in records for key in r if key!='run_id'})]
    output=base/'registry_normalized.csv';temp=output.with_suffix('.csv.tmp')
    with temp.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(records)
    temp.replace(output)
    audit=dict(generated_utc=datetime.now(timezone.utc).isoformat(),scope='Derived canonical index from complete JSON ledgers; legacy CSV preserved. Not a count of independent questions or performance-eligible runs. Pre-replay failures require controller outcomes; missing source/metadata is not inferred.',
        records=len(records),legacy_header_columns=header,legacy_row_width_counts=widths,
        legacy_mixed_width=any(int(k)!=header for k in widths),
        skipped_incomplete_or_nonrequest_summaries=skipped,duplicate_run_ids={k:v for k,v in ids.items() if len(v)>1},
        normalized_csv_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        latency_quantiles_hidden_records=sum(r['latency_quantiles_hidden_for_invalid_or_failed'] for r in records))
    (base/'registry_normalized.audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    return audit


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('results/v3'));a=p.parse_args()
    for base,raw in [(a.root,a.root/'raw'),(a.root/'sglang',a.root/'raw/sglang')]:
        if base.exists() and raw.exists():
            result=normalize(base,raw);print(base,result['records'],'JSON ledgers; legacy mixed width',result['legacy_mixed_width'])


if __name__=='__main__':main()
