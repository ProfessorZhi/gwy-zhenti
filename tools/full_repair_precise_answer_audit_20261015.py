"""Read-only main-answer extraction independent of historic r7 heuristics.

No source URL, byline or teacher commentary contributes to body length. Findings
are review candidates; ambiguous alternative versions and per-item limits are
never combined into a fictional complete composition or an aggregate maximum.
"""
from __future__ import annotations
import argparse,collections,hashlib,html,json,re,unicodedata
from pathlib import Path
import round5_bulk as parser

ROOT=Path(__file__).resolve().parents[1]
MARKER=re.compile(r'<!-- full-repair-answer-20261015 -->\s*(.*?)\s*<!-- /full-repair-answer-20261015 -->',re.S)
SOURCE_LINE=re.compile(r'^\s*(?:>\s*)?(?:来源说明|来源|出处|资料出处|答文出处|参考原稿出处|原稿出处|本题来源记录|原资料|原参考稿固定版本|来源链接|原文链接|原稿链接|整理说明|作者[／/和]?整理性质|作者署名|作者|版权说明|字数异文|原参考正文|篇幅校勘|课程练习|使用说明)[：:（(\s]')
ANALYSIS_LINE=re.compile(r'^\s*(?:#{1,6}\s*|\*\*)?(?:[【\[]\s*)?(?:参考答案说明|文章分析|范文分析|范文点评|例文点评|题目精析|题目解析|解题思路|审题(?:及答题思路|得出答题思路)?|答题思路|写作思路|论证分析|评分细则|参考评分|答题演示|第[一二三四五六七八九十]+步[—－-]|解析)(?:[】\]:：\s*]|$)')
GENERIC_LINE=re.compile(r'^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:来源作文范文|来源参考作答|同题来源参考作答(?:（[^\n]*?）)?|同题来源参考范文(?:（[^\n]*?）)?|同题参考作答|AI辅助(?:原创|修订)示范作答|参考答案|参考例文|参考范文|参考作答|参考文章|【参考答案】|【参考例文】|【参考作答】|【范文】)(?:\*\*)?\s*[:：]?\s*$')
VERSION_LINE=re.compile(r'(?m)^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:参考文章|参考范文|范文|例文|参考答案)[一二三四五六七八九十\d]+[ \t]*(?:[:：、.．][ \t]*|(?:\*\*)?[ \t]*$)|^\s*(?:#{1,6}\s*)?参考答案\s*[（(][FHＡＢAB甲乙][）)]\s*[:：]?\s*$')
SOURCE_LINK_LABEL=re.compile(r'原资料|固定版本|本题来源|来源记录|来源链接|出处|原稿|原文|公开解析|同题来源|查看.*来源|本题依据')
PLACEHOLDER=re.compile(r'此处(?:可以写|填写|补充|展开)|后接材料.*信息|具体表述缺失|正文(?:暂缺|待补)|(?:本题)?尚未收录|答案(?:暂缺|略)|(?:待补充|待填写|TODO|PLACEHOLDER)|\[\s*待[^\]]*\]',re.I)
NUM={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}

def char_count(text):
    text=re.sub(r'<!--.*?-->','',text,flags=re.S)
    text=re.sub(r'<[^>]+>','',text)
    text=re.sub(r'!\[[^\]]*\]\([^)]*\)','',text)
    text=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',text)
    text=re.sub(r'https?://[^\s<>]+','',text)
    return len(re.sub(r'\s|[#*`]','',html.unescape(text)))

