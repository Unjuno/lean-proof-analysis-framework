#!/usr/bin/env python3
"""Download ONLY the 10 pinned public Lean text files for a reproducible pilot.

The source is not included or licensed for redistribution in this repository.
This fetcher never executes downloaded files or installs dependencies.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote

PIN="aa01316131472849f8e3b5b3e49f04d0a06c983f"
REPO="leanprover-community/riemann-hypothesis"

def blob(data:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=Path('work/rh-pilot'))
    p.add_argument('--manifest',type=Path,default=Path(__file__).with_name('expected_blobs.json'))
    a=p.parse_args()
    manifest=json.loads(a.manifest.read_text(encoding='utf-8'))
    for rel,expected in sorted(manifest.items()):
        if not rel.startswith('src/') or not rel.endswith('.lean') or '..' in Path(rel).parts:raise ValueError(f'Unsafe path: {rel}')
        target=a.out/rel
        if target.exists() and blob(target.read_bytes())==expected:
            print('verified cache',rel)
            continue
        u=f'https://raw.githubusercontent.com/{REPO}/{PIN}/{quote(rel)}'
        req=Request(u,headers={'User-Agent':'Lean-Atlas-Read-Only/0.1','Accept':'text/plain'})
        with urlopen(req,timeout=30) as response:
            data=response.read()
        actual=blob(data)
        if actual!=expected:raise ValueError(f'Hash mismatch: {rel}, {actual} != {expected}')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
        print('verified downloaded',rel)
    print(f'All {len(manifest)} files verified: {a.out}')

if __name__=='__main__':main()
