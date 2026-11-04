"""Build the unmodified Termux GNUmakefile out of tree on Windows."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import shutil

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--ndk', type=Path, required=True)
parser.add_argument('--shell', type=Path, required=True)
parser.add_argument('--api', type=int, default=28)
args = parser.parse_args()
root = Path(__file__).resolve().parent
source = args.source.resolve()
ndk = args.ndk.resolve()
tools = ndk / 'toolchains/llvm/prebuilt/windows-x86_64/bin'
build = root / 'proot-arm64'
depbuild = root / 'native-deps'
bindir = root / 'bin'
for directory in (build, depbuild, bindir):
    directory.mkdir(parents=True, exist_ok=True)
# The upstream Makefile prefixes SRC to prerequisites already expanded by
# VPATH. Build a byte-for-byte source snapshot to avoid that path duplication.
shutil.copytree(source / 'src', build, dirs_exist_ok=True)
for generated in ('.check_process_vm.res', '.check_seccomp_filter.res', 'build.h'):
    (build / generated).unlink(missing_ok=True)
for loader in ('loader/loader', 'loader/loader-m32'):
    (build / loader).unlink(missing_ok=True)
config = root / 'talloc-config/default'
if not config.joinpath('config.h').is_file():
    raise SystemExit('Run configure_talloc.py successfully first.')
talloc = root / 'deps/talloc-2.5.0'
env = os.environ.copy()
env['PROOT_BUILD_NDK'] = str(ndk)
env['PROOT_BUILD_API'] = str(args.api)
env['MSYS2_ARG_CONV_EXCL'] = '*'
env['PATH'] = os.pathsep.join((str(bindir), str(args.shell.parent), str(tools), env['PATH']))
cc = tools / 'clang.exe'
common = ['--target=aarch64-linux-android' + str(args.api), '-std=gnu11', '-O2',
          '-ffile-prefix-map=' + source.as_posix() + '=proot',
          '-ffile-prefix-map=' + root.as_posix() + '=build',
          '-ffile-prefix-map=' + ndk.as_posix() + '=android-ndk']
logpath = root / 'compile.log'
with logpath.open('w', encoding='utf-8') as log:
    def run(cmd, cwd=root):
        result = subprocess.run([str(x) for x in cmd], cwd=cwd, env=env,
                                stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            log.flush()
            print(logpath.read_text(encoding='utf-8', errors='replace')[-10000:])
            raise SystemExit(result.returncode)
    print('Building talloc static archive...', flush=True)
    depflags = [*common, '-fPIC', '-ffunction-sections', '-fdata-sections', '-D__STDC_WANT_LIB_EXT1__=1',
         '-I' + config.as_posix(), '-I' + talloc.as_posix(),
         '-I' + (talloc / 'lib/replace').as_posix()]
    run([cc, *depflags, '-c', talloc / 'talloc.c', '-o', depbuild / 'talloc.o'])
    run([cc, *depflags, '-c', talloc / 'lib/replace/replace.c', '-o', depbuild / 'replace.o'])
    run([tools / 'llvm-ar.exe', 'rcs', depbuild / 'libtalloc.a', depbuild / 'talloc.o', depbuild / 'replace.o'])
    readelf = tools / 'llvm-readelf.exe'
    (bindir / 'readelf').write_text('#!/bin/sh\nexec ' + shlex.quote(readelf.as_posix()) + ' "$@"\n', encoding='utf-8', newline='\n')
    commit = subprocess.check_output(['git', '-c', 'core.bare=false', '-C', str(source), 'rev-parse', '--short=12', 'HEAD'], env=env, text=True).strip()
    env['CPPFLAGS'] = ' '.join((
        shlex.quote('-I' + talloc.as_posix()),
        '-DARG_MAX=131072', '-DVERSION=\\"' + commit + '\\"'))
    env['CFLAGS'] = ' '.join(shlex.quote(x) for x in common[1:]) + ' -fPIE'
    env['LDFLAGS'] = shlex.quote('-L' + depbuild.as_posix()) + ' -pie -Wl,--gc-sections,-z,max-page-size=16384'
    env['PROOT_UNBUNDLE_LOADER'] = '/proot-loader'
    env['LOADER_LDFLAGS'] = '-Wl,-z,max-page-size=16384'
    env['LOADER_LDFLAGS-m32'] = '-Wl,-z,max-page-size=16384'
    env.pop('PROOT_WITH_LIBANDROID_SHMEM', None)
    compiler = ' '.join(shlex.quote(x) for x in (Path(sys.executable).as_posix(), (root / 'ndk_cc.py').as_posix()))
    make = ndk / 'prebuilt/windows-x86_64/bin/make.exe'
    print('Building PRoot and its ARM64 / ARM32 loaders...', flush=True)
    make_command = [make, '-f', 'GNUmakefile', '-j8',
         'SHELL=' + args.shell.as_posix(), 'CC=' + compiler,
         'STRIP=' + (tools / 'llvm-strip.exe').as_posix(),
         'OBJDUMP=' + (tools / 'llvm-objdump.exe').as_posix(),
         'OBJCOPY=' + (tools / 'llvm-objcopy.exe').as_posix(),
         'CHECK_VERSION=', 'V=1']
    # Explicitly generate the platform probe header before the parallel build.
    run([*make_command, 'build.h'], cwd=build)
    run([*make_command, 'proot'], cwd=build)
print('BUILD SUCCESS', flush=True)
print('Outputs are in:', build)
