"""Fix administrative-place names in generated paper titles only."""
import hashlib,json,os,re,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NAMES={'北京':'北京市','上海':'上海市','天津':'天津市','重庆':'重庆市','深圳':'深圳市','广州':'广州市','内蒙古':'内蒙古自治区','广西':'广西壮族自治区','宁夏':'宁夏回族自治区','新疆':'新疆维吾尔自治区','西藏':'西藏自治区'}
PATTERN=re.compile(r'(?m)^# (\d{4}) ('+'|'.join(NAMES)+r')省公务员')
def sha(text):return hashlib.sha256(text.encode()).hexdigest()
def main():
    changes=[]
    for top in ('国考','省考'):
        for p in sorted((ROOT/top).rglob('*.md')):
            old=p.read_text(encoding='utf-8');new=PATTERN.sub(lambda m:'# '+m[1]+' '+NAMES[m[2]]+'公务员',old,count=1)
            if old==new:continue
            tmp=p.with_name(p.name+'.title-'+uuid.uuid4().hex+'.tmp')
            try:
                tmp.write_bytes(new.encode())
                if p.read_text(encoding='utf-8')!=old:raise ValueError('Concurrent title edit: '+str(p))
                os.replace(tmp,p)
            finally:
                if tmp.exists():tmp.unlink()
            changes.append({'path':p.relative_to(ROOT).as_posix(),'before_sha256':sha(old),'after_sha256':sha(new),'before_title':next(s for s in old.splitlines() if s.startswith('# ')),'after_title':next(s for s in new.splitlines() if s.startswith('# '))})
    (ROOT/'reports/FULL-REPAIR-TITLES-20261015.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'titles_corrected':len(changes)}))
if __name__=='__main__':main()
