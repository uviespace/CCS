"""File and Git sidebar for the CCS GTK editor."""
import os
from concurrent.futures import ThreadPoolExecutor

from gi.repository import Gtk, Gdk, GLib, Pango
from editor_git import Repository
from editor_file_menu import FileBrowserMenu


class EditorSidebar(Gtk.Notebook):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.directory = os.getcwd()
        self.repo = None
        self.changes = []
        self.busy = False
        self.closed = False
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.set_size_request(240, -1)
        files = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append_page(files, Gtk.Label(label='Files'))
        path_bar = Gtk.Box(spacing=4)
        files.pack_start(path_bar, False, False, 0)
        self.root_label = Gtk.Label(xalign=0)
        self.root_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        path_bar.pack_start(self.root_label, True, True, 0)
        refresh = Gtk.Button.new_from_icon_name('view-refresh-symbolic', Gtk.IconSize.BUTTON)
        refresh.set_relief(Gtk.ReliefStyle.NONE)
        refresh.set_tooltip_text('Refresh files')
        refresh.get_accessible().set_name('Refresh files')
        refresh.connect('clicked', lambda *_: self.refresh())
        path_bar.pack_end(refresh, False, False, 0)
        self.files = Gtk.TreeStore(str, str, str, bool)
        self.file_view = Gtk.TreeView(model=self.files)
        self.file_view.append_column(Gtk.TreeViewColumn('Project files', Gtk.CellRendererText(), text=0, foreground=2))
        self.file_view.connect('row-expanded', self.expand_folder)
        self.file_view.connect('row-activated', self.open_file)
        self.file_menu = FileBrowserMenu(self)
        self.scroll(files, self.file_view)
        git = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append_page(git, Gtk.Label(label='Git'))
        branch_bar = Gtk.Box(spacing=4)
        git.pack_start(branch_bar, False, False, 0)
        self.branch = Gtk.ComboBoxText()
        self._updating_branches = False
        self.branch.connect('changed', self.switch_branch)
        branch_bar.pack_start(self.branch, True, True, 0)
        self.button(branch_bar, 'New branch…', self.create_branch)
        bar = Gtk.Box(spacing=4)
        git.pack_start(bar, False, False, 0)
        self.button(bar, 'Pull', lambda *_: self.operation(lambda: self.repo.run('pull', '--ff-only')))
        self.button(bar, 'Push', lambda *_: self.operation(lambda: self.repo.run('push')))
        self.button(bar, 'Refresh', lambda *_: self.refresh())
        self.status = Gtk.Label(label='Loading…', xalign=0)
        self.status.set_line_wrap(True)
        git.pack_start(self.status, False, False, 0)
        self.rows = Gtk.ListStore(bool, str, str, str)
        view = Gtk.TreeView(model=self.rows)
        toggle = Gtk.CellRendererToggle()
        toggle.connect('toggled', self.toggle)
        view.append_column(Gtk.TreeViewColumn('Include', toggle, active=0))
        view.append_column(Gtk.TreeViewColumn('State', Gtk.CellRendererText(), text=1))
        view.append_column(Gtk.TreeViewColumn('File', Gtk.CellRendererText(), text=2, foreground=3))
        view.get_selection().connect('changed', self.show_diff)
        view.connect('row-activated', self.open_change)
        self.scroll(git, view)
        self.message = Gtk.Entry()
        self.message.set_placeholder_text('Commit message')
        git.pack_start(self.message, False, False, 0)
        git.pack_start(Gtk.Label(label='Save editor files before staging or committing.', xalign=0), False, False, 0)
        bar = Gtk.Box(spacing=4)
        git.pack_start(bar, False, False, 0)
        self.button(bar, 'Stage selected', lambda *_: self.stage())
        self.button(bar, 'Commit selected', lambda *_: self.commit())
        self.diff_view = Gtk.TextView(editable=False, monospace=True)
        self.diff_view.get_buffer().create_tag('addition', foreground='#31964b')
        self.diff_view.get_buffer().create_tag('deletion', foreground='#d94b4b')
        self.diff_window = None
        accel = Gtk.AccelGroup()
        editor.add_accel_group(accel)
        accel.connect(Gdk.KEY_k, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE, self.git_shortcut)
        editor.connect('destroy', self.destroyed)
        self.timer = GLib.timeout_add_seconds(5, self.periodic_refresh)
        self.refresh()

    @staticmethod
    def button(box, label, callback):
        button = Gtk.Button(label=label)
        button.connect('clicked', callback)
        box.pack_start(button, False, False, 0)
        return button

    @staticmethod
    def scroll(box, child):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(child)
        box.pack_start(scroll, True, True, 0)

    def git_shortcut(self, *_):
        self.set_current_page(1)
        self.message.grab_focus()
        return True

    def destroyed(self, *_):
        self.closed = True
        GLib.source_remove(self.timer)
        if self.diff_window:
            self.diff_window.destroy()
        self.executor.shutdown(wait=False)

    def submit(self, work, done):
        if self.busy:
            return
        self.busy = True
        future = self.executor.submit(work)
        def complete():
            self.busy = False
            if self.closed:
                return False
            try:
                value = future.result()
            except Exception as error:
                self.status.set_text(str(error))
            else:
                done(value)
            return False
        future.add_done_callback(lambda _: GLib.idle_add(complete))

    def choose_folder(self, *_):
        if self.busy:
            return
        dialog = Gtk.FileChooserDialog(title='Open project folder', transient_for=self.editor,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            self.directory = dialog.get_filename()
            self.repo = None
            self.changes = []
            self.populate_files()
            self.refresh()
        dialog.destroy()

    def periodic_refresh(self):
        if not self.busy:
            self.refresh()
        return not self.closed

    def refresh(self):
        directory = self.directory
        def load():
            try:
                repo = Repository(directory)
            except RuntimeError as error:
                if 'not a git repository' in str(error):
                    return None, [], 'This folder is not a Git repository.', [], ''
                raise
            return (repo, repo.changes(), repo.run('status', '--short', '--branch').splitlines()[0],
                    repo.branches(), repo.current_branch())
        self.submit(load, self.loaded)

    def loaded(self, result):
        self.repo, self.changes, status, branches, current = result
        self._current_branch = current
        self._updating_branches = True
        try:
            self.branch.remove_all()
            for name in branches:
                self.branch.append(name, name)
            self.branch.set_active_id(current)
        finally:
            self._updating_branches = False
        self.branch.set_tooltip_text('Current branch: ' + (current or 'detached HEAD'))
        selected = {row[2] for row in self.rows if row[0]}
        self.rows.clear()
        for change in self.changes:
            self.rows.append([change.path in selected, change.status, change.path, change.color])
        self.status.set_text(status)
        self.populate_files()

    def populate_files(self):
        # Update existing rows instead of rebuilding the model: GTK then retains
        # expansion, selection, and scroll position during background refreshes.
        if getattr(self, '_tree_directory', None) != self.directory:
            self.files.clear()
            self._loaded_directories = set()
            self._tree_directory = self.directory
        self.root_label.set_text(self.directory)
        self.root_label.set_tooltip_text(self.directory)
        self.sync_directory(self.directory, None)

    def file_color(self, path, folder):
        if self.repo:
            relative = os.path.relpath(path, self.repo.root)
            for change in self.changes:
                if change.path == relative or (folder and change.path.startswith(relative + '/')):
                    return change.color
        return '#888888'

    def sync_directory(self, directory, parent):
        try:
            with os.scandir(directory) as scan:
                entries = sorted((entry for entry in scan if entry.name != '.git'),
                                 key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))
        except OSError as error:
            self.status.set_text(str(error))
            return
        wanted = {entry.path: entry.is_dir(follow_symlinks=False) for entry in entries}
        existing = {}
        placeholders = []
        child = self.files.iter_children(parent)
        while child is not None:
            following = self.files.iter_next(child)
            path = self.files[child][1]
            if not path:
                placeholders.append(child)
            elif path not in wanted or self.files[child][3] != wanted[path]:
                self.files.remove(child)
                self._loaded_directories.difference_update(
                    p for p in tuple(self._loaded_directories)
                    if p == path or p.startswith(path + os.sep))
            else:
                existing[path] = child
            child = following
        for position, entry in enumerate(entries):
            folder = wanted[entry.path]
            color = self.file_color(entry.path, folder)
            node = existing.get(entry.path)
            if node is None:
                sibling = self.files.iter_nth_child(parent, position)
                node = self.files.insert_before(parent, sibling,
                                               [entry.name, entry.path, color, folder])
                if folder:
                    self.files.append(node, ['', '', color, False])
            elif self.files[node][2] != color:
                self.files[node][2] = color
            if folder and entry.path in self._loaded_directories:
                self.sync_directory(entry.path, node)
        # Keep the placeholder until real children exist. Removing the last child
        # during row-expanded makes GTK collapse the parent immediately.
        for placeholder in placeholders:
            self.files.remove(placeholder)

    def expand_folder(self, view, node, path):
        directory = self.files[node][1]
        if directory not in self._loaded_directories:
            self._loaded_directories.add(directory)
            self.sync_directory(directory, node)

    def open_path(self, path):
        try:
            self.editor.open_file(path)
        except (OSError, UnicodeError) as error:
            self.status.set_text(str(error))

    def open_file(self, view, path, column):
        row = self.files[path]
        if not row[3] and row[1]:
            self.open_path(row[1])
        elif row[3]:
            view.expand_row(path, False)

    def open_change(self, view, path, column):
        if self.repo:
            self.open_path(os.path.join(self.repo.root, self.rows[path][2]))

    def toggle(self, renderer, path):
        if not self.busy:
            self.rows[path][0] = not self.rows[path][0]

    def selected(self):
        paths = {row[2] for row in self.rows if row[0]}
        return [change for change in self.changes if change.path in paths]

    def operation(self, work, clear_message=False):
        if not self.repo or self.busy:
            return
        self.status.set_text('Running Git operation…')
        def done(output):
            if clear_message:
                self.message.set_text('')
            self.refresh()
        self.submit(work, done)

    def stage(self):
        changes = self.selected()
        self.operation(lambda: self.repo.stage(changes))

    def switch_branch(self, *_):
        if self._updating_branches:
            return
        name = self.branch.get_active_id()
        if name and name != self._current_branch and not self.busy:
            self.operation(lambda: self.repo.switch_branch(name))

    def create_branch(self, *_):
        if not self.repo or self.busy:
            return
        dialog = Gtk.Dialog(title='Create and switch to branch', transient_for=self.editor, modal=True)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, 'Create', Gtk.ResponseType.OK)
        entry = Gtk.Entry()
        entry.set_placeholder_text('New branch name (from current HEAD)')
        entry.set_activates_default(True)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.get_content_area().add(entry)
        dialog.show_all()
        response = dialog.run()
        name = entry.get_text().strip()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.operation(lambda: self.repo.switch_branch(name, create=True))

    def commit(self):
        changes, message = self.selected(), self.message.get_text()
        self.operation(lambda: self.repo.commit(changes, message), clear_message=True)

    def show_diff(self, selection):
        model, node = selection.get_selected()
        if node is None or not self.repo or self.busy:
            return
        change = next((c for c in self.changes if c.path == model[node][2]), None)
        if change:
            self.submit(lambda: self.repo.diff(change), lambda text: self.display_diff(change.path, text))

    def display_diff(self, path, text):
        if self.diff_window is None:
            self.diff_window = Gtk.Window(transient_for=self.editor, title='Diff')
            self.diff_window.set_default_size(850, 600)
            scroll = Gtk.ScrolledWindow()
            scroll.add(self.diff_view)
            self.diff_window.add(scroll)
            self.diff_window.connect('delete-event', lambda window, event: window.hide() or True)
        self.diff_window.set_title('Diff — ' + path)
        buffer = self.diff_view.get_buffer()
        buffer.set_text('')
        for line in text.splitlines(True):
            tag = 'addition' if line.startswith('+') else 'deletion' if line.startswith('-') else None
            if tag:
                buffer.insert_with_tags_by_name(buffer.get_end_iter(), line, tag)
            else:
                buffer.insert(buffer.get_end_iter(), line)
        self.diff_window.show_all()
