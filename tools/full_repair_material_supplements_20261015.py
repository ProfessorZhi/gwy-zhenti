"""Apply literal, source-hashed missing material restorations after review."""
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent/'gwy-material-ops'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    entries=json.loads((ROOT/'tools/data/essay-b-material-supplements-20261015.json').read_text(encoding='utf-8'))
    results=[]
    for row in entries:
        p=(ROOT/row['path']).resolve();source=(SOURCE/row['source_path']).resolve()
        assert p.is_relative_to(ROOT) and source.is_relative_to(SOURCE)
        assert sha(source.read_bytes())==row['source_sha256'], 'Source changed'
        old=p.read_text(encoding='utf-8');new=old
        for op in row['operations']:
            assert new.count(op['old'])==op['occurrences'], (row['path'],op['old'])
            new=new.replace(op['old'],op['new'])
        # The earlier layout pass can alter unrelated whitespace; literal operation
        # matches and the source hash, rather than a stale whole-file hash, gate this.
        p.write_text(new.rstrip()+'\n',encoding='utf-8',newline='\n')
        results.append({**row,'status':'applied','actual_before_sha256':sha(old.encode()),'actual_after_sha256':sha(p.read_bytes())})
    (ROOT/'reports/FULL-REPAIR-MATERIAL-SUPPLEMENTS-20261015.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'passed','papers':len(results),'literal_operations':sum(len(r['operations']) for r in results)},ensure_ascii=False))
if __name__=='__main__':main()
