"""Restore shared Shenzhen 2016 material numbering and page-break truncations."""
import hashlib,json,os,re,subprocess,uuid
from pathlib import Path
from urllib.parse import quote
import round5_bulk as parser
from full_repair_answers_20261015 import answer_characters,validate_answer
from full_repair_layout_20261015 import format_essay
from paper_integrity_repair import set_fields
ROOT=Path(__file__).resolve().parents[1]
MAT=ROOT.parent/'gwy-material-ops'
DIRECTORY=MAT/'knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf/【33】深圳公务员考试真题pdf版/深圳公务员考试真题——申论（07~24年）'
REV='95676de3a494730fdcacd43416fd51d6bed48ab6'
CN=['','一','二','三','四','五','六','七','八','九','十','十一','十二','十三','十四','十五']
def sha(s):return hashlib.sha256(s.encode() if isinstance(s,str) else s).hexdigest()
def atomic(p,text):
    tmp=p.with_name(p.name+'.sz2016-'+uuid.uuid4().hex+'.tmp')
    try:tmp.write_bytes(text.encode());os.replace(tmp,p)
    finally:
        if tmp.exists():tmp.unlink()
def save(p,data):atomic(p,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def primary(answer):
    marker=re.search(r'<!-- full-repair-answer-20261015 -->\s*(.*?)\s*<!-- /full-repair-answer-20261015 -->',answer,re.S)
    if marker:return marker[1]
    s=re.split(r'\n\s*>\s*(?:出处|来源说明)',answer,1)[0]
    return re.sub(r'^\s*\*\*(?:来源参考作答|来源作文范文)\*\*\s*','',s).strip()
def main():
    receipt=ROOT/'reports/FULL-REPAIR-SHENZHEN-2016-MATERIALS-20261015.json'
    if receipt.exists():raise ValueError('Already applied; do not replay')
    env=dict(os.environ)
    if os.name=='nt':env.update(GIT_CONFIG_GLOBAL='NUL',GIT_CONFIG_NOSYSTEM='1')
    plans=[];sources={}
    for variant in ('A','B'):
        src=DIRECTORY/f'2016年深圳市公务员考试《申论》{variant}卷及参考答案.pdf.md';source_rel=src.relative_to(MAT).as_posix()
        raw=subprocess.check_output(['git','-c','core.fsmonitor=false','show',REV+':'+source_rel],cwd=MAT,env=env,timeout=90)
        text=raw.decode('utf-8').replace('\r\n','\n')
        if text!=src.read_text(encoding='utf-8'):raise ValueError('Source differs from fixed Git version')
        sources[variant]={'path':source_rel,'revision':REV,'git_blob':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),'sha256':sha(raw),'text':text}
    for variant in ('A','B'):
        rel=f'省考/深圳/2016/申论-{variant}类.md';p=ROOT/rel;old=p.read_text(encoding='utf-8');d=parser.parse(old,rel)
        prefix=old[:min(d['question_spans'].values())]
        starts=list(re.finditer(r'(?m)^材料([一二三四五六七八九十]+)[：:]\s*$',prefix))
        if len(starts)!=13:raise ValueError('Unexpected source material layout')
        materials={CN.index(m[1]):prefix[m.end():starts[i+1].start() if i+1<len(starts) else len(prefix)].strip() for i,m in enumerate(starts)}
        materials[13]=re.split(r'(?m)^\s*作答要求\s*$',materials[13],1)[0]
        materials[13]=re.sub(r'<!--.*?-->','',materials[13],flags=re.S).strip()
        split5=re.search(r'据统计，2014\s*年深圳国内专利申请量',materials[5]);split11=materials[11].find('新加坡是世界公认的综合性国际化城市')
        if not split5 or split11<0:raise ValueError('Merged material boundaries do not match fixed source')
        restored={1:materials[1],2:materials[2],3:materials[3],4:materials[4],5:materials[5][:split5.start()].strip(),6:materials[5][split5.start():].strip(),7:materials[6],8:materials[7],9:materials[8],10:materials[9],11:materials[10],12:materials[11][:split11].strip(),13:materials[11][split11:].strip(),14:materials[12],15:materials[13]}
        suffix='全盘情况，然后通过电台广播进行引导。'
        if suffix not in sources['A']['text'] or suffix not in sources['B']['text']:raise ValueError('Missing traffic continuation evidence')
        if not restored[9].endswith('掌握'):raise ValueError('Unexpected traffic truncation boundary')
        restored[9]+=suffix
        ending='全面提升核心竞争力和国际影响力。';tail=re.search(r'全面提升核心竞[^。]*$',restored[15])
        if tail:
            if not ending.startswith(tail[0]):raise ValueError('Unexpected final material truncation')
            restored[15]+=ending[len(tail[0]):]
        if not restored[15].endswith('。'):raise ValueError('Final material remains incomplete')
        # Same shared material, corroborated by the clearer A transcript.
        restored[7]=restored[7].replace('发挥了重大作业','发挥了重大作用')
        restored[8]=restored[8].replace('国家文化都对外文化交流','国家文化部对外文化交流')
        fm=re.match(r'\A---\n.*?\n---\n',old,re.S)[0]
        fm=set_fields(fm,{'给定材料数量':15,'对照题本题量':3,'实有题数':3,'缺失原题号':[],'题目分值':[20,30,50],'资料编号校核凭据':'reports/FULL-REPAIR-SHENZHEN-2016-MATERIALS-20261015.json'},'2026-10-15依固定同卷原稿恢复15则资料编号，补跨页尾句，纠正材料引用；保留旧库更清楚的正文，不倒灌原稿OCR错字。')
        url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(sources[variant]['path'],safe='/')
        new=fm+'# 2016年深圳市公务员考试《申论》试题（'+variant+'卷）\n\n> 申论 · 3 题 · 深圳 2016\n\n> 资料校勘：原来源将第5／6及第12／13则资料合并，现依同卷原稿拆回15则，题面材料号与原稿对应。正文保留较清晰的旧库转录，跨页缺尾据原稿补回；不是官方原件逐字认证。[固定版本原稿]('+url+')。\n\n'
        new+='\n\n'.join('材料'+CN[n]+'：\n\n'+restored[n].strip() for n in range(1,16))+'\n\n'
        questions={};answers=dict(d['answers'])
        for n,q in d['questions'].items():
            q=re.sub(r'<!--.*?-->','',q,flags=re.S).strip()
            q=q.replace('材料给定资料','材料'+str(({1:13,2:11} if variant=='A' else {1:4,2:8}).get(n,'')))
            questions[n]=q;new+='## 第 '+str(n)+' 题\n\n'+q+'\n\n'
        if variant=='B':
            body=primary(answers[2]);continuation='费派发观演指南，举办“文化演出进社区”、“文化演出校园行”，把演艺资源送到群众家门口，提高社会各界关注度和参与度。'
            if not body.endswith('免') or continuation not in sources['B']['text']:raise ValueError('Source answer continuation not established')
            answers[2]=answers[2].replace('地铁站点免','地铁站点免'+continuation,1)
            answers[2]+='\n\n> 跨页校勘：第5点原在页脚广告前截于“免”，现据同一原稿下一页接回“费派发观演指南……”完整续文。'
        metrics=[]
        for n,a in answers.items():
            a=a.replace('/blob/710cb9f85b9ae5e4167cbdd5172c59309a51c80e/','/blob/'+REV+'/');answers[n]=a
            count=validate_answer(questions[n],{'answer':primary(a),'attribution_kind':'owned_source','author':'来源参考；原资料未署名'})
            metrics.append({'number':n,'characters':count,'body_sha256':sha(primary(a))})
        new+='## 答案与解析\n\n'+'\n\n'.join('<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+answers[n]+'\n\n</details>' for n in (1,2,3))+'\n'
        new,layout=format_essay(new,rel)
        plans.append({'path':rel,'before_sha256':sha(old),'before_text':old,'after_sha256':sha(new),'new_text':new,'source':{k:v for k,v in sources[variant].items() if k!='text'},'answers':metrics,'layout':layout,'status':'prepared'})
    save(receipt,{'status':'prepared','papers':plans})
    for item in plans:
        p=ROOT/item['path']
        if p.read_text(encoding='utf-8')!=item['before_text']:raise ValueError('Concurrent paper edit')
        atomic(p,item['new_text']);item['status']='applied';save(receipt,{'status':'applied' if all(v['status']=='applied' for v in plans) else 'partially_applied','papers':plans})
    print(json.dumps({'status':'passed','papers':2,'materials_each':15,'answer_checks':[v['answers'] for v in plans]},ensure_ascii=False))
if __name__=='__main__':main()
