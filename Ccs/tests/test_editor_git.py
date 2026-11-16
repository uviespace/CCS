"""Integration tests using disposable repositories; no configured remotes required."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from editor_git import Repository


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.com')
        self.write('one', 'original\n')
        self.write('two', 'original\n')
        self.git('add', '.')
        self.git('commit', '-m', 'initial')
        self.repo = Repository(str(self.root))

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE).decode()

    def write(self, name, text):
        (self.root / name).write_text(text)

    def test_selected_commit_preserves_unrelated_index(self):
        self.write('one', 'changed\n')
        self.write('two', 'staged elsewhere\n')
        self.git('add', 'two')
        changes = [c for c in self.repo.changes() if c.path == 'one']
        self.repo.commit(changes, 'selected')
        self.assertEqual(self.git('show', '--format=', '--name-only', 'HEAD').strip(), 'one')
        self.assertEqual(self.git('diff', '--cached', '--name-only').strip(), 'two')

    def test_literal_untracked_filename_and_diff(self):
        name = 'new \n [abc].txt'
        self.write(name, 'hello\n')
        change, = self.repo.changes()
        self.assertEqual(change.path, name)
        self.assertEqual(change.color, '#d94b4b')
        self.assertIn('+hello', self.repo.diff(change))
        self.repo.stage([change])
        self.assertEqual(self.repo.changes()[0].color, '#31964b')
        self.repo.commit(self.repo.changes(), 'new file')
        self.assertEqual(self.repo.changes(), [])

    def test_rename_and_deletion(self):
        self.git('mv', 'one', 'renamed')
        (self.root / 'two').unlink()
        changes = self.repo.changes()
        renamed = next(c for c in changes if c.path == 'renamed')
        self.assertEqual(renamed.original, 'one')
        self.assertIn('STAGED', self.repo.diff(renamed))
        self.repo.commit(changes, 'rename and delete')
        self.assertEqual(self.repo.changes(), [])

    def test_validation(self):
        with self.assertRaises(RuntimeError):
            self.repo.stage([])
        with self.assertRaises(RuntimeError):
            self.repo.commit(self.repo.changes(), '  ')

    def test_create_and_switch_branch_updates_worktree(self):
        original = self.repo.current_branch()
        self.repo.switch_branch('feature/test', create=True)
        self.assertIn('feature/test', self.repo.branches())
        self.write('one', 'branch version\n')
        self.repo.commit(self.repo.changes(), 'branch edit')
        self.repo.switch_branch(original)
        self.assertEqual((self.root / 'one').read_text(), 'original\n')
        self.repo.switch_branch('feature/test')
        self.assertEqual((self.root / 'one').read_text(), 'branch version\n')
        with self.assertRaises(RuntimeError):
            self.repo.switch_branch('--discard-changes')
        with self.assertRaises(RuntimeError):
            self.repo.switch_branch('invalid branch', create=True)

    def test_no_upstream_and_detached_head_have_no_incoming_commits(self):
        self.assertEqual(self.repo.fetch_incoming(), 0)
        self.git('checkout', '--detach')
        self.assertEqual(self.repo.fetch_incoming(), 0)

    def test_remote_fetch_detects_incoming_without_changing_worktree(self):
        remote = self.root / 'remote.git'
        peer = self.root / 'peer'
        self.git('init', '--bare', str(remote))
        self.git('remote', 'add', 'origin', str(remote))
        branch = self.repo.current_branch()
        self.git('push', '-u', 'origin', branch)
        self.git('clone', str(remote), str(peer))
        def other(*args):
            return subprocess.check_output(['git', '-C', str(peer), *args], stderr=subprocess.PIPE)
        other('config', 'user.name', 'Peer')
        other('config', 'user.email', 'peer@example.com')
        self.assertEqual(self.repo.fetch_incoming(), 0)
        (peer / 'one').write_text('remote version\n')
        other('add', 'one')
        other('commit', '-m', 'remote edit')
        other('push')
        head = self.git('rev-parse', 'HEAD')
        self.assertEqual(self.repo.incoming_count(), 0)  # cached remote state
        self.assertEqual(self.repo.fetch_incoming(), 1)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual((self.root / 'one').read_text(), 'original\n')
        self.git('merge', '--ff-only', '@{upstream}')
        self.assertEqual(self.repo.incoming_count(), 0)
        self.write('one', 'local ahead\n')
        self.repo.commit([c for c in self.repo.changes() if c.path == 'one'], 'local edit')
        self.assertEqual(self.repo.incoming_count(), 0)


if __name__ == '__main__':
    unittest.main()
