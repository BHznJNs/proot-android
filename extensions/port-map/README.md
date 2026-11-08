# Build-time port mapping extension

`port_map.c` is the GPL-2.0-or-later PRoot extension maintained by
proot-android. `integration.patch` registers its object, callback, and
`--port-map=guest:host,...` CLI option in a disposable upstream source copy.
Both files belong to this project; the input Termux PRoot checkout stays
unchanged. The original `-p` option is preserved.

The integration patch is verified against Termux PRoot commit
`52d65a4dc140ca554d241a1438ddd4f6b00c9813`. It is applied with `git apply
--check` before any hunk is written. An incompatible upstream revision or
an already-patched input fails the build, rather than omitting the feature
or applying it twice. Review this small integration patch when updating
the upstream revision.

The public build command remains `build.ps1 -SourceRoot <upstream-checkout>`.
`build-support/compile_proot.py` creates a fresh `build-support/proot-arm64`
tree for every build, then calls `source_overlay.py` before compilation.
`build-support/build-manifest.json` records the upstream commit, source
state, extension and patch hashes, prepared source hash, and the full
version string identifying this extended build.

The extension supports native ARM64 IPv4/IPv6 TCP and UDP port translation.
It creates no network namespace. Its source and the integration patch
must accompany redistributed modified PRoot builds under the PRoot GPL
license; the upstream license is in `COPYING` of the input checkout.

Host preparation checks (with the upstream checkout in sibling `proot`, or
set `PROOT_TEST_SOURCE` to its location):

```powershell
python -m unittest discover -s build-support -p test_source_overlay.py -v
```

For Android runtime validation, start PRoot from an installed application
and run a guest listener with `--port-map=80:8080`. Verify access through
host port 8080, IPv4/IPv6 and TCP/UDP behavior, loopback destinations,
invalid mapping rejection, and port reuse after stopping the session.
Record the device, build inputs, commands, and observed results with the
integration's test records.
