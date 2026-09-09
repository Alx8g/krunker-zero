#!/usr/bin/env python3
"""Inventory script tags in locally saved original HTML; never fetch or execute.
The result is markup evidence, NOT an execution trace or complete dependency graph.
"""
from __future__ import annotations
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin

class Scripts(HTMLParser):
    def __init__(self, origin: str):
        super().__init__(convert_charrefs=False)
        self.base = origin
        self.got_base = False
        self.entries = []
        self.current = None
        self.body = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'base' and not self.got_base and attrs.get('href'):
            self.base = urljoin(self.base, attrs['href'])
            self.got_base = True
        if tag == 'script':
            self.current = dict(index=len(self.entries),line=self.getpos()[0],
                src=urljoin(self.base,attrs['src']) if attrs.get('src') else None,
                type=attrs.get('type','classic'),async_attribute='async' in attrs,
                defer_attribute='defer' in attrs,nomodule='nomodule' in attrs,
                integrity=attrs.get('integrity'))
            self.body = []
    def handle_data(self, data):
        if self.current is not None: self.body.append(data)
    def handle_endtag(self, tag):
        if tag == 'script' and self.current is not None:
            raw=''.join(self.body).encode('utf-8')
            self.current['inline_utf8_bytes']=len(raw)
            self.current['inline_sha256']=hashlib.sha256(raw).hexdigest() if raw else None
            self.entries.append(self.current)
            self.current=None
            self.body=[]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html',type=Path)
    parser.add_argument('--base-url',required=True,help='original retrieval URL, for resolving relative src')
    args=parser.parse_args()
    if any(x.casefold()=='wok' for x in args.html.resolve().parts): parser.error('excluded implementation path')
    if args.html.stat().st_size>16*1024*1024: parser.error('HTML exceeds 16 MiB')
    raw=args.html.read_bytes()
    inventory=Scripts(args.base_url)
    inventory.feed(raw.decode('utf-8'))
    inventory.close()
    print(json.dumps(dict(schema=1,html_sha256=hashlib.sha256(raw).hexdigest(),
      scripts=inventory.entries,unfinished_script=inventory.current is not None,
      warning='Tag order is not runtime order for async/defer/module scripts. Dynamic loads and inline behavior are not discovered.'),indent=2))
if __name__=='__main__': main()
