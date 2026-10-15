"""Exact outer receipts and isolated historical validation for the full repair.

Historical tests run against an exactly restored PR19 tree, not weakened current
hash expectations. Current task completion is audited separately and explicitly.
"""
from __future__ import annotations
import argparse,collections,difflib,hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SHARD_DIR='reports/full-repair-20261015'
INDEX='reports/FULL-REPAIR-BASELINE-20261015.json'
BASE='f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab'
def sha(data):return hashlib.sha256(data if isinstance(data,bytes) else data.encode('utf-8')).hexdigest()

def git_blob(data):
    if isinstance(data,str):data=data.encode('utf-8')
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def base_tree(root):
    env=dict(os.environ)
    if os.name=='nt':env.update(GIT_CONFIG_GLOBAL='NUL',GIT_CONFIG_NOSYSTEM='1')
    raw=subprocess.check_output(['git','-c','core.fsmonitor=false','ls-tree','-r','-z','--full-tree',BASE],cwd=root,env=env,timeout=120)
    result={}
    for item in raw.split(b'\0'):
        if not item:continue
        header,path=item.split(b'\t',1);mode,kind,blob=header.decode('ascii').split();rel=path.decode('utf-8')
        if rel.startswith('图片/'):continue
        if kind!='blob' or mode not in ('100644','100755'):raise ValueError('Unsupported baseline tree entry: '+rel)
        result[rel]=blob
    return result

def checked_index(root,index):
    expected=base_tree(root);entries=index['base_files']
    if len(entries)!=len(expected) or {e['path'] for e in entries}!=set(expected):raise ValueError('Baseline index differs from fixed Git tree')
    for entry in entries:
        if entry.get('git_blob')!=expected[entry['path']]:raise ValueError('Baseline blob is not bound to Git commit: '+entry['path'])
    return expected

def operations(old,new):
    aa=old.splitlines(keepends=True);bb=new.splitlines(keepends=True)
    ap=[0];bp=[0]
    for s in aa:ap.append(ap[-1]+len(s))
    for s in bb:bp.append(bp[-1]+len(s))
    result=[]
    # Common blank/heading lines must not cause quadratic matching across large
    # transcripts. Coarser exact replacement hunks remain fully byte reversible;
    # both endpoints and the reconstructed fixed Git blob are checked below.
    for tag,a,b,c,d in difflib.SequenceMatcher(None,aa,bb,autojunk=True).get_opcodes():
        if tag!='equal':result.append({'old_start':ap[a],'old_end':ap[b],'new_start':bp[c],'new_end':bp[d],'old':old[ap[a]:ap[b]],'new':new[bp[c]:bp[d]]})
    return result

def reverse(current,row):
    if sha(current)!=row['after_sha256']:raise ValueError('Current postimage mismatch: '+row['path'])
    for op in reversed(row['operations']):
        a,b=op['new_start'],op['new_end']
        if current[a:b]!=op['new']:raise ValueError('Receipt operation mismatch: '+row['path'])
        current=current[:a]+op['old']+current[b:]
    if sha(current)!=row['before_sha256']:raise ValueError('Restored preimage mismatch: '+row['path'])
    return current

