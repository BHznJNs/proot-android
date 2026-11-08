# Android session mode

`libproot.so --android-session [proot options] command [args...]` opts into
an Android-owned, noninteractive session. The mode flag must be the first
argument. Ordinary PRoot invocation keeps its upstream lifecycle behavior.

The same executable supplies an owner process and a PRoot worker process;
this mode removes the separate supervisor binary, not the owner process.
It is a build-time runtime extension, not a syscall extension callback.
`integration.patch` adds the object, entry dispatch, and two startup hooks
only to the disposable build copy. The upstream checkout stays unchanged.
The verified upstream baseline is
`52d65a4dc140ca554d241a1438ddd4f6b00c9813`.

## Ownership and stopping

- Keep the process's stdin pipe open for the lifetime of the session.
- Write byte `q`, close the pipe, or send TERM/INT/QUIT to the owner to stop.
- The guest receives `/dev/null` on stdin; stdout/stderr pass through.
- A stop sends QUIT to the worker. PRoot kills its tracees and drains its
  wait loop; the owner waits for the worker and returns its exit status.
- This preserves the former supervisor's immediate cleanup behavior. It
  does not implement a guest TERM grace period. Use `--kill-on-exit` to
  also clean up background children when the main guest command exits.
- If the Android parent dies, pipe EOF requests cleanup. If the owner
  dies, `PR_SET_PDEATHSIG` delivers QUIT to the worker. Android force-stop
  and OS process killing may independently kill any or all processes;
  this is not a guarantee of shutdown hooks running in those cases.

The owner clears the ART-inherited signal mask, with QUIT blocked across
fork. The worker keeps QUIT blocked until the PRoot cleanup handler is
installed, so startup cancellation and owner death cannot leave a guest
untraced through premature tracer termination. The first guest clears its
mask before entering tracing; it does not inherit the startup QUIT block.
Both hooks are no-ops without `--android-session`.

## Building and validation

Use the normal `build.ps1 -SourceRoot <upstream-checkout>` entry point.
Source, header, and integration patch are covered by the generated build
manifest. Update both extension patches when upstream changes their hook
contexts. An incompatible patch aborts source preparation before applying
either patch.

Host checks: `python -m unittest discover -s build-support -p test_source_overlay.py -v`.
Runtime checks must run from an installed Android app through
`ProcessBuilder`, not just adb shell, to exercise ART's signal inheritance.
The integrating DroidVPS app's `AndroidSessionDeviceTest` covers stop byte,
EOF, TERM, owner death, startup cancellation, guest stdin, and exit status.
Record observed results separately from test coverage and build success.

The source and integration patch are GPL-2.0-or-later and must accompany
redistributed modified PRoot builds. See the input checkout's `COPYING`.
