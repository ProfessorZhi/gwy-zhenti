"""Normalize publication text bytes before capturing receipts and staging Git."""
import hashlib,json,os,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TEXT={'.md','.py','.json','.jsonl','.yml','.yaml','.toml','.txt','.csv','.tsv'}
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    files=[p for top in ('国考','省考','tools','reports','docs','catalog','资料缺失','.github') for p in (ROOT/top).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix.lower() in TEXT]
    files += [p for p in ROOT.iterdir() if p.is_file() and p.suffix.lower() in TEXT]
    rows=[]
    for p in sorted(set(files)):
        before=p.read_bytes()
        if b'\r\n' not in before:continue
        before.decode('utf-8')
        after=before.replace(b'\r\n',b'\n')
        temp=p.with_name(p.name+'.lf-'+uuid.uuid4().hex+'.tmp')
        try:
            temp.write_bytes(after)
            if p.read_bytes()!=before:raise ValueError('Concurrent text change: '+str(p))
            os.replace(temp,p)
            if p.read_bytes()!=after:raise ValueError('LF publication write drift')
        finally:
            if temp.exists():temp.unlink()
        rows.append({'path':p.relative_to(ROOT).as_posix(),'before_sha256':sha(before),'after_sha256':sha(after),'crlf_sequences':before.count(b'\r\n')})
    report=ROOT/'reports/FULL-REPAIR-LF-PUBLICATION-20261015.json'
    previous=json.loads(report.read_text(encoding='utf8')) if report.exists() else {'reason':'Git attributes require LF for Markdown; byte receipts must describe exactly the bytes that will be published. JSON string escapes and source text contents are unchanged.','runs':[]}
    if rows:previous['runs'].append({'files':len(rows),'rows':rows})
    report.write_bytes((json.dumps(previous,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({'lf_normalized_files':len(rows),'remaining_crlf_files':sum(b'\r\n' in p.read_bytes() for p in files)},ensure_ascii=False))
if __name__=='__main__':main()