def capture(baseline,root=ROOT):
    baseline=Path(baseline).resolve();root=Path(root).resolve()
    paths=[];records=[];unrestored=[];expected=base_tree(root)
    actual={p.relative_to(baseline).as_posix() for p in baseline.rglob('*') if p.is_file() and '__pycache__' not in p.parts and not p.relative_to(baseline).as_posix().startswith('图片/')}
    if actual!=set(expected):raise ValueError('Exported baseline paths differ from fixed Git tree: '+str(sorted(actual^set(expected))[:12]))
    disposition=root/'reports/FULL-REPAIR-IDENTITY-DISPOSITION-20261015.json'
    relocations=json.loads(disposition.read_text(encoding='utf-8')).get('relocations',{}) if disposition.exists() else {}
    for p in sorted(baseline.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts:continue
        rel=p.relative_to(baseline).as_posix()
        if rel.startswith('图片/'):continue
        old=p.read_bytes();q=root/rel
        if git_blob(old)!=expected[rel]:raise ValueError('Exported baseline bytes differ from fixed Git commit: '+rel)
        destination=relocations.get(rel)
        if destination:q=root/destination
        if not q.is_file():unrestored.append(rel);continue
        paths.append({'path':rel,'sha256':sha(old),'git_blob':expected[rel]})
        new=q.read_bytes()
        if old==new and not destination:continue
        before=old.decode('utf-8');after=new.decode('utf-8')
        record={'path':rel,'kind':'relocated' if destination else 'modified','before_sha256':sha(old),'after_sha256':sha(new),'operations':operations(before,after)}
        if destination:record['destination']=destination
        if reverse(after,record)!=before:raise ValueError('Receipt self-check failed')
        records.append(record)
    if unrestored:raise ValueError('Baseline files unexpectedly deleted: '+str(unrestored))
    oldpaths={p['path'] for p in paths}
    bound_destinations={relocations.get(rel,rel) for rel in oldpaths}
    created=[p.relative_to(root).as_posix() for top in ('国考','省考') for p in (root/top).rglob('*.md') if p.relative_to(root).as_posix() not in bound_destinations]
    for rel in created:
        data=(root/rel).read_bytes();records.append({'path':rel,'kind':'created_paper','before_sha256':None,'after_sha256':sha(data),'operations':[]})
    # Bounded files remain reviewable and below GitHub's per-file size limit.
    chunks=[];chunk=bytearray()
    for record in records:
        line=(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
        if len(line)>32*1024*1024:raise ValueError('Single receipt exceeds safe shard size')
        if chunk and len(chunk)+len(line)>16*1024*1024:chunks.append(bytes(chunk));chunk=bytearray()
        chunk.extend(line)
    if chunk:chunks.append(bytes(chunk))
    (root/SHARD_DIR).mkdir(exist_ok=True)
    shards=[]
    for n,data in enumerate(chunks,1):
        rel=f'{SHARD_DIR}/receipts-{n:03d}.jsonl';(root/rel).write_bytes(data)
        shards.append({'path':rel,'sha256':sha(data),'bytes':len(data)})
    (root/INDEX).write_text(json.dumps({'base_commit':BASE,'base_files':paths,'receipt_shards':shards,'created_papers':created,'baseline_paper_files':sum(p['path'].startswith(('国考/','省考/')) and p['path'].endswith('.md') for p in paths),'boundary':'The fixed baseline is exported directly from the exact original PR19 Git commit; each original file hash is checked on reconstruction.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'status':'passed','changed_baseline_files':len(records)-len(created),'created_papers':len(created),'base_files':len(paths)}

def records(root):
    root=Path(root).resolve();index=json.loads((root/INDEX).read_text(encoding='utf-8'));rows=[]
    for shard in index['receipt_shards']:
        p=(root/shard['path']).resolve()
        if not p.is_relative_to(root/SHARD_DIR):raise ValueError('Unsafe receipt shard')
        data=p.read_bytes()
        if sha(data)!=shard['sha256']:raise ValueError('Receipt shard changed: '+shard['path'])
        # NDJSON is delimited by LF. U+2028/U+2029 can be genuine source text
        # inside a JSON string and must never be treated as record separators.
        rows.extend(json.loads(line) for line in data.decode('utf-8').split('\n') if line.strip())
    return rows

def historical_snapshot(root,destination):
    root=Path(root).resolve();destination=Path(destination).resolve()
    index=json.loads((root/INDEX).read_text(encoding='utf-8'))
    expected=checked_index(root,index)
    changes={r['path']:r for r in records(root) if r['kind']!='created_paper'}
    for entry in index['base_files']:
        rel=entry['path'];row=changes.get(rel);source_rel=row['destination'] if row and row['kind']=='relocated' else rel
        src=(root/source_rel).resolve();dst=(destination/rel).resolve()
        if not src.is_relative_to(root) or not dst.is_relative_to(destination):raise ValueError('Unsafe baseline path')
        current=src.read_bytes()
        restored=reverse(current.decode('utf-8'),changes[rel]).encode('utf-8') if rel in changes else current
        if sha(restored)!=entry['sha256']:raise ValueError('Unchanged baseline file drifted: '+rel)
        if git_blob(restored)!=expected[rel]:raise ValueError('Restored bytes differ from fixed Git commit: '+rel)
        dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(restored)
    # Earlier source-chain verifiers depend on these two delivered image receipts.
    for rel in ('图片/校核补录/20261012/浙江2025-行测-原52.png','图片/校核补录/20261012/浙江2025-行测-原55.png'):
        dst=destination/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/rel,dst)
    return {'base_files_restored':len(index['base_files']),'created_papers_excluded':len(index['created_papers'])}

def verify(root=ROOT):
    root=Path(root).resolve();rows=records(root);seen=set()
    index=json.loads((root/INDEX).read_text(encoding='utf-8'));expected=checked_index(root,index);changes={r['path']:r for r in rows if r['kind']!='created_paper'}
    created={r['path'] for r in rows if r['kind']=='created_paper'}
    if created!=set(index['created_papers']):raise ValueError('Created-paper receipts differ from index')
    for r in rows:
        rel=r['path'];p=(root/r.get('destination',rel)).resolve()
        if r['kind'] not in ('created_paper','modified','relocated'):raise ValueError('Unknown receipt kind')
        key=(r['kind']=='created_paper',rel)
        if key in seen or not p.is_relative_to(root):raise ValueError('Duplicate or unsafe receipt path')
        seen.add(key)
        if r['kind']=='created_paper':
            if sha(p.read_bytes())!=r['after_sha256']:raise ValueError('Created paper changed: '+rel)
        else:reverse(p.read_bytes().decode('utf-8'),r)
    for entry in index['base_files']:
        rel=entry['path'];row=changes.get(rel);source=row.get('destination',rel) if row else rel
        data=(root/source).read_bytes()
        restored=reverse(data.decode('utf-8'),row).encode('utf-8') if row else data
        if sha(restored)!=entry['sha256'] or git_blob(restored)!=expected[rel]:raise ValueError('Baseline bytes do not match fixed Git commit: '+rel)
    bound={changes.get(rel,{}).get('destination',rel) for rel in expected}
    bound_papers={rel for rel in bound if rel.startswith(('国考/','省考/')) and rel.endswith('.md')}
    actual={p.relative_to(root).as_posix() for top in ('国考','省考') for p in (root/top).rglob('*.md')}
    if actual!=bound_papers|created:raise ValueError('Current paper set changed after capture')
    return {'status':'passed','receipts':len(rows),'changed_papers':sum(r['path'].startswith(('国考/','省考/')) and r['path'].endswith('.md') for r in rows),'base_commit':BASE}

def historical_validation(root=ROOT,tests=False):
    root=Path(root).resolve()
    # Windows may expose TEMP as an 8.3 alias. The unchanged older validators
    # compare resolved paths with their temporary root, so give every nested
    # process the same canonical root without altering those validators.
    canonical_temp=str(Path(tempfile.gettempdir()).resolve())
    child_env={**os.environ,'TMP':canonical_temp,'TEMP':canonical_temp,'TMPDIR':canonical_temp}
    with tempfile.TemporaryDirectory(prefix='gwy-full-repair-pr19-',dir=canonical_temp) as temp:
        old=Path(temp);result=historical_snapshot(root,old)
        commands=[[sys.executable,'-X','utf8',str(old/'tools/verify_repair_receipts.py'),'--root',str(old)]]
        if tests:
            commands.extend([[sys.executable,'-X','utf8','-m','unittest','discover','-s','tests','-q'],[sys.executable,'-X','utf8','-m','unittest','cloud_quality_test','paper_integrity_repair_test','priority_quality_test','essay_transcript_restore_test','round3_repair_test','-q']])
        logs=[]
        for command in commands:
            p=subprocess.run(command,cwd=old/'tools',env=child_env,capture_output=True,text=True,encoding='utf-8',timeout=600)
            logs.append({'command':command[3:],'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
            if p.returncode:raise ValueError('Historical validation failed: '+p.stdout[-1000:]+'\n'+p.stderr[-4000:])
        result.update(status='passed',checks=logs)
        return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--capture',type=Path);ap.add_argument('--historical',action='store_true');ap.add_argument('--tests',action='store_true');ap.add_argument('--output',type=Path);args=ap.parse_args()
    result=capture(args.capture) if args.capture else verify()
    if args.historical:result['historical']=historical_validation(tests=args.tests)
    if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
