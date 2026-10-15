"""Individually authored, material-grounded study answers; never scored-paper claims."""
from pathlib import Path
import json,re,hashlib
from r7_reference_audit import word_range
import round5_bulk
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tools/data/full-repair-essay-a-20261015.json'
ROWS=json.loads(OUT.read_text(encoding='utf8')) if OUT.exists() else []
def add(path,n,answer,sources=None):
    text=(ROOT/path).read_text(encoding='utf8')
    gaps=json.loads((ROOT/'reports/SHENLUN-SOURCE-SEARCH-REMAINING-20261013.json').read_text(encoding='utf8'))['gaps']
    row=next((x for x in gaps if x['path']==path and x['number']==n),{})
    q=row.get('question','') or round5_bulk.parse(text,path)['questions'][n]
    r={'path':path,'number':n,'question':q,'answer':answer.strip(),'attribution_kind':'ai_original','author':'AI辅助编写（本次修复）','sources':sources or [],'writing_basis':'本卷给定材料与作答要求；非官方答案、未经实考评分','target_word_range':list(word_range(q)),'paper_sha256_before':hashlib.sha256(text.encode()).hexdigest(),'answer_characters':len(re.sub(r'\s','',answer.strip()))}
    ROWS[:]=[x for x in ROWS if (x['path'],x['number'])!=(path,n)]
    ROWS.append(r)
def save():
    OUT.write_text(json.dumps(ROWS,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('SAVED',len(ROWS))
