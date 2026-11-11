"""Context actions for the editor file tree."""
import os

from gi.repository import Gtk, Gdk, Gio, GLib


def child_path(directory, name):
    if not name or name in ('.', '..') or os.path.basename(name) != name or '\0' in name:
        raise ValueError('Enter a single file or folder name.')
    return os.path.join(directory, name)


class FileBrowserMenu:
    def __init__(self, sidebar):
        self.sidebar = sidebar
        sidebar.file_view.connect('button-press-event', self.clicked)
        sidebar.file_view.connect('popup-menu', self.keyboard_popup)

    def clicked(self, view, event):
        if event.button != 3:
            return False
        hit = view.get_path_at_pos(int(event.x), int(event.y))
        if hit:
            path, column, *_ = hit
            view.grab_focus()
            view.set_cursor(path, column, False)
            row = self.sidebar.files[path]
            if not row[1]:
                return True
            self.show(row[1], row[3], event, path)
        else:
            view.get_selection().unselect_all()
            self.show(self.sidebar.directory, True, event)
        return True

    def keyboard_popup(self, view):
        model, node = view.get_selection().get_selected()
        if node is not None and model[node][1]:
            self.show(model[node][1], model[node][3], tree_path=model.get_path(node))
        else:
            self.show(self.sidebar.directory, True)
        return True

    def show(self, path, folder, event=None, tree_path=None):
        menu = Gtk.Menu()
        def item(label, action):
            entry = Gtk.MenuItem(label=label)
            entry.connect('activate', lambda *_: self.perform(action))
            menu.append(entry)
        if folder and tree_path is not None:
            view = self.sidebar.file_view
            expanded = view.row_expanded(tree_path)
            item('Collapse' if expanded else 'Expand',
                 lambda: view.collapse_row(tree_path) if expanded else view.expand_row(tree_path, False))
        elif not folder:
            item('Open', lambda: self.sidebar.open_path(path))
        directory = path if folder else os.path.dirname(path)
        item('New file…', lambda: self.create(directory, False))
        item('New folder…', lambda: self.create(directory, True))
        menu.append(Gtk.SeparatorMenuItem())
        item('Copy path', lambda: Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(path, -1))
        if path != self.sidebar.directory:
            item('Rename…', lambda: self.rename(path))
            item('Move to Trash…', lambda: self.trash(path))
        menu.append(Gtk.SeparatorMenuItem())
        item('Refresh', self.sidebar.refresh)
        menu.show_all()
        self.menu = menu
        if event is not None:
            menu.popup_at_pointer(event)
        else:
            menu.popup_at_widget(self.sidebar.file_view, Gdk.Gravity.CENTER, Gdk.Gravity.CENTER, None)

    def perform(self, action):
        try:
            action()
        except (OSError, ValueError, GLib.Error) as error:
            # Gio errors and filesystem errors should be visible in the Files tab.
            dialog = Gtk.MessageDialog(transient_for=self.sidebar.editor, modal=True,
                                       message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CLOSE,
                                       text='File operation failed')
            dialog.format_secondary_text(str(error))
            dialog.run()
            dialog.destroy()

    def ask_name(self, title, initial=''):
        dialog = Gtk.Dialog(title=title, transient_for=self.sidebar.editor, modal=True)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        entry = Gtk.Entry(text=initial, activates_default=True)
        dialog.get_content_area().add(entry)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()
        entry.grab_focus()
        entry.select_region(0, -1)
        response = dialog.run()
        name = entry.get_text()
        dialog.destroy()
        return name if response == Gtk.ResponseType.OK else None

    def create(self, directory, folder):
        name = self.ask_name('New folder' if folder else 'New file')
        if name is None:
            return
        path = child_path(directory, name)
        if folder:
            os.mkdir(path)
        else:
            with open(path, 'x'):
                pass
        self.sidebar.populate_files()
        self.sidebar.refresh()
        if not folder:
            self.sidebar.open_path(path)

    def rename(self, path):
        name = self.ask_name('Rename', os.path.basename(path))
        if name is None:
            return
        destination = child_path(os.path.dirname(path), name)
        if destination == path:
            return
        # Gio's default move refuses an existing destination, including folders.
        Gio.File.new_for_path(path).move(Gio.File.new_for_path(destination), Gio.FileCopyFlags.NONE, None, None)
        self.retarget_tabs(path, destination)
        self.sidebar.populate_files()
        self.sidebar.refresh()

    def retarget_tabs(self, source, destination):
        editor = self.sidebar.editor
        notebook = editor.editor_notebook
        for index in range(notebook.get_n_pages()):
            page = notebook.get_nth_page(index)
            label = notebook.get_tab_label(page).get_children()[0]
            filename = label.get_tooltip_text()
            if not filename:
                continue
            filename = os.path.abspath(filename)
            if filename != source and not filename.startswith(source + os.sep):
                continue
            target = destination + filename[len(source):]
            dirty = label.get_text().startswith('*')
            label.set_tooltip_text(target)
            label.set_text(('*' if dirty else '') + os.path.basename(target))
            editor.file_watcher.track(page, target)

    def trash(self, path):
        dialog = Gtk.MessageDialog(transient_for=self.sidebar.editor, modal=True,
                                   message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.NONE,
                                   text='Move to Trash?')
        dialog.format_secondary_text(path)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, 'Move to Trash', Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT:
            return
        # Never fall back to permanent deletion if trash is unavailable.
        Gio.File.new_for_path(path).trash(None)
        self.sidebar.populate_files()
        self.sidebar.refresh()
