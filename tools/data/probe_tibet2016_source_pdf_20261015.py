"""Read-only original PDF probe; extracted text is an intermediate artifact."""
from pathlib import Path
import hashlib,importlib.util
BASE=Path(r'D:\artifacts\gwy-quality-audit-20261015')
p=BASE/'tibet2016-zhenghua-original.pdf'
print(p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest(),p.read_bytes()[:10],flush=True)
print({m:bool(importlib.util.find_spec(m)) for m in ['fitz','pypdf','pdfplumber']},flush=True)
import fitz
x=fitz.open(p);print('PAGES',len(x),flush=True)
for i,page in enumerate(x):
    t=page.get_text();print(i+1,len(t),t[:90].replace('\n',' '),flush=True)
(BASE/'tibet2016-zhenghua-original.txt').write_bytes('\n\n'.join('--- PAGE '+str(i+1)+' ---\n'+page.get_text() for i,page in enumerate(x)).encode())
x[0].get_pixmap(matrix=fitz.Matrix(1.4,1.4)).save(BASE/'tibet2016-page1.png')
