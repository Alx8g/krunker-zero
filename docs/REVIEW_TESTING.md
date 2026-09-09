# Windows maintenance acceptance

Base this work on `fix/windows-native-acceptance` at `3d7cda7` or a descendant.
Keep your existing private capture and SDK worktree. Do not reset/clean it and do
not inspect excluded projects. Review `AGENTS.md` and `CURRENT_STATUS.md` first.

## Apply and build

The delivered patch contains changes relative to the hash-verified source of
`3d7cda7`, not a replacement repository/history. Apply it on a new local branch:

```powershell
git status --short
git switch -c fix/runtime-contracts-and-evidence
git apply --check C:\path\krunker-zero-fixes.patch
git apply --index C:\path\krunker-zero-fixes.patch
```

Start from the verified development branch, not the old `main`. Stop on conflicts
or local changes; reconcile them rather than forcing the patch. No reset, clean,
force push, credential sharing or source-capture upload is required.

In your existing x64 Visual Studio developer shell:

```powershell
py -3 tools/windows.py doctor
py -3 tools/windows.py build
py -3 -m unittest discover -s tests
py -3 tools/windows.py test --angle-backend d3d11 --interactive --reports reports/windows-review-d3d11
py -3 tools/windows.py test --angle-backend warp --reports reports/windows-review-warp
py -3 tools/test_query_differential.py --host build/windows/zero.exe --report reports/windows-review-query.json
```

`uv run --no-project python` may replace `py -3`, as in the original local run.
No Node/browser is needed for these tests. Expected core count is 100, graphics
52 per backend, interactive platform 13 and noninteractive platform 10. The Python
unit count is recorded in the review validation report. Differential vectors:
2,048 by default. These counts are not game compatibility percentages.

For a NEW SDK source build only, use `doctor --source-build` before `deps`. ANGLE
requires Windows SDK 10.0.28000.0 headers, x64 libraries and tools. The preflight
must name missing files and fail before downloading V8 or ANGLE. Do not delete
existing validated SDKs: the source lock and receipts have not changed.

## Check the tighter audit

Both module audits must observe the exact child executable. The graphics audit
must observe both app-local ANGLE DLLs, a created context/device and the explicitly
requested backend. Imported DLL names alone cannot make it pass. Empty/transient
snapshots remain distinguished from complete nonempty snapshots. A new failure
requires investigation; do not weaken the checks to preserve a green report.

Retain original baseline reports. These new commands write separate destinations.
Native Windows behavior of the new audit/preflight has NOT been exercised by the
remote review environment, which only ran their portable decision tests.

## Continue original-game integration

Rerun the same private ordered, hashed bootstrap used previously. It is expected
to remain blocked at missing `document`; this patch does not implement document or
location. Record the actual context member accesses and values on the permitted
local machine before implementing the next minimum contract. Do not publish raw
captures, inline/eval snapshots, credential-bearing URLs or private probe reports.

Physically test keyboard/raw mouse, click capture, Escape and focus-loss release,
minimize/restore and DPI separately. A window-swap test does not validate those.

After review/testing, commit only intended code and sanitized reports, then push
this branch and open a PR against `fix/windows-native-acceptance`. Do not merge
into main or publish a release merely because the fixtures pass.
