# Provenance and boundaries — current bring-up

This work continues only the new local `krunker-zero` Git repository, starting
from its exported bundle. The excluded Wok implementation, docs, history and
notes were never opened, searched, cloned, copied or used. No user repository
outside this project was read or changed. The GitHub connector was used for public dependency metadata/source configuration,
artifact downloads, and metadata of a public historical game-source archive. No
code from another client implementation was imported.

## Acquired engine

Normal outbound downloads and DNS in the container failed. The connected GitHub
artifact download action did transfer files into the workspace. A small Rust
bindings artifact proved that transport, but those bindings were not used.
Expired/empty candidates were rejected rather than labeled usable SDKs.

The actual engine came from `kitten3d/v8-builds`, workflow run `33958660304`,
artifact `9968116540`. The 21,103,916-byte ZIP and its contained 21,386,774-byte
release tarball both matched GitHub's SHA-256 digests. Details and exact hashes
are in `config/v8-linux-x64.lock.json`. The SDK contains a static V8 archive,
matching public headers, generated ABI definitions and upstream license files.

The builder uses the V8 source subtree in Node v24.20.0, not Node's runtime.
It alters V8's bundled Abseil namespace to avoid symbol collisions. No Node,
Electron, Chromium browser, Go or Rust runtime was linked into the standalone
executable. The build has pointer compression enabled and V8 sandbox/Intl disabled.
This third-party SDK has not been independently rebuilt or security audited.

The engine import is separate from this project's own source code. Original SDK
archives remain unchanged. Preserve upstream notices; a complete downstream
redistribution/license audit remains a production gate, not a claim made here.
No license for the user's new project was chosen on their behalf.

## Execution evidence

Standalone initialization, linking, shutdown, native bindings and V8 foreground
work are now exercised directly. A discovered asynchronous-Wasm bug was reproduced
before fixing it: the host exited with `completed` and no callback log. After the
fix, the synthetic module compiles, instantiates and returns 42. Pending Promises,
Promise adoption and observation overflow now have explicit diagnostics.

The optional Node development adapter remains separate. It cannot exercise the
standalone platform pump or Wasm code generation in its borrowed guest context;
those checks run only in the standalone suite and are not claimed as adapter wins.

## Original game / remote repository status

Direct acquisition of the original game page was attempted again and returned no
bodies because the container could not resolve/reach the site. The web reader's
parsed public landing-page text was not substituted for original response bytes.
No actual game bundle, assets, gameplay or server session were executed.

The original HTTPS/HAR tools do not execute page scripts. The new, separate
DevTools helper uses a fresh local browser to execute pages normally while saving
permitted response bodies and compiled-source strings. It is not linked or used by
the standalone runtime. Header/POST data and font files are excluded from captures.

The browser helper connected to DevTools, but a real localhost fixture navigation
was explicitly blocked by `ERR_BLOCKED_BY_ADMINISTRATOR`. No policy was changed to
work around it. Zero response or compiled-source bodies were captured. That test
is recorded as blocked and returns nonzero, not passed.

A public historical archive (`crvmblr/krunker-src`) was checked as an acquisition
candidate. Its README identifies it as outdated and describes changing the game's
wrapper. Its large game files were not acquired. It was not represented as a
current pristine game bundle and no archive game code was executed or shipped.

The new native graphics source and fixtures were written within this independent
repository against public Khronos interfaces. System EGL/Mesa/LLVM supplies actual
shader compilation and rasterization. Runtime-loaded native libraries are audited
as well as static/ELF linkage. The triangle is independent fixture code, not game
code or evidence of hardware acceleration. No native window or frame presentation
was performed. Deliberately broken EGL libraries exist only in isolated fault
injection tests, never as production rendering or success placeholders.

The connected GitHub tools available in this session support reads/downloads,
not repository creation, fork creation or pushes. No remote repository or fork
was created. Updated source and full Git history are delivered as local artifacts.
