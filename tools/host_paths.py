"""Standalone host paths and explicit Windows graphics arguments."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]


def default_host() -> Path:
    if sys.platform == 'win32':
        choices = [ROOT/'build/windows/zero.exe', ROOT/'build/windows/Release/zero.exe']
        return next((p for p in choices if p.is_file()), choices[0])
    return ROOT/'build/standalone/zero'


def backend_args(backend: str | None) -> list[str]:
    if not backend:
        return []
    if backend not in ('d3d11','warp'):
        raise ValueError('Unknown ANGLE backend')
    return ['--angle-backend', backend]