def strip_body(text):
    """Preserve normal titles and textual labels; remove metadata and commentary."""
    raw=text;text=html.unescape(text)
    text=re.sub(r'<!--.*?-->','',text,flags=re.S)
    text=re.sub(r'<br\s*/?>','\n',text,flags=re.I)
    text=re.sub(r'</?(?:p|div|summary|details)[^>]*>','\n',text,flags=re.I)
    text=re.sub(r'<[^>]+>','',text)
    out=[];removed=[];analysis_only=False
    for line in text.splitlines():
        s=line.strip()
        if not s:out.append('');continue
        if re.fullmatch(r'(?:\*\*)?(?:来源参考答案|发布方参考答案|原创示范作答)(?:[（(][^\n]*[）)])?(?:\*\*)?',s):removed.append('generic_answer_label');continue
        if re.match(r'^>\s*\*\*同题参考答案[^\n]*\*\*',s):removed.append('source_matching_note');continue
        if re.match(r'^(?:>\s*)?(?:写作依据[：:]|同题机构参考作答[／/]|题面与参考答案公开来源)',s):
            removed.append('source_or_note_footer')
            if char_count('\n'.join(out))>0:break
            continue
        if GENERIC_LINE.fullmatch(s):removed.append('generic_answer_label');continue
        if re.fullmatch(r'(?:作者[：:]|文[／/])\s*[\w\u4e00-\u9fff·]{2,24}',s):removed.append('byline');continue
        if SOURCE_LINE.match(s):
            removed.append('source_or_note_footer')
            if char_count('\n'.join(out))>25:break
            continue
        standalone=re.fullmatch(r'\[([^\]]+)\]\((?:https?://)[^)]+\)(?:[（(][^\n]*[）)])?',s)
        if standalone and SOURCE_LINK_LABEL.search(standalone[1]):removed.append('standalone_source_link');continue
        if ANALYSIS_LINE.match(s) or re.match(r'^(?:#{1,6}\s*)?(?:文章分析\s*\d+\s*$|参考范文[一二三四五六七八九十]+文章分析[：:]|第[一二三四五六七八九十]+步\s*(?:审题|阅读资料))',s):
            removed.append('teacher_analysis_boundary');analysis_only=char_count('\n'.join(out))<20;break
        if re.match(r'^\s*获取试卷更新，请关注公众号',s):removed.append('advertisement');continue
        if re.fullmatch(r'(?:第\s*\d+\s*页\s*共\s*\d+\s*页|-\s*\d+\s*-)',s):removed.append('page_footer');continue
        s=re.sub(r'!\[[^\]]*\]\([^)]*\)','',line)
        s=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',s)
        if re.search(r'https?://',s):removed.append('url_not_counted')
        s=re.sub(r'https?://[^\s<>]+','',s)
        out.append(s)
    body=re.sub(r'\n{3,}','\n\n','\n'.join(out)).strip()
    body=re.sub(r'[（(]\s*\d{1,4}\s*字\s*[）)]\s*$','',body).rstrip()
    # Generic inline leading answer tags are envelopes, never essay titles.
    body=re.sub(r'^\s*(?:第\s*[一二三四五六七八九十\d]+\s*(?:道)?题\s*)?(?:【参考答案】|【参考例文】|【参考作答】|参考答案\s*[:：]|参考例文\s*[:：]|答案\s*[:：])\s*','',body)
    return {'body':body,'characters':char_count(body),'raw_characters':char_count(raw),'removed_rules':sorted(set(removed)),'analysis_only':analysis_only}

def extract_versions(answer):
    marked=list(MARKER.finditer(answer))
    if marked:
        chunks=[(f'marker_{i+1}',m[1]) for i,m in enumerate(marked)]
        method='explicit_main_body_marker'
    else:
        markers=list(VERSION_LINE.finditer(answer));method='legacy_body_boundaries'
        if markers:
            chunks=[(answer[m.start():m.end()].strip(),answer[m.end():markers[i+1].start() if i+1<len(markers) else len(answer)]) for i,m in enumerate(markers)]
            prefix=answer[:markers[0].start()]
            if char_count(strip_body(prefix)['body'])>45:chunks.insert(0,('unlabelled_prefix',prefix))
        else:chunks=[('main',answer)]
    result=[]
    for label,text in chunks:
        row=strip_body(text);row.update(version=label,extraction_method=method);result.append(row)
    return result

def word_rules(question):
    q=unicodedata.normalize('NFKC',html.unescape(question))
    per=re.search(r'(?:每(?:个问题|道题|小题|项|问)|各(?:小题|题|问)?)[^。；;\n]{0,24}?(?:不(?:得)?超过|不多于|至多)\s*(\d{1,4})\s*字',q)
    if per:
        expected=re.search(r'(?:讨论了|回答|分别阐述|分为)?\s*([一二两三四五六七八九十\d]+)\s*个问题',q)
        count=NUM.get(expected[1],int(expected[1]) if expected and expected[1].isdigit() else 0) if expected else 0
        return {'kind':'per_item_maximum','maximum':int(per[1]),'expected_items':count,'confidence':'high','evidence':per[0]}
    ranges=list(re.finditer(r'(\d{2,4})\s*字?\s*[-—－–~～至到]{1,2}\s*(\d{2,4})\s*字',q))
    maxima=list(re.finditer(r'(?:不(?:得)?超过|不超|不多于|至多)\s*(\d{1,4})\s*字|(\d{1,4})\s*字\s*(?:以内|以下)',q))
    minima=list(re.finditer(r'(?:不少于|不低于|至少)\s*(\d{1,4})\s*字|(\d{1,4})\s*字\s*以上',q))
    distinct_max={int(m[1] or m[2]) for m in maxima}
    if len(distinct_max)>1 or len(maxima)>1 and re.search(r'分别|小问|[（(]1[）)].*[（(]2[）)]',q,re.S):return {'kind':'multiple_task_limits','maxima':sorted(distinct_max),'ordered_maxima':[int(m[1] or m[2]) for m in maxima],'confidence':'manual','evidence':[m[0] for m in maxima]}
    if ranges:
        m=ranges[-1];return {'kind':'explicit_range','minimum':int(m[1]),'maximum':int(m[2]),'confidence':'high','evidence':m[0]}
    if minima and maxima:
        a=minima[-1];b=maxima[-1];return {'kind':'explicit_range','minimum':int(a[1] or a[2]),'maximum':int(b[1] or b[2]),'confidence':'high','evidence':a[0]+'；'+b[0]}
    if minima:
        m=minima[-1];return {'kind':'explicit_minimum','minimum':int(m[1] or m[2]),'confidence':'high','evidence':m[0]}
    if maxima:
        m=maxima[-1];return {'kind':'explicit_maximum','maximum':int(m[1] or m[2]),'confidence':'high','evidence':m[0]}
    m=re.search(r'(\d{2,4})\s*字\s*左右',q)
    if m:
        target=int(m[1]);return {'kind':'approximate_target','target':target,'review_minimum':int(target*.9),'review_maximum':int(target*1.12),'confidence':'medium','evidence':m[0]}
    return {'kind':'unspecified','confidence':'manual','evidence':''}

