#!/usr/bin/env python3
"""Embed our own optional JS profile, never a proprietary game bundle."""
from pathlib import Path
import sys
source, output = map(Path, sys.argv[1:3])
symbol = sys.argv[3] if len(sys.argv) > 3 else 'kCorePrelude'
if not symbol.isidentifier():
    raise ValueError('invalid C++ symbol')
data = source.read_bytes()
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text('#pragma once\nstatic const unsigned char ' + symbol + '[] = {\n' +
                  ','.join(str(b) for b in data) + ',0\n};\n', encoding='utf-8')
