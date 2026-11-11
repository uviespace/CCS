"""Exercise reloads with a real source buffer and headless editor doubles."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '3.0')
from gi.repository import Gtk, GtkSource

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from editor_file_watch import OpenFileWatcher


class FileWatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'file.py'
        self.path.write_text('original\n')
        self.buffer = GtkSource.Buffer()
        self.buffer.set_text('original\n')
        self.label = Mock()
        self.label.get_text.return_value = 'file.py'
        self.label.set_text.side_effect = lambda text: setattr(self.label.get_text, 'return_value', text)
        self.page = Mock()
        self.page.get_child.return_value.get_buffer.return_value = self.buffer
        notebook = Mock()
        notebook.page_num.return_value = 0
        notebook.get_tab_label.return_value.get_children.return_value = [self.label]
        self.editor = SimpleNamespace(editor_notebook=notebook, logger=Mock())
        self.watcher = OpenFileWatcher.__new__(OpenFileWatcher)
        self.watcher.editor = self.editor
        self.watcher.documents = {}
        self.watcher.track(self.page, str(self.path))

    def text(self):
        return self.buffer.get_text(*self.buffer.get_bounds(), True)

    def test_external_change_reloads_clean_buffer(self):
        self.path.write_text('external change\n')
        self.watcher.check()
        self.assertEqual(self.text(), 'external change\n')
        self.assertEqual(self.label.get_text(), 'file.py')
        self.assertFalse(self.buffer.can_undo())

    def test_unsaved_edits_are_kept_and_prompted_once(self):
        self.buffer.set_text('local edit')
        self.label.get_text.return_value = '*file.py'
        self.path.write_text('external change\n')
        with patch('editor_file_watch.Gtk.MessageDialog') as dialog:
            dialog.return_value.run.return_value = Gtk.ResponseType.CANCEL
            self.watcher.check()
            self.watcher.check()
            self.assertEqual(dialog.call_count, 1)
        self.assertEqual(self.text(), 'local edit')

    def test_explicit_reload_replaces_unsaved_edits(self):
        self.buffer.set_text('local edit')
        self.label.get_text.return_value = '*file.py'
        self.path.write_text('external change\n')
        with patch('editor_file_watch.Gtk.MessageDialog') as dialog:
            dialog.return_value.run.return_value = Gtk.ResponseType.ACCEPT
            self.watcher.check()
        self.assertEqual(self.text(), 'external change\n')
        self.assertEqual(self.label.get_text(), 'file.py')

    def test_deleted_file_kept_and_marked_unsaved(self):
        self.path.unlink()
        self.watcher.check()
        self.assertEqual(self.text(), 'original\n')
        self.assertEqual(self.label.get_text(), '*file.py')

    def test_closed_tabs_are_removed(self):
        self.editor.editor_notebook.page_num.return_value = -1
        self.watcher.check()
        self.assertEqual(self.watcher.documents, {})


if __name__ == '__main__':
    unittest.main()
