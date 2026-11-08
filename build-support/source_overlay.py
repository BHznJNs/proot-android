"""Prepare a disposable PRoot source tree with the Android project's extensions."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess


PORT_MAP = Path(__file__).resolve().parents[1] / 'extensions/port-map'


def tree_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob('*')):
        if path.is_file():
            digest.update(path.relative_to(directory).as_posix().encode('utf-8') + b'\0')
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def prepare_source(source: Path, build: Path, extension: Path = PORT_MAP) -> dict:
    source, build, extension = source.resolve(), build.resolve(), extension.resolve()
    if source == build or source in build.parents or build in source.parents:
        raise ValueError('The generated build tree must be separate from the PRoot source tree.')
    if not (source / 'GNUmakefile').is_file():
        raise ValueError('The PRoot source directory must contain GNUmakefile.')
    if (source / 'extension/port_switch/port_map.c').exists():
        raise ValueError('Use an unmodified Termux PRoot checkout; port mapping is injected by proot-android.')
    if build.exists():
        raise ValueError('Source preparation requires a fresh build directory.')
    source_hash = tree_digest(source)
    shutil.copytree(source, build)
    patch = extension / 'integration.patch'
    command = ['git', 'apply', '--no-index', '--whitespace=error-all']
    environment = os.environ.copy()
    # --no-index alone still discovers an enclosing repository and may skip
    # every patch outside its current subdirectory prefix with exit code zero.
    environment['GIT_CEILING_DIRECTORIES'] = str(build.parent)
    environment.pop('GIT_DIR', None)
    environment.pop('GIT_WORK_TREE', None)
    try:
        # Check every hunk before applying. Unsupported upstream changes must fail visibly.
        for options in (['--check'], []):
            subprocess.run([*command, *options, str(patch)], cwd=build, env=environment, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as error:
        raise RuntimeError('Port mapping integration patch does not match this PRoot source. '
                           'Review extensions/port-map/integration.patch for the selected upstream revision.\n'
                           + error.stderr.strip()) from error
    expected = {
        'GNUmakefile': b'extension/port_switch/port_map.o',
        'cli/proot.c': b'static int handle_option_port_map(',
        'cli/proot.h': b'.name = "--port-map"',
        'extension/extension.h': b'extern int port_map_callback(',
    }
    for name, marker in expected.items():
        if marker not in (build / name).read_bytes():
            raise RuntimeError('Port mapping integration was not applied to ' + name)
    shutil.copyfile(extension / 'port_map.c', build / 'extension/port_switch/port_map.c')
    return {
        'source_tree_sha256': source_hash,
        'port_map_sha256': hashlib.sha256((extension / 'port_map.c').read_bytes()).hexdigest(),
        'integration_patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
        'prepared_tree_sha256': tree_digest(build),
    }
