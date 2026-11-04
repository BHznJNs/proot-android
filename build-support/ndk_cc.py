"""Adapt GNUmakefile's -m32 convention to the Android NDK target triples."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ndk = Path(os.environ['PROOT_BUILD_NDK'])
args = sys.argv[1:]
compat = '-m32' in args
args = [arg for arg in args if arg != '-m32']
# This translation unit uses strcmp/memset without including string.h.
# Supply declarations for modern Clang, without changing the source snapshot.
if any(arg.replace('\\', '/').endswith('/extension/ashmem_memfd/ashmem_memfd.c') for arg in args):
    args = ['-include', 'string.h', *args]
target = 'armv7a-linux-androideabi' if compat else 'aarch64-linux-android'
compiler = ndk / 'toolchains/llvm/prebuilt/windows-x86_64/bin/clang.exe'
command = [str(compiler), '--target=' + target + os.environ.get('PROOT_BUILD_API', '28')]
if compat:
    command.append('-marm')
if '-o' in args and args[args.index('-o') + 1] == '/dev/null':
    with tempfile.TemporaryDirectory(prefix='proot-ndk-probe-') as temp:
        args[args.index('-o') + 1] = str(Path(temp) / 'probe')
        raise SystemExit(subprocess.call(command + args))
sys.exit(subprocess.call(command + args))
