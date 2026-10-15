"""Copy the visually verified four original six-hexagon-distance options."""
from pathlib import Path
import hashlib,json
import fitz
ROOT=Path(__file__).resolve().parents[2];source=Path(r'D:\artifacts\gwy-quality-audit-20261015\tibet2016-zhenghua-original.pdf')
assert hashlib.sha256(source.read_bytes()).hexdigest()=='6b2679510c52d570520271dc06303927d8f5c2785bb09af68a87275a1037e5ea'
doc=fitz.open(source);rows=[]
for letter,xref,value in [('A',56,'50(√3−1)'),('B',58,'50√3'),('C',60,'25(√2+1)'),('D',62,'50√2')]:
    raw=doc.extract_image(xref);p=ROOT/f'图片/修复-20261015/西藏2016-MOPS62-选项{letter}.{raw["ext"]}'
    if p.exists():raise ValueError('No overwrite of original image')
    p.write_bytes(raw['image']);rows.append({'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(raw['image']).hexdigest(),'source_page':14,'source_xref':xref,'pdf_question':66,'target_reference_question':62,'letter':letter,'visually_read_formula':value,'unit':'米（PDF原式外的独立文字）'})
(ROOT/'reports/FULL-REPAIR-TIBET2016-MATH-OPTIONS-20261015.json').write_bytes((json.dumps({'source_pdf_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'method':'original embedded bytes; all four values and option order visually checked against original full page','images':rows},ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps(rows,ensure_ascii=False),flush=True)
