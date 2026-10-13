import json
import round5_bulk as b
from r7_reference_audit import audit
papers,bad,plans,left,counts=b.scan()
for t,adds in plans:
 for a in adds:
  if "AI辅助" in a["answer"] or "AI原创" in a["answer"]:continue
  print("INTERNAL_SOURCE_CANDIDATE="+json.dumps({"path":t["path"],"question":t["questions"][a["number"]],**a},ensure_ascii=False),flush=True)
rows,failed,_,counts=audit()
for p in rows:
 for q in p["tasks"]:
  if q["status"]=="待补":print("CURRENT_GAP="+json.dumps({"path":p["path"],**q},ensure_ascii=False),flush=True)
print("SEARCH_AUDIT="+json.dumps({"parsed":len(rows),"unparsed":failed,"classification":counts},ensure_ascii=False),flush=True)
