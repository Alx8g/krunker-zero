#!/usr/bin/env python3
"""Test the native host with --host, or build/test the separate Node development adapter.
Standalone mode uses no Node executable or Node headers.
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
import tempfile
import hashlib

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'

def command(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=True, cwd=ROOT, text=True, encoding='utf-8', **kwargs)

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
    parser.add_argument('--host', type=Path, help='Test a built standalone executable; Node is not used')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--node', default=shutil.which('node'))
    parser.add_argument('--node-include', type=Path)
    parser.add_argument('--no-build', action='store_true')
    args = parser.parse_args()
    host = args.host.resolve(strict=True) if args.host else None
    node = None
    addon = None
    if host:
        command([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v'])
    else:
        if not args.node:
            parser.error('Supply --host for standalone tests, or Node for the development adapter')
        if platform.system() != 'Linux':
            parser.error('The development adapter is currently tested only on Linux')
        node = str(Path(args.node).resolve())
        include = args.node_include or Path(node).parent.parent / 'include' / 'node'
        if not (include / 'node.h').is_file():
            parser.error('Node headers missing; supply --node-include')
        addon = BUILD / 'zero_smoke.node' if args.no_build else build(node, include)

    def execute(cfg):
        if not host:
            return subprocess.run([node, 'tools/smoke_driver.cjs', str(addon)], cwd=ROOT,
                                  input=json.dumps(cfg), text=True, encoding='utf-8', capture_output=True, timeout=10)
        # One fresh native process per case, including V8 startup and teardown.
        with tempfile.TemporaryDirectory(prefix='zero-test-') as tmp:
            argv = [str(host), '--profile', cfg['profile']]
            if cfg['virtual_time']:
                argv.append('--virtual-time')
            for key in ('timeout_ms', 'max_tasks', 'max_pending', 'frame_hz'):
                if key in cfg:
                    argv.extend(['--' + key.replace('_', '-'), str(cfg[key])])
            argv.append('--')
            for index, script in enumerate(cfg['scripts']):
                path = Path(tmp) / f'{index:03d}-{Path(script["name"]).name}'
                path.write_bytes(script['source'].encode('utf-8'))
                argv.append(str(path))
            return subprocess.run(argv, text=True, encoding='utf-8', capture_output=True, timeout=10)
    results = []
    started = time.monotonic()

    def case(name: str, source: str, *, expected='completed', logs=None,
             profile='core', virtual_time=True, check=None, scripts=None, **options):
        cfg = dict(profile=profile, virtual_time=virtual_time,
                   scripts=scripts or [{'name': name + '.js', 'source': source}], **options)
        try:
            run = execute(cfg)
        except subprocess.TimeoutExpired:
            results.append(dict(name=name, passed=False, errors=['external process deadline exceeded']))
            print('FAIL: ' + name + ' (process hung)', flush=True)
            return
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
                         'process','require','Buffer','__zeroNative','zeroWindow'])
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

    case('query_parse_duplicates', "const p=new URLSearchParams('?a=1&a=2&space=a+b&empty&x=a=b');console.log(p.getAll('a').join(','),p.get('space'),p.get('empty'),p.get('x'),p.size);", logs=['1,2 a b  a=b 5'])
    case('query_forgiving_utf8', "console.log(new URLSearchParams('x=%E2%82&y=%FF&z=%E2%28%A1').toString());", logs=['x=%EF%BF%BD&y=%EF%BF%BD&z=%EF%BF%BD%28%EF%BF%BD'])
    case('query_mutation_iteration', "const p=new URLSearchParams([['b','2'],['a','1'],['b','3']]);p.set('b','4');p.append('a','5');p.sort();p.delete('a','1');console.log(p.toString(),JSON.stringify(Object.fromEntries(p.entries())));", logs=['a=5&b=4 {"a":"5","b":"4"}'])
    case('query_live_iteration', "const p=new URLSearchParams('a=1');const it=p.entries();it.next();p.append('b','2');console.log(it.next().value.join('='));", logs=['b=2'])
    case('query_constructor_errors', "let n=0;for(const f of [()=>new URLSearchParams([['a']]),()=>new URLSearchParams(Symbol()),()=>new URLSearchParams().set('x')])try{f()}catch(e){if(e instanceof TypeError)n++}console.log(n);", logs=['3'])
    case('query_bare_absent', "URLSearchParams", profile='bare', expected='missing_global')

    # These supplement the original host-contract cases with engine features.
    case('typed_arrays_and_dataview', "const b=new ArrayBuffer(16);new DataView(b).setUint32(0,0x12345678,true);console.log(new Uint8Array(b)[0]);", logs=['120'])
    if host:
        case('wasm_sync', "const b=new Uint8Array('0061736d010000000105016000017f03020100070a0106616e7377657200000a06010400412a0b'.match(/../g).map(x=>parseInt(x,16)));const m=new WebAssembly.Module(b);console.log(new WebAssembly.Instance(m).exports.answer()===42);", logs=['true'])
    case('async_await_checkpoint', "(async()=>{await 0; console.log('awaited')})();console.log('sync');", logs=['sync','awaited'])
    case('rejection_then_recovery', "Promise.reject('handled').catch(()=>42).then(console.log);", logs=['42'])

    case('resolved_promise_batch', 'for(let i=0;i<70000;i++)Promise.resolve(i);console.log("done");', logs=['done'])
    case('pending_promises_observation_cap', 'const retained=[];for(let i=0;i<65537;i++)retained.push(new Promise(()=>{}));',
         expected='promise_observation_limit', check=lambda r:r['promise_observation_overflow'])
    case('timer_resolves_promise', 'new Promise(r=>setTimeout(()=>r(42),1)).then(console.log);', logs=['42'])
    pending_status = 'async_work_timeout' if host else 'async_work_pending'
    case('unresolved_promise_not_completed', 'globalThis.pending=new Promise(()=>{});', timeout_ms=40,
         expected=pending_status, check=lambda r:r['pending_promises']>=1)
    case('promise_adoption_not_prematurely_settled', 'const p=new Promise(()=>{});globalThis.pending=new Promise(r=>r(p));',
         timeout_ms=40, expected=pending_status, check=lambda r:r['pending_promises']>=2)
    if host:
        wasm_bytes = "new Uint8Array('0061736d010000000105016000017f03020100070a0106616e7377657200000a06010400412a0b'.match(/../g).map(x=>parseInt(x,16)))"
        case('wasm_async_instantiate', f'WebAssembly.instantiate({wasm_bytes}).then(r=>console.log(r.instance.exports.answer()));',
             logs=['42'], check=lambda r:r['pending_promises']==0 and r['engine_tasks']>0)
        case('wasm_async_compile', f'WebAssembly.compile({wasm_bytes}).then(m=>console.log(new WebAssembly.Instance(m).exports.answer()));', logs=['42'])
        case('wasm_async_rejection_handled', 'WebAssembly.compile(new Uint8Array([0])).catch(e=>console.log(e.name));', logs=['CompileError'])
        case('wasm_async_rejection_unhandled', 'WebAssembly.compile(new Uint8Array([0]));', expected='unhandled_rejection')
        case('wasm_and_timer_both_drained', f'WebAssembly.instantiate({wasm_bytes}).then(r=>console.log("wasm"));setTimeout(()=>console.log("timer"),1);',
             check=lambda r:sorted(x['text'] for x in r['logs'])==['timer','wasm'])

    report = dict(schema=2,
        test_environment='standalone V8 executable' if host else 'development-only Node/V8 native adapter; NOT standalone runtime',
        platform=platform.platform(),
        engine_version=next((r['report']['engine_version'] for r in results if 'report' in r), None),
        native_cli='linked and executed, fresh process per case' if host else 'compiled to object; standalone link not exercised',
        game_bundle_executed=False, elapsed_seconds=round(time.monotonic()-started,3),
        passed=sum(r['passed'] for r in results), total=len(results), tests=results)
    if host:
        report['executable_sha256'] = hashlib.sha256(host.read_bytes()).hexdigest()
    else:
        report['not_exercised'] = ['WebAssembly sync and async execution: requires standalone host; borrowed Node context disallows Wasm code generation']
        report['node'] = command([node,'--version'],capture_output=True).stdout.strip()
    path = args.report or ROOT/'reports'/('standalone-tests.json' if host else 'test-results.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(f"\n{report['passed']}/{report['total']} V8 integration cases passed.")
    return 0 if report['passed']==report['total'] else 1

if __name__=='__main__':
    raise SystemExit(main())
