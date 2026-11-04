import os
from pathlib import Path
import subprocess
import sys
import runpy
import shutil

if len(sys.argv) > 1 and sys.argv[1] == '--run-waf':
    shell = os.environ['PROOT_BUILD_SHELL']
    original_popen = subprocess.Popen
    class ShellPopen(original_popen):
        def __init__(self, args, *more, **kwargs):
            if isinstance(args, (list, tuple)) and args and args[0] == '/bin/sh':
                args = [shell, *args[1:]]
            super().__init__(args, *more, **kwargs)
    subprocess.Popen = ShellPopen
    # Waf creates host-side directory links. NTFS junctions need no developer
    # mode or elevated symlink privilege; this does not change target probes.
    def host_link(src, dst, target_is_directory=False, **kwargs):
        target = (Path(dst).parent / src).resolve()
        if target.is_dir():
            subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(Path(dst).resolve()), str(target)],
                           check=True, stdout=subprocess.DEVNULL)
        else:
            shutil.copy2(target, dst)
    os.symlink = host_link
    sys.argv = ['buildtools/bin/waf', *sys.argv[2:]]
    runpy.run_path('buildtools/bin/waf', run_name='__main__')
    raise SystemExit

root = Path(__file__).resolve().parent
source = root / 'deps' / 'talloc-2.5.0'
ndk = Path(sys.argv[1]).resolve()
tools = ndk / 'toolchains/llvm/prebuilt/windows-x86_64/bin'
answers = root / 'talloc-cross-answers.txt'
answers.write_text('''Checking uname sysname type: "Linux"
Checking uname machine type: "aarch64"
Checking uname release type: "dontcare"
Checking uname version type: "dontcare"
Checking simple C program: OK
building library support: OK
Checking for large file support: OK
Checking for -D_FILE_OFFSET_BITS=64: OK
Checking for WORDS_BIGENDIAN: NO
Checking for C99 vsnprintf: OK
Checking for HAVE_SECURE_MKSTEMP: OK
rpath library support: OK
-Wl,--version-script support: FAIL
Checking correct behavior of strtoll: OK
Checking correct behavior of strptime: OK
Checking for HAVE_IFACE_GETIFADDRS: OK
Checking for HAVE_IFACE_IFCONF: OK
Checking for HAVE_IFACE_IFREQ: OK
Checking getconf LFS_CFLAGS: OK
Checking for large file support without additional flags: OK
Checking for working strptime: OK
Checking for HAVE_SHARED_MMAP: OK
Checking for HAVE_MREMAP: OK
Checking for HAVE_INCOHERENT_MMAP: OK
Checking getconf large file support flags work: OK
''', encoding='utf-8')
env = os.environ.copy()
env['PYTHONHASHSEED'] = '1'
env['CC'] = tools.joinpath('clang.exe').as_posix() + ' --target=aarch64-linux-android28'
env['AR'] = tools.joinpath('llvm-ar.exe').as_posix()
env['CFLAGS'] = '-O2 -fPIC'
env['LINKFLAGS'] = '-Wl,-z,max-page-size=16384'
env['PATH'] = str(tools) + os.pathsep + env['PATH']
env['PROOT_BUILD_SHELL'] = sys.argv[2]
cmd = [sys.executable, str(Path(__file__).resolve()), '--run-waf', 'configure',
       '--out=' + str(root / 'talloc-config'), '--prefix=/unused',
       '--check-c-compiler=clang', '--disable-rpath', '--disable-python',
       '--disable-symbol-versions', '--cross-compile', '--cross-answers=' + str(answers)]
with (root / 'talloc-configure.log').open('w', encoding='utf-8') as log:
    proc = subprocess.run(cmd, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
print('configure exit:', proc.returncode)
print((root / 'talloc-configure.log').read_text(encoding='utf-8', errors='replace')[-7000:])
sys.exit(proc.returncode)
