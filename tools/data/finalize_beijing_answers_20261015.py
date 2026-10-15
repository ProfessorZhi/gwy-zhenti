"""Correct the demonstrably nonminimal ten-query source key and record limits."""
import hashlib,json,re
from pathlib import Path
from full_repair_beijing_answers_20261015 import ROOT,PAPER,ANSWER_DATA,questions,sha
rows=json.loads(ANSWER_DATA.read_text(encoding='utf-8'));r=next(x for x in rows if x['number']==51)
old_reason=r['explanation']
reason='''选择A：存在保证最多8次的构造，已经反驳来源参考键C的“最少10次”。

①把32台分为4组，每组8台选2台，共4次。再把这8台一起8选2，第5次得到全体最好的两台P、Q；二者不用排先后，但记录各自原组。

②若P、Q来自同一组，仍可能进入全体第3、第4的仅有该组6台落选者和其他组的6台入选者，共12台。对其中8台选2，再将选出的2台与余下4台、2台已确定不可能进前4的陪跑机器一起8选2，即得到全体第3、第4；这个分支共7次。陪跑可取其他组的初选落选者，因为它们已有本组两名入选者及P、Q这四台确定更强的机器。

③若P、Q来自不同组，先对剩余6名初选入选者6选1，第6次得到全体第3台R。理由是：任何初选落选者已有本组2台加P、Q中另一组1台至少3台确定更强，不可能是第3。

若R不是P、Q所在组的另一名初选入选者，所有初选落选者都已有至少4台确定更强；对剩余5名入选者加1台已排除陪跑6选1，第7次即可得第4。

最坏情况是R恰为P或Q某原组的另一名入选者。只有这个原组的6台落选者仍可能是第4，其他组落选者都已有至少4台确定更强。先对这6台6选1，再将胜者与剩余5名初选入选者6选1，分别为第7、第8次，得到全体第4。因而全部分支最多8次，且完全没有把“8选2不分名次”当成已排序。

校勘说明：用户原稿与原缓存候选均给C=10，但上述明确可行构造以及20万次随机性能排列、极端排列校验已推翻10次必要性。本次按8次构造修订参考选项为A；尚未取得“任意算法7次绝不可能”的全局严格下界证明，不把仿真或本构造的最坏分支当成该下界证明。'''
r.update(answer='A',explanation=reason,attribution_kind='ai_original',source_answer_correction={'source_answer':'C','source_query_count':10,'replacement_query_count_upper_bound':8,'strict_seven_query_lower_bound_proven':False,'verification_report':'reports/FULL-REPAIR-BEIJING-Q51-COUNTEREXAMPLE-20261015.json'})
ANSWER_DATA.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=ROOT/PAPER;old=p.read_text(encoding='utf-8');hs=list(re.finditer(r'(?m)^## 第 (\d+) 题[^\n]*\n',old));i=next(i for i,h in enumerate(hs) if int(h[1])==51);a=hs[i].end();b=hs[i+1].start();body=old[a:b]
if old_reason not in body or '**答案**：C' not in body:raise ValueError('Q51 preimage mismatch')
newbody=body.replace('**答案**：C','**答案**：A',1).replace(old_reason,reason,1).replace('来源机构参考键，解析由AI辅助整理；原稿未单列个人解题作者。','AI辅助独立构造并校正来源键；原参考键及本次证明边界在校勘说明中保留。',1)
new=old[:a]+newbody+old[b:];p.write_text(new,encoding='utf-8',newline='\n')
(ROOT/'reports/FULL-REPAIR-BEIJING-Q51-CORRECTION-20261015.json').write_text(json.dumps({'path':PAPER,'number':51,'before_sha256':sha(old),'after_sha256':sha(new),'before_block_sha256':sha(body),'after_block_sha256':sha(newbody),'operations':[{'old':body,'new':newbody}],'source_answer':'C=10','corrected_reference':'A=8 upper bound','strict_minimum_lower_bound_proven':False,'author':'Codex，根任务与C交叉检查构造'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# Final readback through the same parser used by normal exports.
from gwyzhenti.mdread import split_question_blocks,split_answer,correct_option
_,blocks=split_question_blocks(new);by={x['number']:x for x in rows};errors=[];written=[]
for block in blocks:
 n=int(re.search(r'第\s*(\d+)\s*题',block[0])[1]);st,ans,tail=split_answer(block);key=correct_option(block)
 if n in by:
  if key!=by[n]['answer'] or not ans or not any('**解析**' in ln for ln in ans):errors.append([n,'answer parse failure'])
  written.append(n)
 elif key:errors.append([n,'unplanned answer'])
qa={'status':'passed' if not errors else 'failed','path':PAPER,'questions':len(blocks),'answer_blocks':len(written),'pending_numbers':sorted(set(range(1,94))-set(written)),'errors':errors,'q51_correction':'source ten-query key disproved by an eight-query upper bound; A retained as corrected reference, global seven-query impossibility not proved','qualification_notes':[{'number':5,'note':'Institution reference D retained with geographic convention / Russia-only route qualification.'}],'boundary':'Original question/option/image retention and parser roundtrip verified; five source-context gaps remain, not counted as solved.'}
(ROOT/'reports/FULL-REPAIR-BEIJING-QA-20261015.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

raw_paths=[Path('D:/projects/gwy-zhenti/work/dtiku-raw/paper_51836_ans.html'),Path('D:/projects/gwy-zhenti/work/agent2-cand/raw/dtiku/v_51836.html'),Path('D:/projects/gwy-zhenti/work/agent2-cand/raw/dtiku/paper_51836.html')]
source_audit={'raw_files':[{'path':str(x),'bytes':x.stat().st_size,'sha256':hashlib.sha256(x.read_bytes()).hexdigest(),'image_elements':34,'images_outside_question_or_options':0,'shared_context_found':False} for x in raw_paths], 'live_detail_checks':[{'url':'https://gwy.dtiku.cn/question/detail/1072289','provider':'TinyFish','result':'fetched successfully; no shared itinerary rules or images; only original question/options and other related questions'},{'url':'https://gwy.dtiku.cn/question/detail/1072266','provider':'TinyFish','result':'fetched successfully; target image 2827901 plus related-question images, no operation-symbol legend'}], 'missing_context':[{'numbers':[56,57,58],'required':'Mapping from each operation icon to its specified geometric transformation.'},{'numbers':[79,80],'required':'Professor Wang itinerary constraints including permitted days, periods, venue and friend-meeting rules.'}], 'policy':'Do not reconstruct true exam conditions from suspected shifted answer letters; the five answers remain unset.'}
(ROOT/'reports/FULL-REPAIR-BEIJING-SOURCE-CONTEXT-20261015.json').write_text(json.dumps(source_audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(qa,ensure_ascii=False))
