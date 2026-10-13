#!/usr/bin/env python3
"""Commit only this worker's generated JSON through GitHub's contents API."""
import argparse,base64,json,os,re,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO='ProfessorZhi/gwy-zhenti'
BRANCH='essay/r11-complete-568'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--label',required=True);args=ap.parse_args()
    if not re.fullmatch(r'[a-z0-9-]{1,60}',args.label):raise ValueError('Unsafe worker label')
    if os.environ.get('GITHUB_REPOSITORY')!=REPO or os.environ.get('GITHUB_REF_NAME')!=BRANCH:
        raise ValueError('Writing is allowed only to the authorized work branch')
    token=os.environ['GH_TOKEN']
    def api(method,path,data=None):
        req=urllib.request.Request('https://api.github.com/repos/'+REPO+'/'+path,
              data=None if data is None else json.dumps(data).encode('utf-8'),method=method,
              headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
                       'X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
    files=[]
    for folder in ('r11-cloud-drafts','r11-cloud-status'):
        p=ROOT/'reports'/folder/(args.label+'.json')
        if p.is_file():files.append(p)
    if not files:
        status=ROOT/'reports/r11-cloud-status'/(args.label+'.json');status.parent.mkdir(parents=True,exist_ok=True)
        log=Path(os.environ.get('RUNNER_TEMP','/tmp'))/'r11-model/server.log'
        status.write_text(json.dumps({'label':args.label,'status':'worker_failed_before_draft','drafts_written':0,
              'runtime_log_tail':log.read_text(errors='replace')[-3000:] if log.exists() else 'Runtime bootstrap did not complete.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        files=[status]
    for p in files:
        rel=p.relative_to(ROOT).as_posix();raw=p.read_bytes();json.loads(raw)
        route='contents/'+urllib.parse.quote(rel,safe='/')
        for attempt in range(8):
            previous=None
            try:previous=api('GET',route+'?ref='+urllib.parse.quote(BRANCH,safe=''))
            except urllib.error.HTTPError as exc:
                if exc.code!=404:raise
            data={'branch':BRANCH,'message':'content: R11 '+args.label+' 原创初稿与实测状态',
                  'content':base64.b64encode(raw).decode('ascii')}
            if previous:data['sha']=previous['sha']
            try:
                result=api('PUT',route,data)
                print('R11_CHECKPOINT '+rel+' '+result['commit']['sha'],flush=True);break
            except urllib.error.HTTPError as exc:
                if exc.code not in (409,422) or attempt==7:raise
                time.sleep(2+attempt)
        else:raise RuntimeError('Could not persist worker output')

if __name__=='__main__':main()
