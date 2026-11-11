"""Git command adapter. No GTK dependency; paths are always literal pathspecs."""
import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Change:
    path: str
    status: str
    original: str = None

    @property
    def color(self):
        if self.status == '??':
            return '#d94b4b'
        if 'A' in self.status:
            return '#31964b'
        return '#3584e4'


class Repository:
    def __init__(self, directory):
        self.root = self.run_at(directory, 'rev-parse', '--show-toplevel').strip()

    @staticmethod
    def run_at(directory, *args):
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_LITERAL_PATHSPECS='1')
        result = subprocess.run(['git', '-C', directory, *args], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=120)
        if result.returncode:
            raise RuntimeError(os.fsdecode(result.stderr).strip() or 'Git command failed')
        return os.fsdecode(result.stdout)

    def run(self, *args):
        return self.run_at(self.root, *args)

    def changes(self):
        fields = self.run('status', '--porcelain=v1', '-z', '--untracked-files=all').split('\0')
        changes = []
        i = 0
        while i < len(fields) and fields[i]:
            status, path = fields[i][:2], fields[i][3:]
            i += 1
            original = None
            if 'R' in status or 'C' in status:
                original = fields[i]
                i += 1
            changes.append(Change(path, status, original))
        return changes

    def branches(self):
        return self.run('for-each-ref', '--format=%(refname:short)', 'refs/heads/').splitlines()

    def current_branch(self):
        return self.run('branch', '--show-current').strip()

    def switch_branch(self, name, create=False):
        if not name or name.startswith('-'):
            raise RuntimeError('Enter a valid branch name.')
        self.run('check-ref-format', '--branch', name)
        return self.run('switch', '-c', name) if create else self.run('switch', '--', name)

    def diff(self, change):
        if change.status == '??':
            with open(os.path.join(self.root, change.path), 'rb') as stream:
                data = stream.read(1024 * 1024)
            if b'\0' in data:
                return 'Binary untracked file'
            return 'Untracked file: ' + change.path + '\n' + ''.join(
                '+' + line for line in data.decode('utf-8', errors='replace').splitlines(True))
        paths = [change.path] + ([change.original] if change.original else [])
        staged = self.run('diff', '--no-ext-diff', '--no-textconv', '--cached', '--', *paths)
        working = self.run('diff', '--no-ext-diff', '--no-textconv', '--', *paths)
        return ('STAGED\n' + staged if staged else '') + ('\nWORKING TREE\n' + working if working else '') or 'No textual changes'

    def stage(self, changes):
        paths = [p for change in changes for p in (change.path, change.original) if p]
        if not paths:
            raise RuntimeError('Select at least one file.')
        tracked = set(self.run('ls-files', '-z').split('\0'))
        # Already staged deletions/rename sources no longer exist in the index.
        paths = [p for p in paths if p in tracked or os.path.lexists(os.path.join(self.root, p))]
        if paths:
            self.run('add', '--all', '--', *paths)

    def commit(self, changes, message):
        if not message.strip():
            raise RuntimeError('Enter a commit message.')
        self.stage(changes)
        paths = [p for change in changes for p in (change.path, change.original) if p]
        # --only prevents unrelated files already in the index entering this commit.
        return self.run('commit', '--only', '-m', message, '--', *paths)
