"""Restore exact task-to-material references from the same pinned transcript."""
import hashlib,json,os,re,subprocess,uuid
from pathlib import Path
from urllib.parse import quote
import round5_bulk as parser
from paper_integrity_repair import set_fields
ROOT=Path(__file__).resolve().parents[1]
REL='省考/黑龙江/2016/申论-C卷：县乡.md'
REV='95676de3a494730fdcacd43416fd51d6bed48ab6'
SOURCE='knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf/【11】黑龙江公务员考试真题pdf版/黑龙江公务员考试真题——申论05-24/2016年黑龙江公务员考试《申论》真题参考答案(县乡).pdf.md'
def sha(x):return hashlib.sha256(x.encode() if isinstance(x,str) else x).hexdigest()
def main():
    receipt=ROOT/'reports/FULL-REPAIR-BLACK2016-REFERENCES-20261015.json'
    if receipt.exists():raise ValueError('Already applied')
    env=dict(os.environ)
    if os.name=='nt':env.update(GIT_CONFIG_GLOBAL='NUL',GIT_CONFIG_NOSYSTEM='1')
    raw=subprocess.check_output(['git','-c','core.fsmonitor=false','show',REV+':'+SOURCE],cwd=ROOT.parent/'gwy-material-ops',env=env,timeout=90)
    source=re.sub(r'\s','',raw.decode('utf-8'))
    for phrase in ('根据给定资料1和2','根据给定资料4','给定资料5中所反映的问题'):
        if phrase not in source:raise ValueError('Expected same-source requirement not established: '+phrase)
    p=ROOT/REL;old=p.read_text(encoding='utf-8');d=parser.parse(old,REL);new=old;changes=[]
    replacements={1:('给定资料给定资料和给定资料','给定资料1和2'),2:('给定资料给定资料','给定资料4'),3:('给定资料给定资料','给定资料5')}
    for n,(before,after) in replacements.items():
        q=d['questions'][n]
        if q.count(before)!=1 or new.count(q)!=1:raise ValueError('Ambiguous task reference replacement')
        changed=q.replace(before,after);new=new.replace(q,changed,1);changes.append({'number':n,'old_question':q,'new_question':changed})
    new=set_fields(new,{'对照题本题量':4,'实有题数':4,'缺失原题号':[],'作答材料范围校核凭据':'reports/FULL-REPAIR-BLACK2016-REFERENCES-20261015.json'},'2026-10-15依同卷固定原稿恢复第1题资料1和2、第2题资料4、第3题资料5引用范围；已标原材料缺段继续保留。')
    url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(SOURCE,safe='/')
    new+='\n> 作答范围校勘：[同卷固定原稿]('+url+')明确前三题分别使用资料1和2、资料4、资料5，现恢复对应引用。原稿自身的两处材料缺段仍见卷首说明。\n'
    record={'path':REL,'before_sha256':sha(old),'before_text':old,'after_sha256':sha(new),'source_revision':REV,'source_path':SOURCE,'source_blob':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),'source_sha256':sha(raw),'source_url':url,'task_reference_changes':changes,'status':'prepared'}
    receipt.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temp=p.with_name(p.name+'.refs-'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_bytes(new.encode())
        if p.read_text(encoding='utf-8')!=old:raise ValueError('Concurrent paper edit')
        os.replace(temp,p)
    finally:
        if temp.exists():temp.unlink()
    record['status']='applied';receipt.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'passed','task_references_restored':3}))
if __name__=='__main__':main()
