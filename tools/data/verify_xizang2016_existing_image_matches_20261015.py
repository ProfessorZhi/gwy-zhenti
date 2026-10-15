"""Read-only matched existing-image evidence for the Xizang2016 reconstruction owner."""
import re,json,hashlib
from pathlib import Path
from urllib.parse import quote
R=Path('.');H=lambda b:hashlib.sha256(b).hexdigest();BASE='f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab';proofs=[]
for rel,nums,files,kind in [
('省考/湖北/2016/行测-统考.md',[74],['图片/省考-湖北-2016-行测-统考/题目图/1546a306368bbfc.png'],'MOPS125_Q74_nine_grid'),
('省考/浙江/2016/行测-A类.md',[108,109,110,111,112],['图片/省考-浙江-2016-行测-A类/题目图/163388a8bbdeff6.png','图片/省考-浙江-2016-行测-A类/题目图/1633883acaad97e.png'],'MOPS125_Q116_120_courier_shared_tables')]:
 s=Path(rel).read_text(encoding='utf-8');front=s[:s.index('## 答案与解析')];qs={};ans={}
 for n in nums:
  m=re.search(r'(?m)^#{2,3}\s*第\s*'+str(n)+r'\s*题[^\n]*\n(.*?)(?=^#{1,3}\s|\Z)',front,re.S);assert m;qs[str(n)]=m[1].strip()
  m=re.search(r'<summary>第\s*'+str(n)+r'\s*题</summary>(.*?)</details>',s,re.S);assert m;ans[str(n)]=re.search(r'\*\*答案\*\*[：:]\s*([ABCD]+)',m[1])[1]
 proofs.append({'kind':kind,'donor_md':rel,'donor_md_sha256':H(Path(rel).read_bytes()),'donor_fixed_baseline_url':'https://github.com/ProfessorZhi/gwy-zhenti/blob/'+BASE+'/'+quote(rel,safe='/'),'donor_questions':qs,'donor_answer_keys':ans,'images':[{'path':p,'sha256':H(Path(p).read_bytes()),'fixed_baseline_url':'https://github.com/ProfessorZhi/gwy-zhenti/blob/'+BASE+'/'+quote(p,safe='/'),'visually_inspected':True} for p in files]})
proofs[0]['match_basis']={'rows_of_point_counts':[[5,6,7],[7,8,9],[9,10,11]],'option_point_counts':[11,11,10,12],'additional_shape_constraint':'题干格内部均有三角形；选项B无三角形，A满足','target_owned_source_question':74,'target_answer':'A','not_the_wrong_variant':'不是政华120版本的2014/1928数字图。','visual_boundary':'目标MOPS文字转录未携原图，依据同年联考题面、完整点数/三角形规律、全部选项顺序同题匹配；不声称取得了丢失原图后的逐像素直接比对。'}
values=[[19.93,23.79,28.32,3.09],[11.12,8.89,11.37,1.18],[11.13,7.07,12.57,1.09],[3.29,6.37,7.24,.91]];totals=[round(sum(x),2) for x in values];assert totals==[75.13,32.56,31.86,17.81]
proofs[1]['match_basis']={'target_owned_question_numbers':[116,117,118,119,120],'donor_question_numbers':[108,109,110,111,112],'table_title':'2015年2月对四家企业的每百万件快递业务有效申诉量','table_units':'件；环比变化率表单位为%','visually_read_values':values,'row_totals':totals,'visually_read_growth_rates':[[87,49,53,-46],[72,87,44,-38],[217,114,139,-9],[54,55,41,-48]],'context_matches':'2015年2月快递8.2亿件/136亿元，全国每百万件有效申诉23.4件，四企总计依次75.13/32.56/31.86/17.81，与MOPS125同组材料一致。','task_matches':'每笔收入、全部申诉量、1月丢失损毁排序、投递服务占比上升家数、综合判断五题对应且四选项次序一致；投递服务题个别稿“有效”字样存在行文差异，未擅自改目标原题。','not_inferred':'直接读取既有原表图像，不以解析/已知答案倒填表格。'}
Path('reports/XIZANG2016-EXISTING-IMAGE-MATCH-EVIDENCE-20261015.json').write_text(json.dumps({'status':'matched_existing_images','read_only_exam_content':True,'new_images_generated':0,'target_md_written':False,'proofs':proofs},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('MATCHED',len(proofs),'groups',sum(len(x['images']) for x in proofs),'existing images; zero MD/image mutations')
