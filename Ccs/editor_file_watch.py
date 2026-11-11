"""Reload externally changed editor documents without discarding local edits."""
import os

from gi.repository import Gtk, GLib


class OpenFileWatcher:
    def __init__(self, editor):
        self.editor = editor
        self.documents = {}
        self.timer = GLib.timeout_add_seconds(1, self.check)
        editor.connect('destroy', self.close)

    def close(self, *_):
        GLib.source_remove(self.timer)
        self.documents.clear()

    @staticmethod
    def fingerprint(path):
        stat = os.stat(path)
        return stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino

    def track(self, page, filename):
        path = os.path.abspath(filename)
        try:
            stamp = self.fingerprint(path)
        except OSError:
            stamp = None
        self.documents[page] = (path, stamp)

    def check(self):
        # Wait until an in-app checkout/pull has finished writing the work tree.
        sidebar = getattr(self.editor, 'editor_sidebar', None)
        if sidebar is not None and sidebar.busy:
            return True
        notebook = self.editor.editor_notebook
        for page, (path, previous) in list(self.documents.items()):
            if notebook.page_num(page) < 0:
                del self.documents[page]
                continue
            label = notebook.get_tab_label(page).get_children()[0]
            try:
                stamp = self.fingerprint(path)
                if stamp == previous:
                    continue
                with open(path, 'r') as stream:
                    text = stream.read()
            except (OSError, UnicodeError) as error:
                # Keep the document recoverable if a checkout removes the file.
                if previous is not None:
                    self.documents[page] = (path, None)
                    if not label.get_text().startswith('*'):
                        label.set_text('*' + label.get_text())
                    self.editor.logger.warning('Open file unavailable: %s: %s', path, error)
                continue
            self.documents[page] = (path, stamp)
            buffer = page.get_child().get_buffer()
            if text == buffer.get_text(*buffer.get_bounds(), True):
                continue
            if label.get_text().startswith('*'):
                dialog = Gtk.MessageDialog(transient_for=self.editor, modal=True,
                                           message_type=Gtk.MessageType.WARNING,
                                           buttons=Gtk.ButtonsType.NONE,
                                           text='File changed on disk: ' + path)
                dialog.format_secondary_text('This tab has unsaved edits. Reload discards those edits; keep retains them in the editor.')
                dialog.add_button('Keep my edits', Gtk.ResponseType.CANCEL)
                dialog.add_button('Reload from disk', Gtk.ResponseType.ACCEPT)
                dialog.set_default_response(Gtk.ResponseType.CANCEL)
                response = dialog.run()
                dialog.destroy()
                if response != Gtk.ResponseType.ACCEPT:
                    continue
            offset = buffer.get_iter_at_mark(buffer.get_insert()).get_offset()
            buffer.begin_not_undoable_action()
            try:
                buffer.set_text(text)
            finally:
                buffer.end_not_undoable_action()
            buffer.place_cursor(buffer.get_iter_at_offset(min(offset, buffer.get_char_count())))
            buffer.set_modified(False)
            # Existing changed handlers mark the tab; a disk reload is clean.
            label.set_text(os.path.basename(path))
        return True