def task_kind(question,rules):
    if max(rules.get('minimum',0),rules.get('target',0))>=700:return 'composition'
    if rules.get('maximum',0) and rules['maximum']<=600:return 'short_answer'
    return 'composition' if re.search(r'议论(?:文|性文章)|策论文|写一篇文章|写一篇.{0,6}文章',question) else 'short_answer'

def split_items(body):
    parts=re.split(r'(?m)(?=^\s*(?:第[一二三四五六七八九十]+[，、：:]|[一二三四五六七八九十]+[、.]|[（(][一二三四五六七八九十\d]+[）)]|\d+[、.]))',body)
    return [p.strip() for p in parts if p.strip()]

def inspect_version(question,version,rules):
    body=version['body'];n=version['characters'];issues=[];kind=task_kind(question,rules)
    def add(rule,confidence,detail):issues.append({'rule':rule,'confidence':confidence,'detail':detail})
    if not n:add('no_main_body','high','剥离来源、解析与标签后未识别到独立作答正文')
    if version['analysis_only']:add('analysis_without_separate_answer','medium','仅见解析标题，需人工核实是否另有明确作答正文')
    if PLACEHOLDER.search(body):add('outline_or_placeholder','high','正文含明确省略、待补或写作指令，不能直接计为完整答文')
    if rules['kind']=='per_item_maximum':
        parts=split_items(body);expected=rules.get('expected_items',0)
        if len(parts)<2 or expected and len(parts)!=expected:add('per_item_needs_manual_split','manual','题目有逐项限额，当前分项无法可靠对应，不以全文合计判超限')
        else:
            counts=[char_count(p) for p in parts];version['per_item_characters']=counts
            if any(c>rules['maximum'] for c in counts):add('per_item_maximum_exceeded','high',f'各项实字数{counts}，单项上限{rules["maximum"]}')
    elif rules['kind']=='multiple_task_limits':
        labels=list(re.finditer(r'(?m)^\s*第[（(](\d+)[）)]小题\s*$',body));limits=rules.get('ordered_maxima',[])
        if labels and [int(m[1]) for m in labels]==list(range(1,len(limits)+1)):
            values=[char_count(body[m.end():labels[i+1].start() if i+1<len(labels) else len(body)]) for i,m in enumerate(labels)]
            version['per_item_characters']=values
            if any(v>limit for v,limit in zip(values,limits)):add('per_item_maximum_exceeded','high',f'各小问正文{values}字，对应上限{limits}字')
        else:add('multiple_limits_manual_review','manual','识别到不同小问字数上限，不把它们合成整题上限')
    else:
        if n and rules.get('minimum') and n<rules['minimum']:add('explicit_minimum_not_met','high',f'正文{n}字，低于题面明确下限{rules["minimum"]}字')
        if rules.get('maximum') and n>rules['maximum']:add('explicit_maximum_exceeded','high',f'正文{n}字，超过题面明确上限{rules["maximum"]}字')
        if rules['kind']=='approximate_target':
            if n and n<rules['review_minimum']:add('approximate_target_short','medium',f'正文{n}字，少于约{rules["target"]}字目标的90%；这是候选阈值，不是假定官方最低分界')
            if n>rules['review_maximum']:add('approximate_target_long','medium',f'正文{n}字，高于约{rules["target"]}字目标的112%；需按题面与答题空间复核')
        if kind=='composition' and rules['kind']=='unspecified':
            add('composition_limit_missing','manual','题干未保留明确字数要求，不能用解析器现状冒充完整原题约束')
            if 0<n<700:add('composition_appears_short','medium',f'仅{n}字且题干写文章，需先核完整原题限制及是否为提纲')
        if kind=='short_answer' and 0<n<min(45,max(15,int(rules.get('maximum',200)*.2))):add('very_short_main_body','medium',f'真实正文仅{n}字，需结合材料判断是否为完整答案；不自动认定缺失')
    # Positive lexical evidence, never punctuation absence by itself.
    tail=re.sub(r'\s|[#*`]|</?[^>]+>','',body).rstrip('。！？!?.；;，,：:”」』）)')
    match=re.search(r'(?:地铁站点免|最美家|进一步加|进一步完善相|以便|从而|以及|并且|例如|包括|[为对把将]其|免)$',tail)
    if match:add('possible_truncated_final_word','medium','末尾为疑似未完成词组“'+match[0]+'”；须按来源逐字核对，不能仅凭标点自动改写')
    elif n>=100 and body.rfind('“')>body.rfind('”') and len(body)-body.rfind('“')<70:
        add('possible_truncation_inside_final_quote','medium','正文止于最后一处未闭引号内且距引号不足70字；需查原文，不因缺标点自动修改')
    return kind,issues

