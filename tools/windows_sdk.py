"""Read-only prerequisite checks for the pinned Windows source builds.

The ANGLE SDK requirement was discovered in the native Windows acceptance run
recorded in AGENT_HANDOFF.txt at upstream 3d7cda7. It is separate from the source
lock so adding a preflight does not invalidate existing SDK receipts/workspaces.
No downloads, registry writes, installations or SDK selection are performed here.
"""
from pathlib import Path

ANGLE_PIN = '041e83047db3e3b45f51cf98daba407583a1b2eb'
ANGLE_SDK = '10.0.28000.0'
SDK_FILES = (
    'Include/{version}/um/Windows.h',
    'Include/{version}/shared/sdkddkver.h',
    'Include/{version}/ucrt/corecrt.h',
    'Lib/{version}/um/x64/kernel32.lib',
    'Lib/{version}/ucrt/x64/ucrt.lib',
    'bin/{version}/x64/rc.exe',
    'bin/{version}/x64/mt.exe',
)


def probe_source_sdks(root: str, lock: dict, components=('v8', 'angle')) -> dict:
    """Check exact known requirements, not merely whether WindowsSdkDir is set.

    V8's other toolchain requirements are still enforced by its pinned build.
    This probe is deliberately not a certificate that every build tool is ready.
    """
    unknown = set(components) - {'v8', 'angle'}
    if unknown:
        raise ValueError('Unknown source-build components: ' + ', '.join(sorted(unknown)))
    checks = []
    if 'angle' in components:
        if lock['angle']['commit'] != ANGLE_PIN:
            raise ValueError('ANGLE pin changed; review its SDK prerequisite before source builds')
        missing = [part.format(version=ANGLE_SDK) for part in SDK_FILES
                   if not root or not (Path(root)/part.format(version=ANGLE_SDK)).is_file()]
        checks.append(dict(component='angle', source_commit=ANGLE_PIN,
                           required_version=ANGLE_SDK, missing_files=missing, ready=not missing))
    return dict(sdk_root=root, checks=checks, ready=all(item['ready'] for item in checks),
                scope='Known pinned source SDK prerequisites; native execution and remaining upstream toolchain checks are separate')


def require_source_sdks(root: str, lock: dict, components=('v8', 'angle')) -> dict:
    result = probe_source_sdks(root, lock, components)
    if not result['ready']:
        detail = '; '.join(item['component'] + ' requires Windows SDK ' + item['required_version'] +
                           ': missing ' + ', '.join(item['missing_files'])
                           for item in result['checks'] if not item['ready'])
        raise ValueError(detail + '. Install the SDK components, reopen the x64 developer shell, and rerun. No dependency download was started by this preflight.')
    return result
