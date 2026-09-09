#!/usr/bin/env python3
"""Build pinned, standalone V8 and ANGLE on Windows; no browser/Node runtime.

Runs only on Windows x64 in an x64 Visual Studio developer environment. --plan
can be used on any OS to inspect the exact pins/arguments without downloads.
All checkouts, intermediate outputs and staged SDKs are under a managed directory.
An existing unmanaged directory or mismatched receipt is never overwritten.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'config/windows-deps.lock.json'
RECEIPT = 'zero-sdk-receipt.json'


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1 << 20), b''):
            h.update(data)
    return h.hexdigest()


def load_lock(path: Path = LOCK) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 1 or data.get('target') != 'windows-x64':
        raise ValueError('Unsupported dependency lock schema or target')
    expected = {
        'v8': 'https://chromium.googlesource.com/v8/v8.git',
        'angle': 'https://chromium.googlesource.com/angle/angle.git',
        'depot_tools': 'https://chromium.googlesource.com/chromium/tools/depot_tools.git',
    }
    for name, url in expected.items():
        item = data[name]
        if item.get('url') != url or not re.fullmatch(r'[0-9a-f]{40}', item.get('commit', '')):
            raise ValueError('Expected pinned official source for ' + name)
    return data


def gn_text(args: dict) -> str:
    lines = []
    for key, value in sorted(args.items()):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', key):
            raise ValueError('Invalid GN argument name')
        if type(value) not in (bool, int, str):
            raise ValueError('Unsupported GN argument value')
        lines.append(f'{key} = {json.dumps(value)}')
    return '\n'.join(lines) + '\n'


def require_windows() -> None:
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('This source-build route requires native Windows x64; no Linux/WSL or ARM64 substitution')
    if sys.maxsize <= 2**32:
        raise ValueError('Use 64-bit Python')
    if sys.version_info < (3, 11):
        raise ValueError('Python 3.11 or newer is required')


def doctor() -> dict:
    native = sys.platform == 'win32' and platform.machine().lower() in ('amd64', 'x86_64')
    programs = {name: shutil.which(name) for name in ('git', 'cmake', 'ninja', 'cl', 'dumpbin')}
    arch = os.environ.get('VSCMD_ARG_TGT_ARCH', '')
    sdk = os.environ.get('WindowsSdkDir', '')
    result = dict(platform=sys.platform, machine=platform.machine(), python=sys.version,
                  python_64bit=sys.maxsize > 2**32, native_windows_x64=native,
                  tools=programs, visual_studio_target=arch, windows_sdk=sdk,
                  ready=native and sys.version_info >= (3, 11) and sys.maxsize > 2**32
                  and all(programs.values()) and arch.lower() == 'x64' and bool(sdk))
    result['instructions'] = ('Use the x64 Native Tools/Developer PowerShell for VS 2022 with Desktop development with C++, '
                              'a compatible Windows SDK, Git, Python 3.11+, CMake and Ninja. No registry changes are made.')
    return result


def checked(command: list[str] | str, cwd: Path, env: dict, *, capture: bool = False) -> str:
    """Only trusted program paths/arguments. Native return codes never ignored."""
    print('+ ' + (command if isinstance(command, str) else subprocess.list2cmdline(command)), flush=True)
    try:
        cp = subprocess.run(command, cwd=cwd, env=env, check=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None,
                            text=True, encoding='utf-8', errors='replace')
    except subprocess.CalledProcessError as error:
        if capture:
            for output in (error.stdout, error.stderr):
                if output: print(output, file=sys.stderr, flush=True)
        raise
    return cp.stdout.strip() if capture else ''


def checked_tool(tool: str, arguments: list[str], cwd: Path, env: dict, *, capture: bool = False) -> str:
    """depot_tools exposes Windows .bat launchers, not all .exe files.

    cmd expansion is unavoidable for its trusted launchers. Reject metacharacters
    and use a quoted /s /c command. The native host and tests never use a shell.
    """
    path = shutil.which(tool, path=env['PATH'])
    if not path:
        raise ValueError('Required tool not found: ' + tool)
    # These pinned wrappers only dispatch to adjacent Python entry points.
    # Avoid their uninitialized python-bin bootstrap with our validated Python.
    if tool in ('gn', 'ninja') and Path(path).suffix.lower() == '.bat':
        script = Path(path).with_suffix('.py')
        if not script.is_file():
            raise ValueError('Missing depot_tools Python entry point: ' + str(script))
        if tool == 'gn' and arguments and arguments[0] == 'gen':
            arguments = [*arguments, '--script-executable=' + sys.executable]
        return checked([sys.executable, str(script), *arguments], cwd, env, capture=capture)
    command = [path, *arguments]
    if Path(path).suffix.lower() in ('.bat', '.cmd'):
        if any(any(c in arg for c in '\r\n%!*&|<>^\"()') for arg in command):
            raise ValueError('depot_tools batch paths/arguments cannot contain command-shell metacharacters')
        # Pass the complete Windows command line as a STRING so Python does
        # not CRT-escape the nested quotes a second time. /s strips exactly
        # the outer pair; the quoted launcher path is retained for cmd parsing.
        shell = os.environ.get('COMSPEC', str(Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/cmd.exe'))
        command = subprocess.list2cmdline([shell]) + ' /d /v:off /s /c "' + subprocess.list2cmdline(command) + '"'
    return checked(command, cwd, env, capture=capture)


def checkout(folder: Path, item: dict, env: dict) -> None:
    """Never reset/clean user's checkout; only create or reuse this pinned clone."""
    if not folder.exists():
        folder.mkdir(parents=True)
        checked(['git', 'init', str(folder)], folder.parent, env)
        checked(['git', '-C', str(folder), 'remote', 'add', 'origin', item['url']], folder.parent, env)
    if not (folder / '.git').is_dir():
        raise ValueError('Refusing unmanaged checkout: ' + str(folder))
    remote = checked(['git', '-C', str(folder), 'remote', 'get-url', 'origin'], folder.parent, env, capture=True)
    if remote != item['url']:
        raise ValueError('Checkout origin does not match lock: ' + str(folder))
    status = checked(['git', '-C', str(folder), 'diff', '--name-only', 'HEAD'], folder.parent, env, capture=True) if (folder/'.git/HEAD').exists() and _has_head(folder, env) else ''
    staged = checked(['git', '-C', str(folder), 'diff', '--cached', '--name-only'], folder.parent, env, capture=True)
    if status or staged:
        raise ValueError('Refusing to update modified checkout: ' + str(folder))
    if _has_head(folder, env):
        head = checked(['git', '-C', str(folder), 'rev-parse', 'HEAD'], folder.parent, env, capture=True)
        if head != item['commit']:
            raise ValueError('Checkout has a different commit. Use a NEW --work directory, not a destructive reset: ' + str(folder))
        return
    checked(['git', '-C', str(folder), 'fetch', '--depth', '1', 'origin', item['commit']], folder.parent, env)
    checked(['git', '-C', str(folder), 'checkout', '--detach', item['commit']], folder.parent, env)


