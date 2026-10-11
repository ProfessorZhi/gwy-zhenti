#!/usr/bin/env python3
"""Read-only full pixel decoding of every image referenced by delivered papers."""
import json
from pathlib import Path
import sys
from PIL import Image, ImageSequence
from cloud_quality import image_refs, papers, resolve_image

root=Path(__file__).resolve().parents[1]
references=set()
for paper in papers(root):
    rel=paper.relative_to(root).as_posix()
    for ref in image_refs(paper.read_text(encoding='utf-8-sig')):
        target=resolve_image(rel,ref)
        if target is None or target.startswith('!'):
            raise RuntimeError('Unverifiable image reference: '+rel+' -> '+ref)
        references.add(target)
errors=[]
frames=0
for rel in sorted(references):
    try:
        target=(root/rel).resolve()
        target.relative_to(root)
        with Image.open(target) as image:
            for frame in ImageSequence.Iterator(image):
                frame.load()
                if frame.width<=0 or frame.height<=0:
                    raise ValueError('Invalid dimensions')
                frames+=1
    except Exception as exc:
        errors.append({'path':rel,'error':type(exc).__name__+': '+str(exc)[:160]})
print(json.dumps({'unique_images':len(references),'decoded_frames':frames,'failed_images':len(errors),'errors':errors},ensure_ascii=False,indent=2))
sys.exit(bool(errors))
