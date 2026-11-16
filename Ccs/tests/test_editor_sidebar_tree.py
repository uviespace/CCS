"""File-tree regressions using GTK's model without requiring a display."""
from pathlib import Path
import sys
import tempfile
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from editor_sidebar import EditorSidebar
from editor_git import Change


class FileTreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'parent' / 'child' / 'nested').mkdir(parents=True)
        (self.root / 'parent' / 'child' / 'file.txt').write_text('test')
        self.tree = SimpleNamespace(directory=str(self.root), files=Gtk.TreeStore(str, str, str, bool),
                                    root_label=Mock(), status=Mock(), repo=None, changes=[])
        for name in ('populate_files', 'sync_directory', 'file_color', 'expand_folder'):
            setattr(self.tree, name, MethodType(getattr(EditorSidebar, name), self.tree))
        self.tree.populate_files()

    def find(self, name, parent=None):
        node = self.tree.files.iter_children(parent)
        while node is not None:
            if self.tree.files[node][0] == name:
                return node
            node = self.tree.files.iter_next(node)
        self.fail('Missing row: ' + name)

    def expand(self, node):
        self.tree.expand_folder(None, node, self.tree.files.get_path(node))

    def test_expansion_never_temporarily_removes_last_child(self):
        parent = self.find('parent')
        child_counts = []
        self.tree.files.connect('row-deleted', lambda *_: child_counts.append(
            self.tree.files.iter_n_children(parent)))
        self.expand(parent)
        self.assertTrue(child_counts)
        self.assertTrue(all(count > 0 for count in child_counts))
        self.find('child', parent)

    def test_nested_rows_survive_repeated_refresh_and_status_changes(self):
        parent = self.find('parent')
        self.expand(parent)
        child = self.find('child', parent)
        self.expand(child)
        nested = self.find('nested', child)
        self.expand(nested)
        refs = [Gtk.TreeRowReference.new(self.tree.files, self.tree.files.get_path(node))
                for node in (parent, child, nested)]
        self.tree.repo = SimpleNamespace(root=str(self.root))
        self.tree.changes = [Change('parent/child/file.txt', ' M')]
        for _ in range(3):
            self.tree.populate_files()
        self.assertTrue(all(ref.valid() for ref in refs))
        self.assertEqual(self.tree.files[parent][2], '#3584e4')
        self.assertEqual(self.tree.files[child][2], '#3584e4')
        self.assertEqual(len(self.tree._loaded_directories), 3)
        # Empty expanded folders pick up files on the next refresh as well.
        (self.root / 'parent' / 'child' / 'nested' / 'new.txt').write_text('new')
        self.tree.populate_files()
        self.find('new.txt', nested)
        self.assertTrue(all(ref.valid() for ref in refs))

    def test_added_and_deleted_files_do_not_replace_sibling_rows(self):
        parent = self.find('parent')
        self.expand(parent)
        child = self.find('child', parent)
        ref = Gtk.TreeRowReference.new(self.tree.files, self.tree.files.get_path(child))
        extra = self.root / 'parent' / 'aaa'
        extra.mkdir()
        self.tree.populate_files()
        self.assertTrue(ref.valid())
        self.assertEqual(self.tree.files[ref.get_path()][0], 'child')
        extra.rmdir()
        self.tree.populate_files()
        self.assertTrue(ref.valid())
        self.assertEqual(self.tree.files[ref.get_path()][0], 'child')


class GitCheckboxTests(unittest.TestCase):
    def test_checkbox_click_toggles_without_diff_or_file_open(self):
        sidebar = SimpleNamespace(busy=False, rows=[[False, ' M', 'file.txt', '']],
                                  repo=Mock(), show_diff=Mock(), open_path=Mock())
        view = Mock()
        checkbox = object()
        view.get_column.return_value = checkbox
        view.get_path_at_pos.return_value = ('0', checkbox, 2, 2)
        event = SimpleNamespace(button=1, x=5, y=5)
        EditorSidebar.toggle(sidebar, None, 0)
        self.assertTrue(sidebar.rows[0][0])
        self.assertFalse(EditorSidebar.git_button_released(sidebar, view, event))
        EditorSidebar.open_change(sidebar, view, 0, checkbox)
        sidebar.show_diff.assert_not_called()
        sidebar.open_path.assert_not_called()
        EditorSidebar.toggle(sidebar, None, 0)
        self.assertFalse(sidebar.rows[0][0])

    def test_filename_click_still_previews_diff(self):
        sidebar = SimpleNamespace(show_diff=Mock())
        view = Mock()
        view.get_column.return_value = object()
        view.get_path_at_pos.return_value = ('0', object(), 2, 2)
        event = SimpleNamespace(button=1, x=80, y=5)
        self.assertFalse(EditorSidebar.git_button_released(sidebar, view, event))
        sidebar.show_diff.assert_called_once_with(view.get_selection())

    def test_blank_space_and_right_click_do_not_open_diff(self):
        sidebar = SimpleNamespace(show_diff=Mock())
        view = Mock()
        view.get_path_at_pos.return_value = None
        for button in (1, 3):
            event = SimpleNamespace(button=button, x=80, y=500)
            self.assertFalse(EditorSidebar.git_button_released(sidebar, view, event))
        sidebar.show_diff.assert_not_called()


class PullIndicatorTests(unittest.TestCase):
    def test_incoming_commits_highlight_and_up_to_date_clears(self):
        sidebar = SimpleNamespace(pull_button=Mock())
        context = sidebar.pull_button.get_style_context.return_value
        EditorSidebar.update_pull_indicator(sidebar, 2)
        context.add_class.assert_called_once_with('incoming')
        self.assertIn('2 incoming', sidebar.pull_button.set_tooltip_text.call_args.args[0])
        EditorSidebar.update_pull_indicator(sidebar, 0)
        context.remove_class.assert_called_once_with('incoming')

    def test_failed_fetch_keeps_cached_indicator_and_explains_status(self):
        sidebar = SimpleNamespace(pull_button=Mock())
        EditorSidebar.update_pull_indicator(sidebar, 1, RuntimeError('offline'))
        sidebar.pull_button.get_style_context.return_value.add_class.assert_called_once_with('incoming')
        tooltip = sidebar.pull_button.set_tooltip_text.call_args.args[0]
        self.assertIn('last fetched state', tooltip)
        self.assertIn('offline', tooltip)


if __name__ == '__main__':
    unittest.main()
