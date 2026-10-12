#!/usr/bin/env python3
"""Make read-only source packets line-addressable without changing any source character.
Only generated reading copies are touched, never an original exam paper.
"""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1]
def normalized(text):return text.replace('\r','').replace('\n','')
def main():
    changed=0
    for file in sorted((ROOT/'reports/r9-context').glob('packet-*.md')):
        old=file.read_text(encoding='utf-8');lines=[]
        for line in old.splitlines():
            if len(line)<=650:lines.append(line);continue
            while len(line)>650:
                # Prefer sentence boundaries, but never remove punctuation or words.
                positions=[line.rfind(mark,250,650) for mark in ('。','；','！','？')]
                cut=max(positions)+1
                if cut<250:cut=650
                lines.append(line[:cut]);line=line[cut:]
            if line:lines.append(line)
        new='\n'.join(lines)+'\n'
        if normalized(old)!=normalized(new):raise ValueError('Text altered while reflowing '+str(file))
        if new!=old:
            file.write_text(new,encoding='utf-8',newline='\n');changed+=1
    print('R9_READING_PACKET_REFLOW',changed,'files; all non-newline characters exactly preserved')
if __name__=='__main__':main()
