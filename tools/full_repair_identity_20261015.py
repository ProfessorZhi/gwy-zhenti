"""Archive a demonstrated year-mislabeled duplicate without discarding its text."""
import hashlib,json,re
from pathlib import Path
from difflib import SequenceMatcher
import round5_bulk as parser
from paper_integrity_repair import set_fields
ROOT=Path(__file__).resolve().parents[1]
OLD='省考/河南/2018/申论-统考.md'
NEW='docs/来源校勘/原误标2018河南申论-实际2017重复来源.md'
def sha(t):return hashlib.sha256(t.encode('utf-8')).hexdigest()
def main():
    source=ROOT/OLD;dest=ROOT/NEW
    if not source.exists():raise ValueError('Already archived or missing source')
    if dest.exists():raise ValueError('Do not overwrite existing archive')
    text=source.read_text(encoding='utf-8');canonical='省考/河南/2017/申论-统考.md'
    a=parser.parse(text,OLD);b=parser.parse((ROOT/canonical).read_text(encoding='utf-8'),canonical)
    matches=[]
    for n,q in a['questions'].items():
        # Old source appended unassigned material to its last question; match the stem.
        key=parser.qkey(q.split('## 附：')[0]);scores=sorted((SequenceMatcher(None,key,parser.qkey(v).split('附源内')[0],autojunk=False).ratio(),m) for m,v in b['questions'].items())
        best,m=scores[-1]
        if best<.86:raise ValueError('Not sufficiently matched to 2017 task '+str((n,best)))
        matches.append({'old_number':n,'canonical_2017_number':m,'stem_similarity':best})
    if len({m['canonical_2017_number'] for m in matches})!=4:raise ValueError('Nonunique exam identity match')
    front=set_fields(text,{'原标年份':'2018','核实所属年份':'2017','真题性质':'第三方误标年份来源留存；不作为2018河南真题','收录状态':'已校勘归档，不计独立试卷覆盖','身份校核凭据':'reports/FULL-REPAIR-IDENTITY-DISPOSITION-20261015.json'},'2026-10-15按四题题干指纹及2017公开题面确认原标2018为第三方年份误标；完整原稿移入来源校勘档案，不计新卷。')
    title=re.search(r'(?m)^# [^\n]+\n',front)
    notice='\n> **年份纠错留存稿。** 本稿原来源误标为2018河南，四道题均与2017河南制造业转型试卷对应；2018河南未开展该年度公务员招录。此处完整保留来源文字和既有作答供校勘，正文内的2018春节等年份不作为事实依据。正式练习入口：[2017河南申论](../../'+canonical+')。\n\n> 年份依据：[2017河南原题节选](http://www.hngwyw.com.cn/2022/0224/82959.html)；[中国网转述2018未招录事实](https://henan.china.com.cn/m/2020-06/11/content_41181181.html)。\n'
    archived=front[:title.end()]+notice+front[title.end():]
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(archived,encoding='utf-8',newline='\n')
    record={'relocations':{OLD:NEW},'source_before_sha256':sha(text),'archive_after_sha256':sha(archived),'canonical_2017':canonical,'question_matches':matches,'evidence':[{'url':'http://www.hngwyw.com.cn/2022/0224/82959.html','supports':'2017河南“制造业不变等死变则找死”同题和2017春节统计原文'},{'url':'https://henan.china.com.cn/m/2020-06/11/content_41181181.html','supports':'来源核实2018河南未开展该年公务员招录；不能以选调题替代省考'}],'boundary':'Archive preserves the full prior transcript; no invented replacement exam and no loss of original source text.'}
    (ROOT/'reports/FULL-REPAIR-IDENTITY-DISPOSITION-20261015.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'prepared':True,'source':str(source.resolve()),'destination':str(dest.resolve()),'matches':matches},ensure_ascii=False))
    # The exact original file is removed only by the caller after reviewing the
    # fully resolved source/destination and the verified archive hash.
if __name__=='__main__':main()
