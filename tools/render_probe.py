#!/usr/bin/env python3
"""Render an independent native triangle fixture and save its actual pixels.

Uses the standalone executable, not a browser or an image generator. PNG writing
uses only Python's standard library. This is not a Krunker screenshot.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

from host_paths import default_host, backend_args

ROOT = Path(__file__).resolve().parents[1]


def frame_pixels(report: dict) -> tuple[int, int, bytes]:
    """Check a complete row-labelled RGBA8 readback; return top-down RGB."""
    if report.get('status') != 'completed' or report.get('exit_code') != 0:
        raise ValueError('Native fixture did not finish successfully')
    if report.get('logs_dropped', 0):
        raise ValueError('Native readback logs were truncated')
    graphics = report.get('graphics', {})
    if (graphics.get('contexts') != 1 or graphics.get('draw_calls') != 1
            or graphics.get('shader_compiles') != 2 or graphics.get('pixel_reads') != 1
            or graphics.get('backend') not in ('egl-surfaceless-pbuffer','angle-d3d11-pbuffer','angle-warp-pbuffer')):
        raise ValueError('Required real native graphics operations were not recorded')
    logs = report.get('logs', [])
    if not logs or not isinstance(logs[0].get('text'), str):
        raise ValueError('Missing framebuffer header')
    header = logs[0]['text'].split()
    if len(header) != 3 or header[0] != 'FRAME_RGBA8':
        raise ValueError('Invalid framebuffer header')
    width, height = int(header[1]), int(header[2])
    if not (1 <= width <= 2048 and 1 <= height <= 2048):
        raise ValueError('Framebuffer dimensions outside diagnostic cap')
    if len(logs) != height + 1:
        raise ValueError('Missing or extra framebuffer rows')
    rows = {}
    for entry in logs[1:]:
        parts = entry.get('text', '').split()
        if len(parts) != 3 or parts[0] != 'ROW':
            raise ValueError('Invalid row record')
        index = int(parts[1])
        if index not in range(height) or index in rows or len(parts[2]) != width * 8:
            raise ValueError('Duplicate, out-of-range or incorrectly sized row')
        rgba = bytes.fromhex(parts[2])
        if len(rgba) != width * 4:
            raise ValueError('Invalid row byte count')
        if any(alpha != 255 for alpha in rgba[3::4]):
            raise ValueError('This opaque fixture must have alpha 255 everywhere')
        rows[index] = bytes(value for offset, value in enumerate(rgba) if offset % 4 != 3)
    # GL readback is bottom-up; PNG and PPM store top row first.
    return width, height, b''.join(rows[y] for y in reversed(range(height)))


def png_bytes(width: int, height: int, rgb: bytes) -> bytes:
    if width < 1 or height < 1 or len(rgb) != width * height * 3:
        raise ValueError('Invalid RGB image dimensions or length')
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    raw = b''.join(b'\0' + rgb[y*width*3:(y+1)*width*3] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', type=Path, default=default_host())
    parser.add_argument('--out', type=Path, default=ROOT/'reports/native-triangle.png')
    parser.add_argument('--report', type=Path, default=ROOT/'reports/render-probe.json')
    parser.add_argument('--angle-backend',choices=['d3d11','warp'])
    args = parser.parse_args()
    try:
        host = args.host.resolve(strict=True)
        fixture = ROOT/'fixtures/native-triangle.js'
        run = subprocess.run([str(host), *backend_args(args.angle_backend), '--profile', 'graphics', '--timeout-ms', '10000', str(fixture)],
                             capture_output=True, text=True, encoding='utf-8', timeout=20)
        if run.returncode:
            raise ValueError('Native renderer failed: ' + (run.stdout + run.stderr)[:4096])
        report = json.loads(run.stdout)
        width, height, pixels = frame_pixels(report)
        if (width, height) != (128, 128) or len(set(zip(*[iter(pixels)]*3))) < 100:
            raise ValueError('Expected a 128x128 shaded triangle, not an empty/uniform frame')
        image = png_bytes(width, height, pixels)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(image)
        result = dict(schema=1, scope='Independent triangle fixture, NOT Krunker; no window presented',
                      width=width, height=height, fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
                      executable_sha256=hashlib.sha256(host.read_bytes()).hexdigest(),
                      rgb_topdown_sha256=hashlib.sha256(pixels).hexdigest(), png_sha256=hashlib.sha256(image).hexdigest(),
                      native_report=report)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2)+'\n')
        print(f'Native shader pixels: {width}x{height}; PNG: {args.out}; report: {args.report}')
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print('Render probe failed: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
