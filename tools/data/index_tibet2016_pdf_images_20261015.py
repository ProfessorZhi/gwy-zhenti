"""Index exact embedded original images, preserving bytes in temporary artifacts."""
import hashlib,json
from pathlib import Path
import fitz
BASE=Path(r'D:\artifacts\gwy-quality-audit-20261015');out=BASE/'tibet2016-pdf-images';out.mkdir(exist_ok=True)
doc=fitz.open(BASE/'tibet2016-zhenghua-original.pdf');rows=[]
for number,page in enumerate(doc,1):
    for item in page.get_images(full=True):
        xref=item[0];raw=doc.extract_image(xref);data=raw['image'];name=f'page-{number:02d}-xref-{xref}.{raw["ext"]}';p=out/name;p.write_bytes(data)
        rows.append({'page':number,'xref':xref,'width':raw['width'],'height':raw['height'],'rects':[[round(v,2) for v in rect] for rect in page.get_image_rects(xref)],'file':str(p),'sha256':hashlib.sha256(data).hexdigest()})
(out/'index.json').write_bytes((json.dumps(rows,ensure_ascii=False,indent=2)+'\n').encode())
for r in rows:
    if r['width']>150 or r['height']>130:print(json.dumps(r,ensure_ascii=False),flush=True)
