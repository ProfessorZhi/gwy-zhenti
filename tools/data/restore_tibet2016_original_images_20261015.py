"""Extract original source images; never redraw a question or infer absent data."""
from pathlib import Path
import hashlib,json
import fitz
ROOT=Path(__file__).resolve().parents[2];BASE=Path(r'D:\artifacts\gwy-quality-audit-20261015')
PDF=BASE/'tibet2016-zhenghua-original.pdf';SOURCE='http://zhenghuajiaoyu.cn/uploads/test/20220429/c0fd32b299da312ce4acda2bd077fd04.pdf'
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(PDF.read_bytes())=='6b2679510c52d570520271dc06303927d8f5c2785bb09af68a87275a1037e5ea'
doc=fitz.open(PDF);dest=ROOT/'图片/修复-20261015';dest.mkdir(exist_ok=True)
specs=[
 (16,'地貌',2,23),(69,'题干图',14,64),(69,'选项A',14,65),(69,'选项B',14,66),(69,'选项C',15,69),(69,'选项D',15,70),
 (71,'题图与选项',17,79),(72,'题图与选项',15,71),(73,'六图分类',16,75),(75,'题图与选项',16,76),
 (111,'运输资料原表',24,94),(121,'租赁贸易资料原图',26,143)
]
rows=[]
for task,label,page,xref in specs:
    extracted=doc.extract_image(xref);data=extracted['image'];name=f'西藏2016-MOPS{task}-{label}.{extracted["ext"]}';p=dest/name
    if p.exists():raise ValueError('Existing original image must not be overwritten: '+str(p))
    p.write_bytes(data)
    rows.append({'mops_source_task':task,'label':label,'path':p.relative_to(ROOT).as_posix(),'source_page':page,'source_xref':xref,'method':'unchanged original embedded image bytes','sha256':sha(data),'width':extracted['width'],'height':extracted['height']})
# This material has several percentages embedded as tiny formula images. Rendering
# a bounded original region retains all of them and the complete source wording.
clip=fitz.Rect(35,60,558,433);pix=doc[24].get_pixmap(matrix=fitz.Matrix(2,2),clip=clip)
p=dest/'西藏2016-MOPS106-国企资料原文.png'
if p.exists():raise ValueError('Existing original render must not be overwritten')
pix.save(p);rows.append({'mops_source_task':106,'label':'国企资料原文','path':p.relative_to(ROOT).as_posix(),'source_page':25,'clip_pdf_points':list(clip),'render_scale':2,'method':'direct original page-region render; no source text or numeric data changed','sha256':sha(p.read_bytes()),'width':pix.width,'height':pix.height})
proof={'source_url':SOURCE,'source_pdf_sha256':sha(PDF.read_bytes()),'source_pages':27,'source_version_last_question':120,'version_boundary':'This public 120-task arrangement differs from the user-provided 125-task reference. Only individually matched diagrams/materials are reused. It contains no courier-material group and cannot authenticate the entire 125-task order.','images':rows}
(ROOT/'reports/FULL-REPAIR-TIBET2016-ORIGINAL-IMAGE-EXTRACTION-20261015.json').write_bytes((json.dumps(proof,ensure_ascii=False,indent=2)+'\n').encode())
for r in rows:print(r['mops_source_task'],r['label'],r['path'],flush=True)
