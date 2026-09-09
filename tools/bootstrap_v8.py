#!/usr/bin/env python3
"""Acquire the pinned standalone V8 SDK, verify hashes, and optionally build.
Accepts the original release tar.gz or the exact GitHub Actions ZIP offline.
Never downloads or executes a helper script, and never falls back to Node.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024


def checked_digest(raw: bytes, expected: str) -> str:
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError(f'SHA-256 mismatch: expected {expected}, got {actual}')
    return actual


def unwrap(raw: bytes, lock: dict) -> bytes:
    if len(raw) > MAX_ARCHIVE:
        raise ValueError('archive exceeds size limit')
    if raw.startswith(b'PK'):
        checked_digest(raw, lock['artifact_zip_sha256'])
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) != 1 or entries[0].filename != lock['archive_name']:
                raise ValueError('unexpected GitHub artifact contents')
            if entries[0].file_size > MAX_ARCHIVE:
                raise ValueError('nested archive exceeds size limit')
            raw = archive.read(entries[0])
    checked_digest(raw, lock['archive_sha256'])
    return raw


def extract_verified_tar(raw: bytes, destination: Path, prefix: str) -> None:
    """Extract only regular files/directories inside prefix into a NEW empty dir."""
    if not destination.is_dir() or any(destination.iterdir()) or destination.is_symlink():
        raise ValueError('extraction requires a new empty real directory')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = archive.getmembers()
        if len(members) > 2048 or sum(m.size for m in members) > MAX_EXPANDED:
            raise ValueError('expanded archive exceeds bounds')
        seen = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or '..' in path.parts or not path.parts or
                path.parts[0] != prefix or '\\' in member.name or ':' in member.name):
                raise ValueError('unsafe archive path')
            if not (member.isdir() or member.isfile()):
                raise ValueError('links and special files are forbidden')
            if str(path) in seen:
                raise ValueError('duplicate archive member')
            seen.add(str(path))
        # Manual extraction avoids tar metadata, mode, owner, and link surprises.
        for member in members:
            path = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as src, path.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
                path.chmod(0o644)


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith('https://'):
            raise ValueError('refusing HTTPS downgrade')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(lock: dict) -> bytes:
    opener = urllib.request.build_opener(HTTPSRedirect())
    req = urllib.request.Request(lock['archive_url'], headers={'User-Agent': 'krunker-zero-dependency-bootstrap/1'})
    with opener.open(req, timeout=30) as response:
        raw = response.read(MAX_ARCHIVE + 1)
    if len(raw) > MAX_ARCHIVE:
        raise ValueError('download exceeds size limit')
    return raw


def install(raw: bytes, lock: dict, deps: Path) -> Path:
    raw = unwrap(raw, lock)
    deps.mkdir(parents=True, exist_ok=True)
    target = deps / lock['prefix']
    if target.is_symlink():
        raise ValueError('SDK destination cannot be a symlink')
    with tempfile.TemporaryDirectory(prefix='.v8-verified-', dir=deps) as tmp:
        staging = Path(tmp)
        extract_verified_tar(raw, staging, lock['prefix'])
        sdk = staging / lock['prefix']
        for rel in ('include/v8.h', 'include/v8-gn.h', 'include/v8-version.h', 'lib/libv8_monolith.a', 'lic/LICENSE'):
            if not (sdk / rel).is_file():
                raise ValueError(f'Incomplete SDK: {rel}')
        if not (sdk/'lib/libv8_monolith.a').read_bytes().startswith(b'!<arch>\n'):
            raise ValueError('not a static library')
        (sdk/'zero-provenance.json').write_text(json.dumps(lock, indent=2)+'\n')
        if target.exists():
            # Repeated setup is safe only if EVERY SDK file still matches the
            # newly verified archive. A receipt alone is not proof of integrity.
            def fingerprints(root):
                files = {}
                for p in root.rglob('*'):
                    if p.is_symlink():
                        raise ValueError('symlink in existing SDK')
                    if p.is_file() and p.name != 'zero-provenance.json':
                        files[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
                return files
            if not target.is_dir() or fingerprints(target) != fingerprints(sdk):
                raise ValueError('existing SDK differs from verified archive; use a fresh --deps directory')
            return target
        sdk.rename(target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--archive', type=Path, help='Exact release tar.gz or GitHub Actions ZIP')
    source.add_argument('--download', action='store_true', help='Use the pinned public release URL')
    parser.add_argument('--deps', type=Path, default=ROOT/'deps')
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--build-dir', type=Path, default=ROOT/'build/standalone')
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        parser.error('This SDK pin is Linux x86-64 only; do not use it on another platform')
    lock = json.loads((ROOT/'config/v8-linux-x64.lock.json').read_text())
    try:
        if args.archive and args.archive.stat().st_size > MAX_ARCHIVE:
            raise ValueError('archive exceeds size limit')
        raw = args.archive.read_bytes() if args.archive else download(lock)
        sdk = install(raw, lock, args.deps.resolve())
        print(f'Verified standalone V8 SDK: {sdk}')
        print('Development build: V8 sandbox and ICU/Intl are disabled upstream.')
        if args.build:
            build = args.build_dir.resolve()
            cmd = ['cmake', '-S', str(ROOT), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release',
                   '-DZERO_BUILD_V8_HOST=ON', f'-DZERO_V8_INCLUDE_DIR={sdk}/include',
                   f'-DZERO_V8_LIBRARY={sdk}/lib/libv8_monolith.a']
            subprocess.run(cmd, check=True)
            subprocess.run(['cmake', '--build', str(build), '-j2'], check=True)
            subprocess.run(['ctest', '--test-dir', str(build), '--output-on-failure'], check=True)
        return 0
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print(f'V8 bootstrap failed: {error}', file=sys.stderr)
        print('No browser or Node fallback was used. An exact offline --archive is supported.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
