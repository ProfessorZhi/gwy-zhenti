#!/usr/bin/env python3
"""Verify source continuation; restore exact prior bytes for historical checks."""
from __future__ import annotations
import hashlib,json,shutil,tempfile
from pathlib import Path
from unittest.mock import patch
import round5_bulk as parser
from round4_delivery import is_missing
from r7_reference_audit import audit,assess
from source_supplement_20261013 import cleaned,norm,exam_body,formatted,gitsha
ROOT=Path(__file__).resolve().parents[1]
RECEIPT="SOURCED-CONTINUATION-20261013.jsonl"
FULL="SOURCED-CONTINUATION-FULL-20261013.json"
SUMMARY="SOURCED-CONTINUATION-20261013.json"
def sha(t):return hashlib.sha256(t.encode("utf-8")).hexdigest()
def sources():
 result={}
 for f in sorted((ROOT/"tools/data/sourced-continuation-20261013").glob("sources-*.json")):
  for x in json.loads(f.read_text(encoding="utf-8")):
   if gitsha(x["text"])!=x["blob"]:raise ValueError("Changed source blob")
   if x["path"] in result:raise ValueError("Duplicate original source")
   result[x["path"]]=x
 return result
def records(root):return [json.loads(s) for s in (Path(root)/"reports"/RECEIPT).read_text(encoding="utf-8").splitlines() if s.strip()]
def reverse(text,row):
 if sha(text)!=row["after_sha256"]:raise ValueError("Changed delivered text: "+row["path"])
 for op in sorted(row["operations"],key=lambda o:o["new_start"],reverse=True):
  a,b=op["new_start"],op["new_end"]
  if text[a:b]!=op["new"]:raise ValueError("Changed receipt operation")
  text=text[:a]+op["old"]+text[b:]
 if sha(text)!=row["before_sha256"]:raise ValueError("Failed exact restoration")
 return text
def historical_snapshot(root,destination):
 root=Path(root).resolve();destination=Path(destination).resolve()
 shutil.copytree(root/"reports",destination/"reports")
 for top in ("国考","省考"):shutil.copytree(root/top,destination/top)
 for r in records(root):
  p=(destination/r["path"]).resolve()
  if not p.is_relative_to(destination):raise ValueError("Unsafe source receipt")
  p.write_text(reverse(p.read_text(encoding="utf-8"),r),encoding="utf-8",newline="\n")
 from verify_repair_receipts import RECEIPTS
 for name in RECEIPTS:
  f=root/"reports"/name
  if not f.exists():continue
  for line in f.read_text(encoding="utf-8").splitlines():
   if not line.strip():continue
   rel=json.loads(line)["path"];src=(root/rel).resolve();dst=(destination/rel).resolve()
   if not src.is_relative_to(root) or not dst.is_relative_to(destination):raise ValueError("Unsafe historical path")
   if not dst.exists():dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 (destination/"reports"/RECEIPT).unlink()
def verify(root):
 root=Path(root).resolve();rows=records(root)
 full=json.loads((root/"reports"/FULL).read_text(encoding="utf-8"))
 summary=json.loads((root/"reports"/SUMMARY).read_text(encoding="utf-8"))
 source=sources();pending={(e["path"],e["number"]):e for e in full};seen=set();count=0;preserved=0
 if len(pending)!=len(full) or summary["new_AI_answers"]!=0:raise ValueError("Duplicate or newly authored answer")
 for r in rows:
  rel=r["path"];p=(root/rel).resolve()
  if rel in seen or not p.is_relative_to(root):raise ValueError("Invalid delivery path")
  seen.add(rel);text=p.read_text(encoding="utf-8");old=reverse(text,r)
  if sha(exam_body(old))!=r["exam_body_sha256"] or exam_body(old)!=exam_body(text):raise ValueError("Changed original exam body")
  before=parser.parse(old,rel);after=parser.parse(text,rel)
  if before["questions"]!=after["questions"]:raise ValueError("Changed original task")
  for n,a in before["answers"].items():
   if not is_missing(a):
    if after["answers"].get(n)!=a:raise ValueError("Existing answer overwritten")
    preserved+=1
  for n in r["added_numbers"]:
   e=pending.pop((rel,n));src=source[e["full_source_path"]]
   if src["blob"]!=e["source_blob"] or src["revision"]!=e["source_revision"] or sha(src["text"])!=e["source_sha256"]:raise ValueError("Changed source provenance")
   if sha(e["answer"])!=e["answer_sha256"] or norm(e["answer"]) not in norm(cleaned(src["text"])):raise ValueError("Untraceable reference text")
   if not is_missing(before["answers"].get(n,"")):raise ValueError("Previously answered task")
   if parser.qkey(before["questions"][n])!=parser.qkey(e["question"]):raise ValueError("Wrong source task")
   a=after["answers"].get(n,"")
   if formatted(e) not in a or e["original_author"] not in a or src["revision"] not in a:raise ValueError("Lost answer or attribution")
   if assess(after["questions"][n],a)["status"]!="已收录":raise ValueError("Incomplete reference body")
   count+=1
 if pending or count!=summary["source_answer_positions_added"] or len(rows)!=summary["papers_modified"]:raise ValueError("Delivery count mismatch")
 with patch("r7_reference_audit.ROOT",root):current,bad,_,counts=audit()
 actual=sum(v for k,v in counts.items() if k.endswith("/待补"))
 expected=summary.get("known_missing_answers_after",summary["expected_missing_answers_after"])
 if len(current)!=729 or len(bad)!=9 or actual!=expected:raise ValueError("Current actual coverage mismatch: "+str(actual))
 with tempfile.TemporaryDirectory(prefix="gwy-source-continuation-before-") as tmp:
  historical_snapshot(root,Path(tmp))
  with patch("r7_reference_audit.ROOT",Path(tmp)):prior,oldbad,_,oldcounts=audit()
 oldmissing=sum(v for k,v in oldcounts.items() if k.endswith("/待补"))
 if oldmissing!=451 or oldmissing-actual!=count or len(oldbad)!=9:raise ValueError("Historical coverage mismatch")
 return {"status":"passed","source_reference_positions":count,"papers_modified":len(rows),"preserved_existing_answers":preserved,"known_missing_answers_after":actual,"boundary":"Existing source text and exact exam preservation; original author statements retained."}
if __name__=="__main__":print(json.dumps(verify(ROOT),ensure_ascii=False))
