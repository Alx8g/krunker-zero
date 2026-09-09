#!/usr/bin/env python3
"""Embed our own optional JS profile, never a proprietary game bundle."""
from pathlib import Path
import sys
source, output = map(Path, sys.argv[1:])
data = source.read_bytes()
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text('#pragma once\nstatic const unsigned char kCorePrelude[] = {\n' +
                  ','.join(str(b) for b in data) + ',0\n};\n', encoding='utf-8')
