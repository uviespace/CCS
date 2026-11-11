"""Context file actions run on temporary directories without a display."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from editor_file_menu import FileBrowserMenu, child_path


class FileMenuTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sidebar = SimpleNamespace(editor=Mock(), populate_files=Mock(), refresh=Mock(), open_path=Mock())
        self.menu = FileBrowserMenu.__new__(FileBrowserMenu)
        self.menu.sidebar = self.sidebar
        self.menu.ask_name = Mock()

    def test_create_file_and_directory(self):
        self.menu.ask_name.return_value = 'file.py'
        self.menu.create(str(self.root), False)
        self.assertTrue((self.root / 'file.py').is_file())
        self.sidebar.open_path.assert_called_once_with(str(self.root / 'file.py'))
        self.menu.ask_name.return_value = 'folder'
        self.menu.create(str(self.root), True)
        self.assertTrue((self.root / 'folder').is_dir())

    def test_create_does_not_overwrite_existing_file(self):
        path = self.root / 'file.py'
        path.write_text('keep me')
        self.menu.ask_name.return_value = path.name
        with self.assertRaises(FileExistsError):
            self.menu.create(str(self.root), False)
        self.assertEqual(path.read_text(), 'keep me')

    def test_name_cannot_escape_directory(self):
        for name in ('', '.', '..', '../outside', '/absolute', 'nested/file', 'null\0name'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                child_path(str(self.root), name)

    def test_rename_keeps_dirty_open_descendant_tab(self):
        source = self.root / 'folder'
        source.mkdir()
        (source / 'file.py').write_text('disk contents')
        self.menu.ask_name.return_value = 'renamed'
        page = Mock()
        label = Mock()
        label.get_tooltip_text.return_value = str(source / 'file.py')
        label.get_text.return_value = '*file.py'
        notebook = self.sidebar.editor.editor_notebook
        notebook.get_n_pages.return_value = 1
        notebook.get_nth_page.return_value = page
        notebook.get_tab_label.return_value.get_children.return_value = [label]
        self.menu.rename(str(source))
        destination = self.root / 'renamed' / 'file.py'
        self.assertEqual(destination.read_text(), 'disk contents')
        label.set_tooltip_text.assert_called_once_with(str(destination))
        label.set_text.assert_called_once_with('*file.py')
        self.sidebar.editor.file_watcher.track.assert_called_once_with(page, str(destination))

    def test_rename_cannot_overwrite_existing_destination(self):
        source, target = self.root / 'source', self.root / 'target'
        source.write_text('source')
        target.write_text('target')
        self.menu.ask_name.return_value = 'target'
        with self.assertRaises(GLib.Error):
            self.menu.rename(str(source))
        self.assertEqual(source.read_text(), 'source')
        self.assertEqual(target.read_text(), 'target')


if __name__ == '__main__':
    unittest.main()
