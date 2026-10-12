#!/usr/bin/env python3
"""Receive one user-owned source bundle through an ephemeral GitHub file URL."""
import base64,hashlib,json,lzma,os,re
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from urllib.request import Request,urlopen,build_opener,HTTPRedirectHandler
ROOT=Path(__file__).resolve().parents[1]
SRC='ProfessorZhi/gwy-material-ops';REV='710cb9f85b9ae5e4167cbdd5172c59309a51c80e'
CACHE=ROOT/'tools/data/r7-owned-transcripts.pack.json'
def sha(b):return hashlib.sha256(b).hexdigest()
def unpack(data):
 if len(data)>40000000:raise ValueError('Source package too large')
 obj=json.loads(data)
 if obj.get('format')!='gwy-owned-transcript-v1' or obj.get('compression')!='xz':raise ValueError('Wrong source bundle')
 dec=lzma.LZMADecompressor();raw=dec.decompress(base64.b64decode(obj['data'],validate=True),max_length=100000001)
 if len(raw)>100000000 or not dec.eof or len(raw)!=obj['raw_bytes'] or sha(raw)!=obj['raw_sha256']:raise ValueError('Source size/hash mismatch')
 pack=json.loads(raw)
 if pack.get('source_repository')!=SRC or pack.get('source_revision')!=REV:raise ValueError('Wrong original source identity')
 seen=set()
 for row in pack['files']:
  p=row['path'];t=row['text'].encode('utf-8')
  if p in seen or not p.startswith('knowledge/gwy/001【公务员国省考】/') or not p.endswith('.md') or '..' in Path(p).parts:raise ValueError('Unsafe/duplicate source path')
  seen.add(p)
  if sha(t)!=row['sha256'] or hashlib.sha1(('blob '+str(len(t))+'\0').encode()+t).hexdigest()!=row['blob']:raise ValueError('Source text identity mismatch')
 return pack
class SameHost(HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if urlparse(newurl).hostname!='raw.githubusercontent.com':raise ValueError('Unapproved source redirect')
  return super().redirect_request(req,fp,code,msg,headers,newurl)
def main():
 event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
 body=event['pull_request'].get('body') or ''
 m=re.search(r'^R7-SOURCE-INPUT: (\{[^\r\n]+\})$',body,re.M)
 if not m:raise ValueError('No source file input')
 spec=json.loads(m[1]);url=spec['url'];u=urlparse(url)
 # Mask the temporary download reference and its query before any network work.
 for value in [url,*parse_qs(u.query).get('token',[])]:
  print('::add-mask::'+value.replace('%','%25').replace('\r','%0D').replace('\n','%0A'),flush=True)
 if (u.scheme!='https' or u.hostname!='raw.githubusercontent.com' or u.username or u.password or
     not re.fullmatch(r'/ProfessorZhi/gwy-material-ops/[a-f0-9]{40}/reports/r7-source-bundle/transcripts\.pack\.json',u.path)):
  raise ValueError('Source URL is outside the approved one-file scope')
 if not re.fullmatch(r'[a-f0-9]{64}',spec.get('sha256','')):raise ValueError('Missing source hash')
 try:
  with build_opener(SameHost()).open(Request(url,headers={'User-Agent':'gwy-reference-maintenance'}),timeout=90) as response:
   data=response.read(40000001)
 except Exception:raise RuntimeError('Temporary source file could not be retrieved') from None
 if sha(data)!=spec['sha256']:raise ValueError('Fetched file differs from immutable source manifest')
 pack=unpack(data)
 if len(pack['files'])!=spec['files']:raise ValueError('Source file count mismatch')
 CACHE.parent.mkdir(parents=True,exist_ok=True)
 if CACHE.exists() and CACHE.read_bytes()!=data:raise ValueError('Do not overwrite an earlier source bundle')
 CACHE.write_bytes(data)
 receipt={'source_repository':SRC,'original_source_revision':REV,'export_revision':u.path.split('/')[3],
          'package_sha256':sha(data),'source_files':len(pack['files']),'source_text_bytes':sum(len(r['text'].encode()) for r in pack['files']),
          'note':'Scoped user-owned file transfer; temporary URL deliberately not retained.'}
 (ROOT/'reports/R7-SOURCE-INPUT-20261013.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('R7_OWNED_SOURCE_READY',json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
