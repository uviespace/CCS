#!/usr/bin/env python
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '3.0')
from gi.repository import Gtk


class InfoBarDemo(Gtk.Window):
    def __init__(self, parent=None):
        Gtk.Window.__init__(self)
        try:
            self.set_screen(parent.get_screen())
        except AttributeError:
            self.connect('destroy', lambda *w: Gtk.main_quit())
        self.set_title(self.__class__.__name__)
        self.set_border_width(8)

        vb = Gtk.VBox()
        self.add(vb)

        bar = Gtk.InfoBar()
        vb.pack_start(bar, False, False, 0)
        bar.set_message_type(Gtk.MessageType.INFO)
        bar.get_content_area().pack_start(
                Gtk.Label("This is an info bar with message type GTK_MESSAGE_INFO"),
                False, False, 0)

        bar = Gtk.InfoBar()
        vb.pack_start(bar, False, False, 0)
        bar.set_message_type(Gtk.MessageType.WARNING)
        bar.get_content_area().pack_start(
                Gtk.Label("This is an info bar with message type GTK_MESSAGE_WARNING"),
                False, False, 0)

        bar = Gtk.InfoBar()
        bar.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        bar.connect("response", self._on_bar_response)
        vb.pack_start(bar, False, False, 0)
        bar.set_message_type(Gtk.MessageType.QUESTION)
        bar.get_content_area().pack_start(
                Gtk.Label("This is an info bar with message type GTK_MESSAGE_QUESTION"),
                False, False, 0)

        bar = Gtk.InfoBar()
        vb.pack_start(bar, False, False, 0)
        bar.set_message_type(Gtk.MessageType.ERROR)
        bar.get_content_area().pack_start(
                Gtk.Label("This is an info bar with message type GTK_MESSAGE_ERROR"),
                False, False, 0)

        bar = Gtk.InfoBar()
        vb.pack_start(bar, False, False, 0)
        bar.set_message_type(Gtk.MessageType.OTHER)
        bar.get_content_area().pack_start(
                Gtk.Label("This is an info bar with message type GTK_MESSAGE_OTHER"),
                False, False, 0)

        frame = Gtk.Frame()
        vb.pack_start(frame, False, False, 8)
        vb2 = Gtk.VBox(spacing=8)
        vb2.set_border_width(8)
        frame.add(vb2)
        vb2.pack_start(Gtk.Label("An example of different info bars"), False, False, 0)

        self.show_all()

    def _on_bar_response(self, button, response_id):
        dialog = Gtk.MessageDialog(
                        self,
                        0,
                        Gtk.MessageType.INFO,
                        Gtk.ButtonsType.OK,
                        "You clicked a button on an info bar")
        dialog.format_secondary_text("Your response has id %d" % response_id)
        dialog.run()
        dialog.destroy()


def main():
    InfoBarDemo()
    Gtk.main()


if __name__ == '__main__':
    main()
