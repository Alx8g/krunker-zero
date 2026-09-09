#!/usr/bin/env python3
"""Build/test the native scheduler and V8 bindings without downloading packages.
Node supplies V8 ONLY to the development adapter; it is not the shipped host.
Each guest runs once in its own child process and fresh V8 Context.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'

def command(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=True, cwd=ROOT, text=True, **kwargs)

def build(node: str, include: Path) -> Path:
    BUILD.mkdir(exist_ok=True)
    command([sys.executable, 'tools/embed.py', 'runtime/core.js', 'build/generated/core_prelude.h'])
    command(['cmake', '-S', '.', '-B', 'build/native', '-DCMAKE_BUILD_TYPE=Release'])
    command(['cmake', '--build', 'build/native', '-j2'])
    command(['ctest', '--test-dir', 'build/native', '--output-on-failure'])
    command([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_tools.py', '-v'])
    cc = os.environ.get('CXX', 'c++')
    # All ABI-affecting defines must match the engine supplying the symbols.
    config = json.loads(command([node, '-p', 'JSON.stringify(process.config.variables)'],
                                capture_output=True).stdout)
    flags = []
    for key, define in [('v8_enable_pointer_compression', 'V8_COMPRESS_POINTERS'),
                        ('v8_enable_sandbox', 'V8_ENABLE_SANDBOX'),
                        ('v8_enable_31bit_smis_on_64bit_arch', 'V8_31BIT_SMIS_ON_64BIT_ARCH')]:
        if config.get(key) in (1, True, '1'): flags.append('-D' + define)
    common = [cc, '-std=c++20', '-fno-rtti', '-O2', '-Wall', '-Wextra', '-pthread',
              '-I', 'native', '-I', 'build/generated', '-isystem', str(include), *flags]
    command([*common, '-c', 'native/main.cc', '-o', 'build/main.o'])
    addon = BUILD / 'zero_smoke.node'
    command([*common, '-fPIC', '-shared', 'native/host.cc', 'native/task_queue.cc',
             'native/node_smoke.cc', '-o', str(addon)])
    return addon

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', default=shutil.which('node'))
    parser.add_argument('--node-include', type=Path)
    parser.add_argument('--no-build', action='store_true')
    args = parser.parse_args()
    if not args.node:
        parser.error('Node is required for the development-only V8 smoke adapter')
    if platform.system() != 'Linux':
        parser.error('The development adapter is currently tested only on Linux')
    node = str(Path(args.node).resolve())
    include = args.node_include or Path(node).parent.parent / 'include' / 'node'
    if not (include / 'node.h').is_file():
        parser.error('Node headers missing; supply --node-include')
    addon = BUILD / 'zero_smoke.node' if args.no_build else build(node, include)
    results = []
    started = time.monotonic()

    def case(name: str, source: str, *, expected='completed', logs=None,
             profile='core', virtual_time=True, check=None, scripts=None, **options):
        cfg = dict(profile=profile, virtual_time=virtual_time,
                   scripts=scripts or [{'name': name + '.js', 'source': source}], **options)
        run = subprocess.run([node, 'tools/smoke_driver.cjs', str(addon)], cwd=ROOT,
                             input=json.dumps(cfg), text=True, capture_output=True, timeout=10)
        try:
            report = json.loads(run.stdout)
        except (ValueError, TypeError) as error:
            results.append(dict(name=name, passed=False, errors=[f'No valid report: {error}; exit={run.returncode}; stderr={run.stderr}']))
            print('FAIL: ' + name + ' (no valid JSON report)', flush=True)
            return
        errors = []
        if report['status'] != expected:
            errors.append(f"status {report['status']!r} != {expected!r}: {report['message']}")
        if run.returncode != report['exit_code']:
            errors.append(f'process return {run.returncode} != report {report["exit_code"]}')
        actual = [log['text'] for log in report['logs']]
        if logs is not None and logs != actual: errors.append(f'logs {actual!r} != {logs!r}')
        if check is not None and not check(report): errors.append('additional invariant failed')
        print(('FAIL' if errors else 'PASS') + ': ' + name, flush=True)
        if errors: print('\n'.join(errors))
        results.append(dict(name=name, passed=not errors, errors=errors, report=report))

    case('bare_ecmascript', 'if ([1,2,3].map(x=>x*2).join() !== "2,4,6") throw Error("bad JS");', profile='bare')
    case('bare_globals_absent', '''
      for (const key of ['window','document','navigator','console','setTimeout','fetch','WebSocket',
                         'process','require','Buffer','__zeroNative'])
        if (key in globalThis) throw Error('unexpected global: '+key);
    ''', profile='bare')
    case('missing_document', 'document.createElement("canvas");', profile='bare',
         expected='missing_global', check=lambda r: r['missing_global']=='document' and r['line']==1)
    case('missing_window', 'window.x;', profile='bare', expected='missing_global',
         check=lambda r: r['missing_global']=='window')
    case('feature_detection_preserved', 'console.log(typeof document, "document" in globalThis, typeof WebGLRenderingContext);',
         logs=['undefined false undefined'])
    case('core_has_no_host_escape', '''
      console.log(typeof process, typeof require, typeof Buffer, typeof __zeroNative,
                  typeof fetch, typeof WebSocket, typeof WebAssembly);
      console.log(Function('return typeof process')());
    ''', check=lambda r: r['logs'][0]['text'].startswith('undefined undefined undefined undefined undefined undefined')
                           and r['logs'][1]['text']=='undefined')
    case('window_identity', 'console.log(window===globalThis, self===globalThis);', logs=['true true'])
    case('nested_property_not_invented', 'window.document.createElement("canvas");', expected='script_exception',
         check=lambda r: not r['missing_global'])
    case('caught_missing_not_claimed', 'try { document.x } catch (e) {} console.log("caught");', logs=['caught'])
    case('syntax_error', 'const = ;', expected='script_exception')
    case('synchronous_throw', 'throw new Error("sentinel");', expected='script_exception',
         check=lambda r:'sentinel' in r['message'])
    case('ordered_scripts', '', scripts=[{'name':'first.js','source':'var state=10;'},
         {'name':'second.js','source':'console.log(state+2);'}], logs=['12'])
    case('microtask_between_scripts', '', scripts=[{'name':'first.js','source':'var state=0; Promise.resolve().then(()=>state=7);'},
         {'name':'second.js','source':'console.log(state);'}], logs=['7'])
    case('promise_before_timer', 'setTimeout(()=>console.log("timer"),0); Promise.resolve().then(()=>console.log("promise")); console.log("sync");',
         logs=['sync','promise','timer'])
    case('microtask_between_timers', 'setTimeout(()=>{console.log("one");Promise.resolve().then(()=>console.log("micro"));},0);setTimeout(()=>console.log("two"),0);',
         logs=['one','micro','two'])
    case('timer_order', 'setTimeout(()=>console.log("ten"),10);setTimeout(()=>console.log("zero"),0);setTimeout(()=>console.log("five"),5);',
         logs=['zero','five','ten'])
    case('timer_args_and_this', 'setTimeout(function(a,b){console.log(a,b,this===globalThis)},2,"x",3);', logs=['x 3 true'])
    case('clear_timeout', 'const id=setTimeout(()=>{throw Error("cancelled")},0);clearTimeout(id);console.log("ok");', logs=['ok'])
    case('cancel_unknown_harmless', 'clearTimeout(900);clearInterval(-1);cancelAnimationFrame(NaN);console.log("ok");', logs=['ok'])
    case('same_batch_cancellation', 'let b;setTimeout(()=>{console.log("a");clearTimeout(b)},0);b=setTimeout(()=>console.log("b"),0);', logs=['a'])
    case('interval_self_cancellation', 'let n=0; const id=setInterval(()=>{console.log(++n,performance.now());if(n===3)clearInterval(id)},5);',
         logs=['1 5','2 10','3 15'])
    case('cross_cancel_timer_interval', 'let id=setInterval(()=>{console.log("once");clearTimeout(id)},1);', logs=['once'])
    case('nested_timer_fifo', 'setTimeout(()=>{console.log("a");setTimeout(()=>console.log("c"),0)},0);setTimeout(()=>console.log("b"),0);',
         logs=['a','b','c'])
    case('raf_shared_timestamp', 'let t;requestAnimationFrame(x=>{t=x;console.log("first")});requestAnimationFrame(x=>console.log(x===t));',
         logs=['first','true'], check=lambda r:r['callbacks']==2 and r['clock_ms']>16)
    case('raf_nested_next_frame', 'requestAnimationFrame(a=>requestAnimationFrame(b=>console.log(b>a)));', logs=['true'])
    case('raf_cancel_same_frame', 'let b;requestAnimationFrame(()=>{console.log("a");cancelAnimationFrame(b)});b=requestAnimationFrame(()=>console.log("b"));', logs=['a'])
    case('raf_one_shot', 'requestAnimationFrame(()=>console.log("once"));', logs=['once'],check=lambda r:r['callbacks']==1)
    case('timer_throw_visible', 'setTimeout(()=>{throw Error("timer failed")},0);', expected='script_exception',
         check=lambda r:r['phase']=='timer')
    case('raf_throw_visible', 'requestAnimationFrame(()=>{throw Error("frame failed")});', expected='script_exception',
         check=lambda r:r['phase']=='animation-frame')
    case('rejected_promise_visible', 'Promise.reject(new Error("rejected"));', expected='unhandled_rejection')
    case('handled_promise_success', 'Promise.reject(Error("handled")).catch(()=>console.log("caught"));', logs=['caught'])
    case('microtask_adds_rejection_handler', 'const p=Promise.reject("x");Promise.resolve().then(()=>p.catch(()=>console.log("caught")));', logs=['caught'])
    case('promise_throw_visible', 'Promise.resolve().then(()=>{throw Error("microtask failed")});', expected='unhandled_rejection')
    case('reject_string_timer', 'setTimeout("console.log(1)",0);', expected='script_exception')
    case('reject_nonfunction_raf', 'requestAnimationFrame(null);', expected='script_exception')
    case('pending_cap', 'setTimeout(()=>{},0);setTimeout(()=>{},0);', max_pending=1, expected='script_exception')
    case('recurring_work_budget', 'setInterval(()=>{},1);', max_tasks=3, expected='task_budget_exhausted',
         check=lambda r:r['callbacks']==3 and r['pending_tasks']==1)
    case('loop_timeout', 'while(true){}', timeout_ms=40, expected='execution_timeout', virtual_time=False)
    case('promise_loop_timeout', 'function spin(){Promise.resolve().then(spin)}spin();', timeout_ms=40,
         expected='execution_timeout', virtual_time=False)
    case('idle_wait_timeout', 'setTimeout(()=>console.log("too late"),10000)', timeout_ms=40,
         expected='execution_timeout', virtual_time=False,logs=[])
    case('real_clock', 'const t=performance.now();setTimeout(()=>console.log(performance.now()>=t+2),3);',
         virtual_time=False,logs=['true'])
    case('unknown_profile', '1', profile='pretend-browser', expected='configuration_error')
    case('invalid_hz', '1', frame_hz=0, expected='configuration_error')
    case('invalid_timeout', '1', timeout_ms=0, expected='configuration_error')
    case('json_escaping', 'console.log("line\\n\\t\\\"quote\\\"\\\\end");', logs=['line\n\t"quote"\\end'])
    case('unicode_report', 'console.log("héllo 日本語 🎮");',logs=['héllo 日本語 🎮'])
    case('bounded_logs', 'for(let i=0;i<520;i++)console.log(i)',check=lambda r:len(r['logs'])==512 and r['logs_dropped']==8)

    report = dict(schema=1, test_environment='development-only Node/V8 native adapter; NOT standalone runtime',
                  platform=platform.platform(), node=command([node,'--version'],capture_output=True).stdout.strip(),
                  native_scheduler='12 checks; separate native executable',
                  native_cli='compiled to object; standalone link not exercised by this suite',
                  game_bundle_executed=False, elapsed_seconds=round(time.monotonic()-started,3),
                  passed=sum(r['passed'] for r in results), total=len(results), tests=results)
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/test-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"\n{report['passed']}/{report['total']} V8 integration cases passed.")
    return 0 if report['passed']==report['total'] else 1

if __name__=='__main__':
    raise SystemExit(main())
