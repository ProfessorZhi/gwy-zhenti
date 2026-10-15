"""Render the untouched original source pages for visual inspection."""
from pathlib import Path
import fitz
BASE=Path(r'D:\artifacts\gwy-quality-audit-20261015')
doc=fitz.open(BASE/'tibet2016-zhenghua-original.pdf')
for number in (13,14,15,16,17,24,25,26,27):
    doc[number-1].get_pixmap(matrix=fitz.Matrix(1.7,1.7)).save(BASE/f'tibet2016-page{number}.png')
    print(number,flush=True)
