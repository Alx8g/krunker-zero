#!/usr/bin/env python3
"""Hash local script inputs and run them unchanged, in explicit argument order.
No downloading, browser automation, authentication handling, or game patching.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from host_paths import default_host, backend_args

ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE = 16 * 1024 * 1024

def read_input(path: Path) -> tuple[bytes, dict]:
    # A convenience guard, not a substitute for the clean-room process.
    # Reject the excluded implementation's directory name before opening bytes.
    resolved = path.resolve(strict=True)
    if any(part.casefold() == 'wok' for part in resolved.parts):
        raise ValueError('excluded implementation path; use original game inputs only')
    if not resolved.is_file() or resolved.stat().st_size > MAX_SOURCE:
        raise ValueError(f'not a regular script of at most 16 MiB: {path}')
    raw = resolved.read_bytes()
    if len(raw) > MAX_SOURCE: raise ValueError('source grew beyond size limit')
    raw.decode('utf-8')  # Do not silently replace malformed input or run HTML.
    if raw.decode('utf-8-sig').lstrip().lower().startswith(('<!doctype html', '<html')):
        raise ValueError('HTML is not a JS bundle; inspect the bootstrap separately')
    return raw, dict(name=path.name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scripts', nargs='+', type=Path)
    parser.add_argument('--profile', choices=['bare','core','graphics'], default='bare')
    parser.add_argument('--virtual-time', action='store_true')
    parser.add_argument('--timeout-ms', type=int, default=2000)
    parser.add_argument('--max-tasks', type=int, default=10000)
    parser.add_argument('--host', type=Path, default=default_host())
    parser.add_argument('--dev-node-smoke', action='store_true',
                        help='explicitly use the development harness, NOT the standalone host')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/probe-latest.json')
    parser.add_argument('--angle-backend',choices=['d3d11','warp'])
    args = parser.parse_args()
    if not 1 <= args.timeout_ms <= 60000 or not 1 <= args.max_tasks <= 1000000:
        parser.error('invalid timeout/task budget')
    try:
        inputs = [read_input(p) for p in args.scripts]
        cfg = dict(profile=args.profile, virtual_time=args.virtual_time,
                   timeout_ms=args.timeout_ms,max_tasks=args.max_tasks,
                   scripts=[dict(name=m['name'],source=b.decode('utf-8')) for b,m in inputs])
        if args.dev_node_smoke and args.angle_backend:
            raise ValueError('ANGLE selection belongs to standalone Windows graphics only')
        if args.dev_node_smoke:
            node = shutil.which('node')
            addon = ROOT/'build/zero_smoke.node'
            if not node or not addon.exists():
                raise ValueError('development adapter missing; run python3 tools/test.py')
            cmd = [node, str(ROOT/'tools/smoke_driver.cjs'), str(addon)]
            completed = subprocess.run(cmd,input=json.dumps(cfg),capture_output=True,text=True, encoding='utf-8',
                                       timeout=args.timeout_ms/1000+5)
            environment = 'development-only Node/V8 adapter, NOT standalone'
        else:
            host = args.host.resolve(strict=True)
            # Run immutable copies of the exact bytes that were hashed. This
            # avoids recording one version and executing a subsequently edited one.
            private = ROOT/'input'
            private.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='probe-',dir=private) as folder:
                copies = []
                for index,(raw,metadata) in enumerate(inputs):
                    copy = Path(folder)/f'{index:03d}-{metadata["name"]}'
                    copy.write_bytes(raw)
                    copies.append(str(copy))
                cmd = [str(host),*backend_args(args.angle_backend),'--profile',args.profile,'--timeout-ms',str(args.timeout_ms),
                       '--max-tasks',str(args.max_tasks)]
                if args.virtual_time: cmd.append('--virtual-time')
                completed = subprocess.run([*cmd,'--',*copies],capture_output=True,text=True, encoding='utf-8',
                                           timeout=args.timeout_ms/1000+5)
            environment = 'standalone V8 host'
        report = json.loads(completed.stdout)
        if completed.returncode != report['exit_code']:
            raise ValueError('process exit disagrees with structured report')
        report['execution_environment'] = environment
        report['inputs'] = [m for _,m in inputs]
        report['coverage_note'] = ('This reports one executed path, not all API usage. '
                                  'Completed does not imply a playable or compatible game.')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print(f"{report['status']}: {report['message'] or 'input execution finished'}")
        print(f'Report: {args.output}')
        return report['exit_code']
    except (OSError,ValueError,subprocess.TimeoutExpired) as error:
        print(f'probe failed: {error}',file=sys.stderr)
        return 70

if __name__ == '__main__':
    raise SystemExit(main())
