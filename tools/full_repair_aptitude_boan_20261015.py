#!/usr/bin/env python3
"""Restore the matching bank-protection options as an attributed source image."""
from pathlib import Path
import json,hashlib,re,argparse
R=Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def apply(source_image):
 p=R/'省考/江苏/2024/行测-C类.md';old=p.read_text(encoding='utf8');imgrel='图片/修复-20261015/江苏2024C110-options.png';img=R/imgrel
 image_bytes=source_image.read_bytes();img.parent.mkdir(parents=True,exist_ok=True)
 if img.exists():assert img.read_bytes()==image_bytes,'Do not overwrite existing image'
 else:img.write_bytes(image_bytes)
 front,ans=old.split('## 答案与解析',1);m=re.search(r'(^## 第 110 题[^\n]*\n)(.*?)(?=^## )',front,re.M|re.S)
 assert m and '- **A**. 缺失' in m[2]
 stem=m[2].split('- **A**.',1)[0].rstrip()
 body=stem+'\n\n![第110题选项图A至D](../../../'+imgrel+')\n\n'+ '\n'.join('- **'+k+'**. 见上图'+k for k in 'ABCD')+'\n\n> 选项原图据[搜狐号“教学视频分享”同题第10题](https://www.sohu.com/a/988893344_121124033)补回（2026-02-21发布，2026-10-15校对）；图中字母对应本题A—D，不以来源原占位默认字母判分。\n\n'
 front=front[:m.start()]+m[1]+body+front[m.end():]
 m=re.search(r'(<details>\s*<summary>第 110 题</summary>)(.*?)(</details>)',ans,re.S);assert m
 body='''\n\n**答案**：B

**原创校核解析（AI辅助整理，非官方标准答案）**

定义要求在人水交界处，以砖石、植被、混凝土等建造保护性工程。A为园林水岸的人工构景，C为石块砌筑的护岸，D为利用植被形成的护岸，均具有人为建造并保护水岸的特征。B为天然海岸的地貌，没有题干要求的人工保护性工程，不属于驳岸，选B。

**来源与版本说明**：选项图来自搜狐号“教学视频分享”2026-02-21《每日限时｜判断推理刷题打卡（2.21）》第10题，[文章链接](https://www.sohu.com/a/988893344_121124033)。该页未署个人作者；机构身份未明确，不冒称官方答案或机构授权版本。源图[原始地址](https://q2.itc.cn/q_70/images03/20260221/afb1f2537bff4f86850cdf199135e3d4.png)。答案由本库依据完整题干和选项图重新判断，并与来源展示答案B交叉核对。旧源缺选项时的默认B此前已撤销，本次B有完整图示与推理支持。

'''
 ans=ans[:m.start()]+m[1]+body+m[3]+ans[m.end():];new=front+'## 答案与解析'+ans
 p.write_text(new,encoding='utf8',newline='\n')
 receipt={'path':p.relative_to(R).as_posix(),'before_sha256':sha(old.encode()),'after_sha256':sha(new.encode()),'question':110,'answer':'B','image_path':imgrel,'image_sha256':sha(image_bytes),'source_url':'https://www.sohu.com/a/988893344_121124033','source_image_url':'https://q2.itc.cn/q_70/images03/20260221/afb1f2537bff4f86850cdf199135e3d4.png','source_kind':'公开同题选项图；独立原创校核解析','restored_options':['A','B','C','D']}
 (R/'reports/FULL-REPAIR-APTITUDE-BOAN-20261015.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8');return receipt
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--source-image',type=Path,required=True);a=ap.parse_args();print(json.dumps(apply(a.source_image),ensure_ascii=False))
