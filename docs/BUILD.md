# Building the standalone host

## Verified offline route

Tested on Linux x86-64 with GCC 14.2, CMake, Python 3.13, and the locked V8 SDK.
Python 3.10+ is required by the acquisition utilities. No Node or browser is needed.

```sh
python3 tools/bootstrap_v8.py --archive ../v8-13.6.233.17-linux-x64.zip --build
python3 tools/test.py --host build/standalone/zero
```

The artifact ZIP and direct release tar.gz are both accepted, with distinct locked
hashes. The ZIP contains one tar.gz; both layers are verified. The lock is
`config/v8-linux-x64.lock.json`. No remote helper scripts run during installation.
An existing SDK is reused only after comparing its files with a newly verified
extraction. Binary archives are ignored by Git.

`--download --build` uses the pinned release URL instead. This network path could
not reach the internet in the current container; the complete offline route was
executed successfully. The GitHub connector's artifact-download action supplied
the archive here. The connected GitHub tools expose reads/downloads, not remote
repository creation, pushes or forks; no remote write was performed.

## A different engine build

Supply the include tree and static library from the **same** build:

```sh
cmake -S . -B build/custom -DCMAKE_BUILD_TYPE=Release -DZERO_BUILD_V8_HOST=ON \
  -DZERO_V8_INCLUDE_DIR=/absolute/sdk/include \
  -DZERO_V8_LIBRARY=/absolute/sdk/lib/libv8_monolith.a
cmake --build build/custom -j2
python3 tools/test.py --host build/custom/zero
```

If `include/v8-gn.h` is present, CMake defines `V8_GN_HEADER` so V8's generated
configuration selects matching ABI macros. Do not guess pointer compression or
sandbox defines. For other SDK layouts, `ZERO_V8_DEFINITIONS` accepts an explicit
semicolon-separated list from that build; `ZERO_V8_EXTRA_LIBRARIES` supplies extra
matching archives. `ZERO_V8_ICU_DATA` copies matching external `icudtl.dat` when
needed. Other external startup files require explicit packaging/validation.

The locked SDK embeds startup data and omits ICU; it needs no external data file.
Its V8 sandbox is disabled. Merely defining `V8_ENABLE_SANDBOX` in our build cannot
enable a feature absent from the library and would create an ABI mismatch.
The source V8 subtree is taken from Node's vendor tree, but no Node application
code, libnode, libuv, browser code or Go/Rust runtime is linked into `zero`.

No Windows/macOS standalone build was tested. The accompanying pin is Linux-only.
System C/C++ dynamic libraries are still required: this is not a fully static ELF.

## Developer adapter

`python3 tools/test.py` uses installed Node headers and its engine in a separate
native test adapter. The new ScriptOrigin compatibility helper compiles against
both tested V8 header APIs. WebAssembly execution is not tested in this adapter:
Node's borrowed isolate rejects Wasm code generation in the fresh guest context.
Its lack of a V8 default-platform pump is explicitly reported as
`async_work_pending` when a Promise remains unresolved.

## Primary interface/build references

- V8 embedding: https://v8.dev/docs/embed
- Acquired builder: https://github.com/kitten3d/v8-builds/tree/5cebfbe21f8bca6204a248a47c7eca4411a8cbde
- Exact run: https://github.com/kitten3d/v8-builds/actions/runs/33958660304
- Release: https://github.com/kitten3d/v8-builds/releases/tag/v13.6.233.17

Archive integrity was checked; independent reproducible-build verification was not.