def _has_head(folder: Path, env: dict) -> bool:
    return subprocess.run(['git', '-C', str(folder), 'rev-parse', '--verify', 'HEAD'], env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def required_paths(component: str) -> list[str]:
    if component == 'v8':
        return ['include/v8.h', 'include/v8-version.h', 'include/v8-gn.h', 'lib/v8_monolith.lib']
    if component == 'angle':
        return ['bin/libEGL.dll', 'bin/libGLESv2.dll']
    raise ValueError('Unknown SDK component')


def record_sdk(stage: Path, component: str, lock: dict) -> None:
    for path in required_paths(component):
        if not (stage/path).is_file():
            raise ValueError('Missing SDK output: ' + path)
    files = {p.relative_to(stage).as_posix(): digest(p) for p in sorted(stage.rglob('*'))
             if p.is_file() and p.name != RECEIPT}
    receipt = dict(schema=1, component=component, target=lock['target'],
                   commit=lock[component]['commit'], url=lock[component]['url'],
                   gn_args=lock[component]['gn_args'], crt=lock['crt'],
                   created_at=datetime.now(timezone.utc).isoformat(), sha256=files,
                   validation='locally built outputs; native runtime tests are separate acceptance gates')
    (stage/RECEIPT).write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')


def verify_sdk(stage: Path, component: str, lock: dict) -> dict:
    receipt = json.loads((stage/RECEIPT).read_text(encoding='utf-8'))
    for key, expected in [('schema', 1), ('component', component), ('target', lock['target']),
                          ('commit', lock[component]['commit']), ('gn_args', lock[component]['gn_args']),
                          ('url', lock[component]['url']), ('crt', lock['crt'])]:
        if receipt.get(key) != expected:
            raise ValueError('SDK receipt mismatch: ' + key)
    hashes = receipt.get('sha256', {})
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('Empty SDK hash inventory')
    for needed in required_paths(component):
        if needed not in hashes:
            raise ValueError('Required SDK file not in receipt: ' + needed)
    actual = {p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file() and p.name != RECEIPT}
    if actual != set(hashes):
        raise ValueError('SDK inventory has changed; refusing stale receipt')
    for name, value in hashes.items():
        if '\\' in name or ':' in name or name.startswith('/') or '..' in Path(name).parts:
            raise ValueError('Unsafe SDK receipt path')
        path = stage/name
        if path.is_symlink() or not path.resolve().is_relative_to(stage.resolve()):
            raise ValueError('SDK files may not escape the staged tree')
        if not re.fullmatch(r'[0-9a-f]{64}', value) or digest(path) != value:
            raise ValueError('SDK hash mismatch: ' + name)
    return receipt


def validate_crt_directives(text: str) -> None:
    """Require /MT Release evidence; do not suppress conflicting runtime libraries."""
    libraries = {x.upper() for x in re.findall(r'/DEFAULTLIB:\s*"?([A-Za-z0-9_.-]+)', text, re.I)}
    libraries = {x.removesuffix('.LIB') for x in libraries}
    conflicts = libraries.intersection({'MSVCRT', 'MSVCRTD', 'MSVCPRT', 'MSVCPRTD', 'LIBCMTD', 'LIBCPMTD'})
    if conflicts or 'LIBCMT' not in libraries:
        raise ValueError('Expected release /MT V8 archive; inspect dumpbin directives before changing CRT settings')


def copy_licenses(source: Path, stage: Path) -> None:
    """Retain source notices for development. Not a completed distribution audit."""
    output = stage/'licenses'
    candidates = [p for p in source.glob('LICENSE*') if p.is_file()]
    third_party = source/'third_party'
    if third_party.exists():
        # Avoid scanning output trees; upstream third-party source notices only.
        candidates += [p for p in third_party.rglob('*') if p.is_file()
                       and p.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE'))
                       and '.git' not in p.parts and p.stat().st_size < 2*1024*1024]
    for path in candidates:
        dest = output/path.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    (stage/'REDISTRIBUTION-NOTICE.txt').write_text(
        'Development SDK. Source license/notice files were retained; this is NOT a completed '\
        'redistribution or third-party attribution audit. Audit compiler/runtime and transitive '\
        'components before public distribution.\n', encoding='utf-8')


def prepare_git_launcher(work: Path, env: dict) -> Path:
    """Supply pinned depot_tools' git.bat without running its global bootstrap."""
    git = shutil.which('git.exe', path=env['PATH'])
    if not git or any(c in git for c in '\r\n%!*&|<>^"'):
        raise ValueError('A safe installed git.exe path is required')
    directory = work/'zero-launchers'
    directory.mkdir(exist_ok=True)
    launcher = directory/'git.bat'
    content = '@echo off\nsetlocal\nset "NoDefaultCurrentDirectoryInExePath=1"\n"'+git+'" %*\n'
    if launcher.exists():
        if launcher.read_text(encoding='utf-8') != content:
            raise ValueError('Refusing modified managed Git launcher')
    else:
        with launcher.open('x', encoding='utf-8', newline='\r\n') as output:
            output.write(content)
    return directory


def build(component: str, work: Path, dest: Path, lock: dict, jobs: int) -> None:
    require_windows()
    prerequisites = doctor()
    if not prerequisites['ready']:
        raise ValueError(json.dumps(prerequisites, indent=2))
    if jobs < 1 or jobs > 256:
        raise ValueError('--jobs must be 1..256')
    work = work.resolve(); dest = dest.resolve()
    # Chromium's batch launchers and GN generally require uncomplicated source paths.
    # The finished native host itself DOES support Unicode/spaces, tested separately.
    if not str(work).isascii() or re.search(r'[\s%!*&|<>^"()]', str(work)):
        raise ValueError('Use a short ASCII dependency --work path without spaces/metacharacters (e.g. C:\\kz-deps). Native host paths have no such restriction.')
    if dest.exists():
        verify_sdk(dest, component, lock)
        print('Verified existing ' + component + ' SDK; no replacement or downloads performed.')
        return
    work.mkdir(parents=True, exist_ok=True)
    marker = work/'zero-managed-build.json'
    if marker.exists():
        managed = json.loads(marker.read_text(encoding='utf-8'))
        if managed.get('lock_sha256') != digest(LOCK):
            raise ValueError('Managed work directory belongs to a different lock; use a new --work directory')
    elif any(work.iterdir()):
        raise ValueError('Refusing existing unmanaged --work directory')
    else:
        marker.write_text(json.dumps({'schema':1,'lock_sha256':digest(LOCK)}), encoding='utf-8')
    env = os.environ.copy()
    env.update(DEPOT_TOOLS_WIN_TOOLCHAIN='0', DEPOT_TOOLS_UPDATE='0', PYTHONUTF8='1', GIT_TERMINAL_PROMPT='0')
    # Upstream only probes default installation paths unless explicitly told.
    # Reuse the active VS 2022 developer environment for custom installations.
    if env.get('VISUALSTUDIOVERSION', env.get('VSCMD_VER', '')).startswith('17.') and env.get('VSINSTALLDIR'):
        env.setdefault('vs2022_install', env['VSINSTALLDIR'])
    depot = work/'depot_tools'
    checkout(depot, lock['depot_tools'], env)
    launchers = prepare_git_launcher(work, env)
    env['PATH'] = str(depot) + os.pathsep + str(launchers) + os.pathsep + env['PATH']
    workspace = work/(component+'-work'); workspace.mkdir(exist_ok=True)
    source = workspace/component
    checkout(source, lock[component], env)
    variables = ({'checkout_angle_cl_deps':False,'checkout_angle_dawn_deps':False,
                  'checkout_angle_restricted_traces':False} if component == 'angle' else {})
    config = 'solutions = '+repr([dict(name=component, url=lock[component]['url'], managed=False,
                                      custom_deps={}, custom_vars=variables)])+'\n'
    gclient = workspace/'.gclient'
    if gclient.exists() and gclient.read_text(encoding='utf-8') != config:
        raise ValueError('Refusing modified .gclient configuration')
    gclient.write_text(config, encoding='utf-8')
    checked_tool('gclient', ['sync','--jobs','2','--revision', component+'@'+lock[component]['commit']], workspace, env)
    if checked(['git','-C',str(source),'rev-parse','HEAD'],workspace,env,capture=True) != lock[component]['commit']:
        raise ValueError('gclient changed the requested source pin')
    # Save exact dependency revisions before staging (evidence, not a reproducibility proof).
    revisions = checked_tool('gclient', ['revinfo'], workspace, env, capture=True)
    out = source/'out/zero-release'; out.mkdir(parents=True, exist_ok=True)
    (out/'args.gn').write_text(gn_text(lock[component]['gn_args']), encoding='utf-8')
    checked_tool('gn', ['gen', 'out/zero-release', '--fail-on-unused-args'], source, env)
    targets = ['v8_monolith'] if component == 'v8' else ['libEGL', 'libGLESv2']
    checked_tool('ninja', ['-C','out/zero-release','-j',str(jobs),*targets], source, env)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=component+'-stage-', dir=dest.parent) as temp:
        stage = Path(temp)/'sdk'; stage.mkdir()
        if component == 'v8':
            header_dir = source/'out/zero-header'; header_dir.mkdir(parents=True, exist_ok=True)
            args = dict(lock['v8']['gn_args'], v8_generate_external_defines_header=True)
            (header_dir/'args.gn').write_text(gn_text(args), encoding='utf-8')
            checked_tool('gn', ['gen','out/zero-header','--fail-on-unused-args'], source, env)
            checked_tool('ninja', ['-C','out/zero-header','gen_v8_gn'], source, env)
            header = header_dir/'gen/include/v8-gn.h'
            text = header.read_text(encoding='utf-8')
            for flag in ('V8_COMPRESS_POINTERS', 'V8_ENABLE_SANDBOX'):
                if not re.search(r'^#define\s+'+flag+r'\s+1\s*$', text, re.M):
                    raise ValueError('Generated V8 ABI header does not enable '+flag)
            if re.search(r'^#define\s+V8_INTL_SUPPORT\s+1', text, re.M):
                raise ValueError('Unexpected V8 Intl configuration')
            shutil.copytree(source/'include', stage/'include')
            shutil.copy2(header, stage/'include/v8-gn.h')
            (stage/'lib').mkdir()
            shutil.copy2(out/'obj/v8_monolith.lib', stage/'lib/v8_monolith.lib')
            directives = checked_tool('dumpbin', ['/directives', str(stage/'lib/v8_monolith.lib')], source, env, capture=True)
            # /MT and /MD object mixes must be discovered before linking, not suppressed.
            validate_crt_directives(directives)
            (stage/'crt-directives.txt').write_text(directives+'\n', encoding='utf-8')
        else:
            (stage/'bin').mkdir()
            for name in ('libEGL.dll','libGLESv2.dll'):
                shutil.copy2(out/name, stage/'bin'/name)
            if (out/'d3dcompiler_47.dll').is_file():
                shutil.copy2(out/'d3dcompiler_47.dll', stage/'bin/d3dcompiler_47.dll')
        (stage/'upstream-revisions.txt').write_text(revisions+'\n', encoding='utf-8')
        (stage/'args.gn').write_text(gn_text(lock[component]['gn_args']), encoding='utf-8')
        copy_licenses(source, stage)
        record_sdk(stage, component, lock)
        verify_sdk(stage, component, lock)
        # Rename only to an absent destination. Never overwrite an SDK another agent edited.
        stage.rename(dest)
    print('Staged verified files: ' + str(dest))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--component', choices=['v8','angle','all'], default='all')
    p.add_argument('--work', type=Path, default=Path('C:/kz-deps'))
    p.add_argument('--out', type=Path, default=ROOT/'deps/windows-x64')
    p.add_argument('--jobs', type=int, default=min(os.cpu_count() or 2, 8))
    p.add_argument('--plan', action='store_true')
    args=p.parse_args()
    try:
        lock=load_lock()
        if args.plan:
            print(json.dumps(lock, indent=2)); return 0
        for name in ('v8','angle') if args.component=='all' else (args.component,):
            build(name,args.work,args.out/name,lock,args.jobs)
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print('Windows dependency setup failed: '+str(exc), file=sys.stderr); return 1


if __name__=='__main__': raise SystemExit(main())