def audit(root=ROOT):
    root=Path(root);candidates=[];allrows=[];parse_errors=[];counts=collections.Counter()
    for p in sorted([*root.glob('国考/*/申论*.md'),*root.glob('省考/*/*/申论*.md')]):
        rel=p.relative_to(root).as_posix();text=p.read_text(encoding='utf-8')
        try:paper=parser.parse(text,rel)
        except Exception as exc:parse_errors.append({'path':rel,'error':str(exc)});continue
        counts['papers']+=1
        for number,question in paper['questions'].items():
            counts['tasks']+=1;answer=paper['answers'].get(number,'');versions=extract_versions(answer);rules=word_rules(question);rows=[]
            for version in versions:
                kind,issues=inspect_version(question,version,rules);row={'path':rel,'question_number':number,'question':question,'task_kind':kind,'word_rules':rules,'version':version['version'],'extraction_method':version['extraction_method'],'characters':version['characters'],'raw_answer_characters_without_urls':version['raw_characters'],'removed_rules':version['removed_rules'],'per_item_characters':version.get('per_item_characters'),'body_sha256':hashlib.sha256(version['body'].encode()).hexdigest(),'start_excerpt':version['body'][:220],'end_excerpt':version['body'][-180:],'issues':issues};rows.append(row);counts['versions']+=1
            if len(rows)>1 and any(r['characters']>0 for r in rows):
                for row in rows:
                    if row['characters']==0:row['issues']=[{'rule':'empty_alternate_version_label','confidence':'manual','detail':'此处仅有另一个版本标签而无正文，不等于整题缺答案；应核是否是多余空标签'}]
            valid=any(not r['issues'] for r in rows)
            for row in rows:
                row['another_version_without_findings']=len(rows)>1 and valid
                if row['issues']:
                    candidates.append(row)
                    for issue in row['issues']:counts[issue['rule']]+=1
                allrows.append(row)
    return {'status':'review_candidates' if candidates or parse_errors else 'no_candidates_under_current_rules','scope':'当前申论MD真实主作答；独立于旧r7/is_missing，不改历史466检查','counting_convention':'剥除格式、URL、署名与解析后按非空白字符计字，保留正常标题、标点；ASCII字母逐个计数。此为一致的库内复核口径，不宣称等同官方答题格或评分细则。','counts':dict(counts),'candidate_tasks':len({(r['path'],r['question_number']) for r in candidates}),'candidate_versions':len(candidates),'parse_errors':parse_errors,'candidates':candidates,'all_extracted_versions':allrows,'boundary':'候选不是官方评分或自动修订指令。每版独立计字；有合规主版本时，其他版本的候选不能直接说成整题缺答案。正文分小问无法可靠切分者只标人工复核。来源URL、署名和附解析不贡献正文字数。'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);ap.add_argument('--output',type=Path);args=ap.parse_args();result=audit(args.root)
    if args.output:
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        md=['# 申论真实主作答审计候选','',result['boundary'],'',f'当前{result["counts"].get("papers",0)}份MD，{result["counts"].get("tasks",0)}题；候选{result["candidate_tasks"]}题、{result["candidate_versions"]}个版本。','','| 文件／题 | 主文实字数 | 类型／规则 | 摘要末尾 |','|---|---:|---|---|']
        for r in result['candidates']:md.append('| '+r['path']+' #'+str(r['question_number'])+' '+r['version']+' | '+str(r['characters'])+' | '+'；'.join(i['rule']+'('+i['confidence']+')' for i in r['issues'])+' | '+r['end_excerpt'][-75:].replace('\n',' ').replace('|','／')+' |')
        args.output.with_suffix('.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('candidates','all_extracted_versions')},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
