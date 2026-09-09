#!/usr/bin/env python3
"""Compare standalone query parsing to an independent byte-level Python oracle.

Reference operations implement WHATWG form parsing/serialization in bytes and
use Python's UTF-8 decoder. No Node/browser is needed. This checks strings and
mutations, not all Web IDL cases, game compatibility, or conformance certification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
from host_paths import default_host
from urllib.parse import unquote_to_bytes


def vectors(count, seed):
    result = ['x=%'+format(n, '02X') for n in range(min(count, 256))]
    rng = random.Random(seed)
    alphabet = ['a', 'b', '?', '&', '=', '+', '%', '0', 'F', 'f', ' ', '!', '~', '\x00',
                '\u00e9', '\u65e5', '\U0001f3ae', '\ud800', '\udfff', '\ufeff']
    while len(result) < count:
        result.append(''.join(rng.choice(alphabet) for _ in range(rng.randrange(1, 81))))
    return result


def reference(input):
    # JS USVString conversion, including paired and unpaired UTF-16 surrogates.
    scalar = input.encode('utf-16-le', 'surrogatepass').decode('utf-16-le', 'replace')
    raw = scalar.removeprefix('?').encode('utf-8')
    pairs = []
    for field in raw.split(b'&'):
        if not field: continue
        name, _, value = field.partition(b'=')
        pairs.append([unquote_to_bytes(p.replace(b'+', b' ')).decode('utf-8', 'replace')
                      for p in (name, value)])
    def encode(value):
        allowed = b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789*-._'
        return ''.join(chr(b) if b in allowed else '+' if b == 32 else f'%{b:02X}'
                       for b in value.encode('utf-8'))
    def serialize(values):
        return '&'.join(encode(k)+'='+encode(v) for k, v in values)
    original = serialize(pairs)
    pairs.append(['probe', 'x y'])
    changed = []; found = False
    for key, value in pairs:
        if key == 'probe':
            if found: continue
            value = '!~'; found = True
        changed.append([key, value])
    changed.sort(key=lambda row: row[0].encode('utf-16-be'))
    changed = [row for row in changed if row[0] != 'missing']
    return [original, serialize(changed), len(changed), [v for k,v in changed if k == 'a']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', type=Path, default=default_host())
    parser.add_argument('--cases', type=int, default=2048)
    parser.add_argument('--seed', type=int, default=3909)
    parser.add_argument('--report', type=Path, default=Path('reports/query-differential.json'))
    args = parser.parse_args()
    result = dict(schema=1, status='not_run', passed=False, total=0,
                  scope='Standalone V8 candidate vs independent Python byte-level reference; query strings/mutations, not game/conformance/performance validation')
    start = time.monotonic()
    try:
        if not 1 <= args.cases <= 20000: raise ValueError('--cases must be 1..20000')
        host = args.host.resolve(strict=True)
        operation = """function check(input) {
          const p = new URLSearchParams(input);
          const original = p.toString();
          p.append('probe', 'x y'); p.set('probe', '!~'); p.sort(); p.delete('missing');
          return [original, p.toString(), p.size, p.getAll('a')];
        }"""
        inputs = json.dumps(vectors(args.cases, args.seed), ensure_ascii=True)
        expected = [reference(value) for value in json.loads(inputs)]
        marker = 'QUERY_DIFFERENTIAL_OK '+str(args.cases)
        source = operation + '\nconst inputs='+inputs+';\nconst expected='+json.dumps(expected, ensure_ascii=True)+''';
          for (let i=0;i<inputs.length;i++) {
            const actual=check(inputs[i]);
            if(JSON.stringify(actual)!==JSON.stringify(expected[i]))
              throw Error('query differential mismatch at case '+i);
          }
        ''' + 'console.log('+json.dumps(marker)+');\n'
        with tempfile.TemporaryDirectory(prefix='zero-query-') as temp:
            script = Path(temp)/'query.js'; script.write_text(source, encoding='utf-8')
            run = subprocess.run([str(host), '--profile', 'core', '--timeout-ms', '10000', str(script)],
                                 capture_output=True, text=True, encoding='utf-8', timeout=20)
            native = json.loads(run.stdout)
        passed = run.returncode == 0 and native.get('status') == 'completed' and [x['text'] for x in native.get('logs', [])] == [marker]
        result.update(status='tested', passed=passed, total=args.cases, matched=args.cases if passed else None,
                      seed=args.seed, executable_sha256=hashlib.sha256(host.read_bytes()).hexdigest(),
                      inputs_sha256=hashlib.sha256(inputs.encode()).hexdigest(),
                      source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                      reference_version='Python '+sys.version.split()[0],
                      native_report=native)
        print(marker if passed else 'Query differential test failed')
        return 0 if passed else 1
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result['error']=str(exc);print(str(exc),file=sys.stderr);return 1
    finally:
        result['elapsed_seconds']=round(time.monotonic()-start,3)
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':raise SystemExit(main())
