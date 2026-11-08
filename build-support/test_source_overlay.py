"""Host checks for the build-only extension boundary; no Android toolchain required."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from source_overlay import ANDROID_SESSION, PORT_MAP, prepare_source, tree_digest


class SourceOverlayTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        upstream = Path(os.environ.get('PROOT_TEST_SOURCE', Path(__file__).resolve().parents[2] / 'proot')) / 'src'
        self.source = self.directory / 'upstream'
        self.source.mkdir()
        for name in ('GNUmakefile', 'cli/cli.c', 'cli/proot.c', 'cli/proot.h', 'tracee/event.c',
                     'extension/extension.h', 'extension/port_switch/port_switch.c'):
            destination = self.source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(upstream / name, destination)
        self.build = self.directory / 'build'

    def test_injects_only_into_copy_and_records_inputs(self):
        before = tree_digest(self.source)
        result = prepare_source(self.source, self.build)
        self.assertEqual(before, tree_digest(self.source))
        self.assertEqual(before, result['source_tree_sha256'])
        self.assertEqual(tree_digest(self.build), result['prepared_tree_sha256'])
        self.assertFalse((self.source / 'extension/port_switch/port_map.c').exists())
        self.assertEqual((PORT_MAP / 'port_map.c').read_bytes(), (self.build / 'extension/port_switch/port_map.c').read_bytes())
        self.assertIn('--port-map', (self.build / 'cli/proot.h').read_text())
        self.assertIn('extension/port_switch/port_map.o', (self.build / 'GNUmakefile').read_text())
        self.assertEqual(tree_digest(ANDROID_SESSION), result['android_session_sha256'])
        self.assertFalse((self.source / 'extension/android_session').exists())
        self.assertEqual((ANDROID_SESSION / 'android_session.c').read_bytes(),
                         (self.build / 'extension/android_session/android_session.c').read_bytes())
        self.assertIn('android_session_tracer_ready();', (self.build / 'tracee/event.c').read_text())

    def test_rejects_incompatible_session_hooks_before_applying_any_patch(self):
        entry = self.source / 'cli/cli.c'
        entry.write_text(entry.read_text().replace('int main(', 'int upstream_main('))
        before = tree_digest(self.source)
        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            prepare_source(self.source, self.build)
        self.assertEqual(before, tree_digest(self.source))
        self.assertNotIn('--port-map', (self.build / 'cli/proot.h').read_text())

    def test_rejects_incompatible_upstream_without_changing_it(self):
        header = self.source / 'cli/proot.h'
        header.write_text(header.read_text().replace('handle_option_p', 'upstream_changed_option'))
        before = tree_digest(self.source)
        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            prepare_source(self.source, self.build)
        self.assertEqual(before, tree_digest(self.source))
        self.assertFalse((self.build / 'extension/port_switch/port_map.c').exists())
        self.assertNotIn('--port-map', (self.build / 'cli/proot.h').read_text())

    def test_injects_inside_an_enclosing_git_repository(self):
        repository = self.directory / 'wrapper-repository'
        repository.mkdir()
        subprocess.run(['git', 'init', '--quiet', str(repository)], check=True)
        parent = repository / 'build-support'
        parent.mkdir()
        build = parent / 'proot-arm64'
        prepare_source(self.source, build)
        self.assertIn('--port-map', (build / 'cli/proot.h').read_text())
        self.assertNotIn('--port-map', (self.source / 'cli/proot.h').read_text())

    def test_rejects_already_patched_source(self):
        target = self.source / 'extension/port_switch/port_map.c'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('already patched')
        with self.assertRaisesRegex(ValueError, 'unmodified'):
            prepare_source(self.source, self.build)
        self.assertFalse(self.build.exists())

    def test_rejects_existing_destination_and_overlapping_directories(self):
        self.build.mkdir()
        marker = self.build / 'stale.o'
        marker.write_text('old object')
        with self.assertRaisesRegex(ValueError, 'fresh'):
            prepare_source(self.source, self.build)
        self.assertTrue(marker.exists())
        for destination in (self.source, self.source / 'child', self.source.parent):
            with self.assertRaisesRegex(ValueError, 'separate'):
                prepare_source(self.source, destination)


if __name__ == '__main__':
    unittest.main()
