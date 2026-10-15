"""Recover four source materials and missing references, without inventing text."""
import hashlib,json,os,re,subprocess,uuid
from pathlib import Path
from urllib.parse import quote
import round5_bulk as parser
from full_repair_layout_20261015 import format_essay
from paper_integrity_repair import set_fields
ROOT=Path(__file__).resolve().parents[1];MOPS=ROOT.parent/'gwy-material-ops';REV='95676de3a494730fdcacd43416fd51d6bed48ab6'
def sha(s):return hashlib.sha256(s.encode() if isinstance(s,str) else s).hexdigest()
def atomic(p,s):
    tmp=p.with_name(p.name+'.black23-'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('wb') as f:f.write(s.encode());f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if tmp.exists():tmp.unlink()
def main():
    receipt=ROOT/'reports/FULL-REPAIR-BLACK2023-MATERIALS-20261015.json'
    if receipt.exists():raise ValueError('Already prepared')
    source='knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf/【11】黑龙江公务员考试真题pdf版/黑龙江公务员考试真题——申论05-24/2023年公务员多省联考《申论》题及参考答案（黑龙江行政执法卷）.pdf.md'
    env=dict(os.environ,GIT_CONFIG_GLOBAL='NUL',GIT_CONFIG_NOSYSTEM='1')
    raw=subprocess.check_output(['git','-c','core.fsmonitor=false','show',REV+':'+source],cwd=MOPS,env=env,timeout=90)
    text=raw.decode().replace('\r\n','\n');assert text==(MOPS/source).read_text(encoding='utf8')
    materials=text[text.index('### 材料1：'):text.index('## 三、作答要求')]
    materials=re.sub(r'<!--.*?-->','',materials,flags=re.S)
    materials=re.sub(r'(?m)^### 材料(\d+)：',lambda m:'## 给定资料 '+m[1],materials)
    materials=re.sub(r'(?<=[\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])','',materials)
    # Source typesetting spaces around Latin city labels and numerals are harmless;
    # content is retained rather than guessed from the old broken page joins.
    rel='省考/黑龙江/2023/申论-行政执法卷.md';p=ROOT/rel;old=p.read_text(encoding='utf8');d=parser.parse(old,rel)
    assert len(d['questions'])==4 and old.count('给定资料给定资料')==4
    assert len(materials)>old.index('作答要求\n\n问题一')-old.index('材料一：')
    prefix=old[:old.index('材料一：')]
    prefix=set_fields(prefix,{'给定材料数量':4,'对照题本题量':4,'实有题数':4,'缺失原题号':[],'材料与题面校核凭据':receipt.relative_to(ROOT).as_posix()},'2026-10-15据固定同题原稿恢复四则资料跨页漏文和引用编号。')
    url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(source,safe='/')
    new=prefix+'\n> 材料校勘：据[同题原稿固定版本]('+url+')接回跨页漏文，恢复资料1—4引用。来源为网友回忆整理，未冒充考试机关原件。\n\n'+materials.strip()+'\n\n'
    questions={}
    for n,q in d['questions'].items():
        q=q.replace('给定资料给定资料','给定资料'+str(n));questions[n]=q;new+='## 第 '+str(n)+' 题\n\n'+q+'\n\n'
    new+='## 答案与解析\n\n'+'\n\n'.join('<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+d['answers'][n]+'\n\n</details>' for n in questions)+'\n'
    new,layout=format_essay(new,rel);after=parser.parse(new,rel)
    assert len(after['questions'])==4
    for n in questions:assert parser.qkey(questions[n])==parser.qkey(after['questions'][n])
    proof={'status':'prepared','path':rel,'before_sha256':sha(old),'before_text':old,'after_sha256':sha(new),'source':source,'revision':REV,'source_sha256':sha(raw),'source_git_blob':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),'material_count':4,'correct_references':[1,2,3,4],'layout':layout}
    atomic(receipt,json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    if p.read_text(encoding='utf8')!=old:raise ValueError('Concurrent edit')
    atomic(p,new);proof['status']='applied';atomic(receipt,json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in proof.items() if k!='before_text'},ensure_ascii=False))
if __name__=='__main__':main()
