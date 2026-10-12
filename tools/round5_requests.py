#!/usr/bin/env python3
import hashlib,json
import round5_bulk as b

def fingerprint(t):
 t=b.qkey(t);grams={t[i:i+3] for i in range(max(0,len(t)-2))};v=[0]*64
 for x in grams:
  h=int.from_bytes(hashlib.sha256(x.encode()).digest()[:8],'big')
  for j in range(64):v[j]+=1 if h>>j&1 else -1
 return format(sum(1<<j for j,x in enumerate(v) if x>=0),'016x')

def main():
 papers,bad,plans,unresolved,c=b.scan();fixed={(t['path'],a['number']) for t,adds in plans for a in adds};out={}
 for t in papers:
  for n in t['missing']:
   if (t['path'],n) in fixed:continue
   area,year=t['identity'];out.setdefault(year,{}).setdefault(area,[]).append(fingerprint(t['questions'][n]))
 for year,x in sorted(out.items()):print('REQUESTS_'+year,json.dumps({a:sorted(set(v)) for a,v in x.items()},ensure_ascii=False,separators=(',',':')),flush=True)
if __name__=='__main__':main()
