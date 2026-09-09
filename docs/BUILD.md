# Build and execution

## What was available here

Linux x86-64, GCC 14.2, CMake 3.31.6, Node 22.16.0 with headers. The available V8
reports `12.4.254.21-node.26`. This is the **observed test environment**, not a
recommendation to ship that older engine. Use a maintained engine revision for
actual deployment, and record its exact revision, build arguments and toolchain.

No standalone `libv8_monolith.a` is installed. Outbound dependency downloads failed.
The repo does not contain a V8 source checkout or engine binary. The command below
was not executable end-to-end in this environment.

## Standalone target

Build V8 using its official embedding/build instructions. Its current embedding
example uses a Linux x64 sample configuration and demonstrates the relevant ABI
flags and data files. Start with a maintained source revision and pin it. Compile
the matching upstream hello-world sample successfully before integrating this host.
Do not substitute a Node archive or mismatched headers to force a link.

Primary reference: `https://v8.dev/docs/embed`.

Once that engine build exists:

```sh
cmake -S . -B build/standalone -DCMAKE_BUILD_TYPE=Release \
  -DZERO_BUILD_V8_HOST=ON \
  -DZERO_V8_INCLUDE_DIR=/absolute/path/to/v8/include \
  -DZERO_V8_LIBRARY=/absolute/path/to/v8/out.gn/your-build/obj/libv8_monolith.a \
  -DZERO_V8_EXTRA_LIBRARIES='/absolute/path/to/libv8_libbase.a;/absolute/path/to/libv8_libplatform.a' \
  -DZERO_V8_DEFINITIONS='V8_COMPRESS_POINTERS;V8_ENABLE_SANDBOX' \
  -DZERO_V8_ICU_DATA=/absolute/path/to/that/build/icudtl.dat
cmake --build build/standalone
build/standalone/zero --profile bare fixtures/bare.js
build/standalone/zero --profile core --virtual-time fixtures/clock.js
```

The extra libraries, ABI defines and ICU data are **conditional on the chosen V8
build**, not universally correct flags. The example matches the shape of the
upstream x64 sample; omit items only when that engine was built without them.
Keep sandbox, pointer-compression and 31-bit-Smi defines in agreement with the
engine. Use its matching C++ toolchain requirements and snapshot/ICU files.
The CMake target is provided but its final linkage still needs validation.

`native/main.cc` owns V8 startup, allocator/isolate creation and teardown. Its
`--memory-mb` flag sets an old-generation heap target; it is not a process RSS or
ArrayBuffer cap. The host reports JS timeouts, but V8/native OOM can still terminate
the process. Run trusted inputs in an OS-isolated process during bring-up.

## Development-only adapter

```sh
python3 tools/test.py
# A distribution-installed Node may need an explicit header directory:
python3 tools/test.py --node-include /usr/include/node
```

This dynamically loads a small C++ test adapter into the installed Node executable.
The adapter calls the **same native host code** using a fresh guest V8 Context and
private microtask queue. No Node guest globals are passed across. Each test uses
one separate child process. This checks native binding and scheduler behavior;
it does not validate standalone V8 initialization, linking, shutdown or packaging.
The borrowed-isolate promise hook is why the adapter is one-run-per-process.

A V8 Context is not an OS security sandbox. Do not treat the test adapter as a
safe service for arbitrary uploaded code. Its observed V8 version is recorded in
every report. The standalone CMake target never includes the adapter.

## Diagnostics

Exit 0: that input's execution completed with no outstanding host tasks.
Exit 2: uncaught script exception or an unhandled Promise rejection.
Exit 3: wall-clock or callback budget exhausted; the run is incomplete.
Exit 64: unsupported/invalid configuration.
Exit 70: input/tool failure, where applicable.

Reports contain source positions, the exception, bounded logs, task counts and
clock mode. An uncaught `ReferenceError` may identify a missing global. An error
caught by the game is not observable in this first probe; no fake API is installed
to force execution through a branch. Stack text alone is not a complete inventory.
