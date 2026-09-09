#!/usr/bin/env python3
"""Audit this host's ELF linkage and observed own-child runtime libraries on Linux.

This is not a security, sandbox, resource-use, or performance assessment. The
runtime observation captures libraries on one independent fixture path only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',type=Path,default=ROOT/'build/standalone/zero')
    p.add_argument('--graphics',action='store_true')
    p.add_argument('--report',type=Path,default=ROOT/'reports/binary-audit.json')
    args=p.parse_args();child=None
    try:
        if sys.platform!='linux':raise ValueError('This audit uses Linux ELF and /proc')
        host=args.host.resolve(strict=True)
        engine=json.loads(subprocess.check_output([str(host),'--engine-info'],text=True,timeout=5))
        dynamic=subprocess.check_output(['readelf','-d',str(host)],text=True,timeout=5)
        needed=re.findall(r'\(NEEDED\).*?\[(.*?)\]',dynamic)
        images=set();source=('const c=new OffscreenCanvas(8,8);c.getContext("webgl");\n' if args.graphics else '')+'setTimeout(()=>{},2000);\n'
        with tempfile.TemporaryDirectory(prefix='zero-library-audit-') as tmp:
            path=Path(tmp)/'probe.js';path.write_text(source)
            child=subprocess.Popen([str(host),'--profile','graphics' if args.graphics else 'core','--timeout-ms','8000',str(path)],
                                   text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            deadline=time.monotonic()+10
            while child.poll() is None and time.monotonic()<deadline:
                try:
                    for line in Path(f'/proc/{child.pid}/maps').read_text().splitlines():
                        parts=line.split(None,5)
                        if len(parts)==6 and 'x' in parts[1] and parts[5].startswith('/') and '.so' in parts[5]:images.add(parts[5])
                except FileNotFoundError:pass
                time.sleep(.04)
            out,err=child.communicate(timeout=2)
            report=json.loads(out)
            if child.returncode or report['status']!='completed':raise ValueError('Audit fixture failed: '+out[:2048]+err[:1024])
        suspect=[x for x in images if re.search(r'(^|/)(?:libnode|libcef|libchromium|chromium|chrome|electron)(?:[.\-/]|$)',x)]
        graphics_observed=any(Path(x).name.startswith('libEGL') for x in images)
        passed=not suspect and bool(images) and (graphics_observed if args.graphics else not graphics_observed)
        link=host.parent/'CMakeFiles/zero.dir/link.txt'
        result=dict(schema=2,binary=str(host.relative_to(ROOT)) if host.is_relative_to(ROOT) else str(host),
                    platform='linux-x86_64',bytes=host.stat().st_size,sha256=hashlib.sha256(host.read_bytes()).hexdigest(),
                    engine_info=engine,direct_elf_dependencies=needed,observed_runtime_libraries=sorted(images),
                    unexpected_browser_or_node_images=suspect,graphics_requested=args.graphics,graphics_libraries_observed=graphics_observed,
                    graphics=report.get('graphics'),link_command=link.read_text().strip() if link.exists() else None,passed=passed,
                    notes=['V8 is statically linked; graphics loads native EGL/driver libraries dynamically only when requested.',
                           'The graphics-enabled image list includes the complete observed native driver path, not just ldd output.',
                           'One fixture path only; no security, minimality, full-game compatibility or performance certification.'])
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,indent=2)+'\n')
        print(f"{'PASS' if passed else 'FAIL'}: {len(images)} observed runtime libraries; browser/Node images: {len(suspect)}")
        return 0 if passed else 1
    except (OSError,ValueError,subprocess.SubprocessError) as e:
        print('Audit failed: '+str(e),file=sys.stderr);return 1
    finally:
        if child and child.poll() is None:child.kill();child.communicate(timeout=3)

if __name__=='__main__':raise SystemExit(main())
