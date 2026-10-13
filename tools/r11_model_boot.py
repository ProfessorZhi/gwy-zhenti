#!/usr/bin/env python3
"""Download public, pinned GGUF weights and a checksummed official CPU runtime.
Only the ephemeral GitHub-hosted runner runs inference; no private text leaves it.
"""
from __future__ import annotations
import hashlib,json,os,pathlib,subprocess,tarfile,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
WORK=pathlib.Path(os.environ.get('RUNNER_TEMP','/tmp'))/'r11-model'
MODEL_REPO='unsloth/Qwen3-4B-Instruct-2507-GGUF'
MODEL_REV='a06e946bb6b655725eafa393f4a9745d460374c9'
MODEL_FILE='Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
MODEL_SHA='3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597'
RUNTIME_TAG='b11429'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()

def download(url,path,expected):
    if path.exists() and sha(path)==expected:return
    req=urllib.request.Request(url,headers={'User-Agent':'gwy-r11-local-reference-writer'})
    with urllib.request.urlopen(req,timeout=180) as r,path.open('wb') as f:
        while True:
            b=r.read(8*1024*1024)
            if not b:break
            f.write(b)
    actual=sha(path)
    if actual!=expected:raise ValueError('Downloaded asset SHA256 differs: '+path.name)

def main():
    WORK.mkdir(parents=True,exist_ok=True)
    model=WORK/MODEL_FILE
    download('https://huggingface.co/'+MODEL_REPO+'/resolve/'+MODEL_REV+'/'+MODEL_FILE,model,MODEL_SHA)
    url='https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/'+RUNTIME_TAG
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'gwy-r11-local-reference-writer'}),timeout=60) as r:
        release=json.load(r)
    names=[a for a in release['assets'] if a['name']==f'llama-{RUNTIME_TAG}-bin-ubuntu-x64.tar.gz']
    if len(names)!=1:raise ValueError('Official CPU runtime asset not uniquely available')
    a=names[0]; digest=a.get('digest','')
    if not digest.startswith('sha256:') or len(digest)!=71:raise ValueError('Runtime asset lacks official SHA256')
    archive=WORK/a['name'];download(a['browser_download_url'],archive,digest[7:])
    runtime=WORK/'runtime';runtime.mkdir(exist_ok=True)
    with tarfile.open(archive) as tf:tf.extractall(runtime,filter='data')
    servers=list(runtime.rglob('llama-server'))
    if len(servers)!=1:raise ValueError('Expected exactly one llama-server executable')
    server=servers[0]
    env=dict(os.environ)
    env.pop('GH_TOKEN',None);env.pop('GITHUB_TOKEN',None)
    env['LD_LIBRARY_PATH']=str(server.parent)
    provenance={'model':MODEL_REPO,'model_revision':MODEL_REV,'model_file':MODEL_FILE,'model_sha256':MODEL_SHA,
                'runtime_tag':RUNTIME_TAG,'runtime_asset':a['name'],'runtime_sha256':digest[7:],
                'inference_location':'ephemeral GitHub-hosted runner, loopback only',
                'private_material_external_api_submission':False}
    (WORK/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    log=(WORK/'server.log').open('wb')
    cmd=[str(server),'-m',str(model),'--host','127.0.0.1','--port','8080','-c','16384','-t',str(min(4,os.cpu_count() or 2)),
         '-tb',str(min(4,os.cpu_count() or 2)),'--parallel','1','-ngl','0','-b','512','-ub','128']
    process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
    (WORK/'server.pid').write_text(str(process.pid))
    print('R11_LOCAL_SERVER_STARTED '+json.dumps(provenance),flush=True)

if __name__=='__main__':main()
