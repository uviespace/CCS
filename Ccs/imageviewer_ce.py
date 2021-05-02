#!/usr/bin/env python3

import sys
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

import matplotlib

matplotlib.use('Gtk3Cairo')
from matplotlib.pyplot import colormaps
from matplotlib.colors import Normalize, LogNorm, PowerNorm
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
# from matplotlib.backends.backend_gtk3cairo import FigureCanvasGTK3Cairo as FigureCanvas
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3 as NavigationToolbar

import numpy as np
import astropy.io.fits as pyfits
import configparser
import glob
import threading
import multiprocessing
import time
from event_storm_squasher import delayed


# from event_storm_squasher import delayed


class ImageViewer(Gtk.Window):
    default_config = 'egse.cfg'
    pixzoom = 10
    cmap = 'viridis'
    normalisations = {'LINEAR': Normalize, 'LOG': LogNorm, 'POWER': PowerNorm, 'SQRT': PowerNorm}

    window_sizes = {'CCD_FULL': (1076, 1033), 'CCD_WIN_EXPOS': (200, 200),
                    'CCD_WIN_LSM': (200, 28), 'CCD_WIN_RSM': (200, 24), 'CCD_WIN_TM': (9, 200)}

    refresh_interval = 1
    histrange = (0, 2 ** 16 - 1)
    image_interpolation = 'none'

    def __init__(self, cfg=None, directory="./", prefix=""):
        Gtk.Window.__init__(self, title="Image Viewer (watching {}*)".format(directory + prefix), default_height=900,
                            default_width=1200)
        self.set_border_width(5)
        self.set_resizable(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        if cfg is not None:
            self.cfg = cfg
        else:
            self.cfg = configparser.ConfigParser()
            self.cfg.read(self.default_config)
            self.cfg.source = self.default_config

        self.prefix = prefix
        self.dir_watcher_active = False
        self.autoscroll = 0
        self.slice_count = 2

        self.fixed_cuts = False
        self.keep_regions = False

        self.region_size = 20
        self.region_shape = 'square'
        self.region_cursor = None
        self.region_stats = {}
        self.region_store = {}

        self.watched_directory = directory if directory.endswith('/') else directory + '/'
        self.instore = multiprocessing.Manager().list()

        self.fileview = self.create_fileview()
        self.headerview = self.create_headerview()
        self.headerbuffer = self.headerview.get_child().get_buffer()
        self.start_dir_watch(self.watched_directory)
        self.layer_slice = 0
        self.scaled = False

        if len(self.instore) == 0:
            self.loaded_fits = None
        else:
            self.load_fits(self.instore[0])
        self.canvas = self.create_canvas()
        # self.statbar = NavigationToolbar(self.canvas, self)
        self.statbar = NavBar(self.canvas, self)
        self.slider = self.create_slider()

        clippingbox = Gtk.VBox()
        self.histcanvas = self.create_histogram()
        cutsbox = Gtk.HBox()
        self.minbox, self.maxbox = Gtk.Entry(xalign=1), Gtk.Entry(xalign=1)
        self.vmin, self.vmax = 0, 2 ** 24 - 1
        self.minline, self.maxline = None, None
        self.minbox.connect('activate', self.update_cuts)
        self.maxbox.connect('activate', self.update_cuts)
        self.minbox.set_text('{:.5f}'.format(self.vmin))
        self.maxbox.set_text('{:.5f}'.format(self.vmax))
        cutsbox.pack_start(self.minbox, 1, 0, 0)
        cutsbox.pack_end(self.maxbox, 1, 0, 0)
        cutsbox.set_spacing(5)
        clippingbox.pack_start(self.histcanvas, 1, 1, 0)
        clippingbox.pack_start(cutsbox, 0, 0, 0)
        clippingbox.set_spacing(5)

        self.zoom_view = self.create_zoom_view()
        self.stat_settings = self.create_stat_settings()
        self.stat_view = self.create_stat_view()

        grid = Gtk.VBox()
        grid.pack_start(self.zoom_view, 1, 1, 0)
        grid.pack_start(self.stat_settings, 1, 1, 0)
        grid.pack_start(self.stat_view, 1, 0, 0)

        self.plot_bar = self.create_plot_bar()
        box = Gtk.VBox()
        box.pack_start(self.plot_bar, 0, 1, 0)
        box.pack_start(self.canvas, 1, 1, 0)
        box.pack_start(self.slider, 0, 0, 0)
        box.pack_start(clippingbox, 0, 1, 0)
        box.pack_start(self.statbar, 0, 0, 0)

        hbox = Gtk.HBox()
        # hbox.pack_start(self.fileview, 1, 1, 5)
        paned2 = Gtk.HPaned(wide_handle=True)
        paned2.pack1(self.fileview, True, True)
        paned2.pack2(hbox, True, False)
        hbox.pack_start(box, 1, 1, 0)
        hbox.pack_start(grid, 0, 1, 0)
        paned = Gtk.HPaned(wide_handle=True)
        paned.pack1(paned2, True, True)
        # self.headerview.set_size_request(300, -1)
        paned.pack2(self.headerview, True, True)
        # hbox.pack_start(self.headerview, 1, 1, 5)
        # hbox.pack_start(paned, 1, 1, 5)
        self.add(paned)

        # self.connect('delete-event',Gtk.main_quit)
        self.canvas.set_size_request(400, -1)
        self.canvas.draw_idle()

        self.show_all()

    def create_plot_bar(self):
        plot_bar = Gtk.HBox()

        cmap_box = Gtk.ComboBoxText()
        cmap_store = Gtk.ListStore(str)
        [cmap_store.append([c]) for c in colormaps()[::2]]
        cidx = {i[0]: j for j, i in enumerate(cmap_store)}['viridis']
        cmap_box.set_model(cmap_store)
        cmap_box.set_wrap_width(5)
        cmap_box.connect('changed', self.set_colormap)
        cmap_box.set_active(cidx)

        scaling = Gtk.ComboBoxText()
        scalings = Gtk.ListStore(str)
        for norm in self.normalisations:
            scalings.append([norm])
        scaling.set_model(scalings)
        scaling.connect('changed', self.set_scaling)
        # scaling.set_active(0)

        layers = Gtk.ListStore(str)
        if self.loaded_fits:
            for hdu in self.loaded_fits[1:]:
                layers.append([hdu.name])
        self.layerbox = Gtk.ComboBoxText(model=layers)
        self.layerbox.connect('changed', self.set_layer)

        plot_bar.pack_start(cmap_box, 1, 1, 2)
        plot_bar.pack_start(scaling, 1, 1, 2)
        plot_bar.pack_start(self.layerbox, 1, 1, 2)

        return plot_bar

    def create_canvas(self, img=None):
        dpi = 96
        margin = 0.025
        xpixels, ypixels = 200, 200
        figsize = (1 + margin) * ypixels / dpi, (1 + margin) * xpixels / dpi

        fig = Figure(figsize=figsize, dpi=dpi)

        # Make the axis the right size...
        self.ax = fig.add_axes([margin, margin, 1 - 2 * margin, 1 - 2 * margin])
        # self.ax = fig.add_subplot(111)
        if self.loaded_fits is not None:
            self.imview = self.ax.imshow(self.loaded_fits[self.layer].data, interpolation='none', cmap=self.cmap)
        else:
            self.imview = self.ax.imshow(np.zeros((200, 200)), interpolation='none', cmap=self.cmap)
        self.ax.xaxis.set_visible(False)
        self.ax.yaxis.set_visible(False)

        # self.ax.format_coord = Formatter(self.imview)

        canvas = FigureCanvas(fig)
        canvas.mpl_connect('motion_notify_event', self.update_zoom)
        canvas.mpl_connect('motion_notify_event', self.set_pixel_stats)
        canvas.mpl_connect('motion_notify_event', self.update_region_cursor)
        canvas.mpl_connect('button_press_event', self.store_region_stats)
        canvas.mpl_connect('axes_leave_event', self.clear_region_cursor)
        # canvas.mpl_connect('pick_event', self.on_pick)

        canvas.figure.subplots_adjust(left=0.02, right=0.98)
        # canvas.set_size_request(300, 600)
        return canvas

    def create_fileview(self):
        self.filestore = Gtk.ListStore(str, str)
        view = Gtk.TreeView(model=self.filestore)
        render = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("FITS files", render, text=0)
        column.set_resizable(True)
        view.append_column(column)
        column = Gtk.TreeViewColumn("FITS files", render, text=1)
        column.set_visible(False)
        view.append_column(column)

        self.selection = view.get_selection()
        self.selection.connect("changed", self.set_view)
        # self.selection.connect("changed", self.update_slice_count)

        sv = Gtk.ScrolledWindow()
        sv.add(view)
        view.connect('size-allocate', self.treeview_update)
        sv.connect('edge-overshot', self.edge_reached)
        sv.connect('edge-reached', self.edge_reached)
        sv.connect('scroll-event', self.scroll_event)
        view.connect('key-press-event', self.edge_reached)
        sv.get_vscrollbar().connect('value-changed', self.disable_autoscroll)

        check = Gtk.CheckButton(label="Keep cut levels fixed")
        check.connect("toggled", self._set_fixed_cuts)
        check.set_active(self.fixed_cuts)

        statreg = Gtk.CheckButton(label="Keep statistics regions")
        statreg.connect("toggled", self._set_keep_regions)
        statreg.set_active(self.keep_regions)

        button = Gtk.Button(label='Change directory')
        button.connect("clicked", self._on_change_watched_dir)

        box = Gtk.VBox(spacing=3)
        box.pack_start(sv, 1, 1, 0)
        box.pack_start(check, 0, 0, 0)
        box.pack_start(statreg, 0, 0, 0)
        box.pack_start(button, 0, 0, 0)
        return box

    def _set_fixed_cuts(self, widget):
        self.fixed_cuts = widget.get_active()

    def _set_keep_regions(self, widget):
        self.keep_regions = widget.get_active()

    def create_headerview(self):
        headerview = Gtk.TextView()
        headerview.set_property("cursor-visible", False)
        headerview.set_property("monospace", True)
        sv = Gtk.ScrolledWindow()
        sv.add(headerview)
        return sv

    def disable_autoscroll(self, widget=None, event=None):
        self.autoscroll = 0

    def treeview_update(self, widget, event, data=None):
        if self.autoscroll:
            adj = widget.get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())

            selection = widget.get_selection()
            last = self.get_last_item(widget.get_model())
            if isinstance(last, Gtk.TreeIter):
                selection.select_iter(last)

    def edge_reached(self, widget, event, data=None):
        if hasattr(event, 'value_name'):
            if event.value_name == 'GTK_POS_BOTTOM':
                self.autoscroll = 1
        if hasattr(event, 'keyval'):
            if event.keyval == Gdk.KEY_End:
                self.autoscroll = 1

    def scroll_event(self, widget, event, data=None):
        # disable autoscroll on scrollwheel up
        if event.get_scroll_deltas()[2] == -1:
            self.autoscroll = 0

    def get_last_item(self, model, parent=None):
        n = model.iter_n_children(parent)
        return n and model.iter_nth_child(parent, n - 1)

    def load_fits(self, fname):
        self.loaded_fits = pyfits.open(fname)

    def calculate_cuts(self, imgdata, ns=2):
        median, sigma = np.median(imgdata), imgdata.std()
        return median - ns * sigma, median + ns * sigma

    def set_view(self, widget=None):
        if widget is None:
            layer = self.layerbox.get_active_text()
            if self.loaded_fits[layer].header['NAXIS'] == 3:
                self.imview.set_data(self.loaded_fits[layer].data[self.layer_slice, :, :])
            else:
                self.imview.set_data(self.loaded_fits[layer].data)
            self.update_zoom()
            if not self.fixed_cuts:
                self.set_scaling()
            self.restore_regions()
            self.canvas.draw_idle()
            self.update_histogram()
            self.set_clip_line()
            return
        model, treepath = widget.get_selected_rows()
        if len(model) == 0:
            return
        fname = model[treepath][1]
        self.load_fits(fname)
        layer = self.layerbox.get_active_text()
        layers = self.layerbox.get_model()
        layers.clear()
        for hdu in self.loaded_fits:
            if hdu.is_image and hdu.data is not None:
                layers.append([hdu.name])
        if layer is None or layer not in [lay[0] for lay in layers]:
            self.layerbox.set_active(0)
        else:
            layer_row = [lay for lay in layers if lay[0] == layer][0]
            self.layerbox.set_active_iter(layer_row.iter)
        self.set_header_view()
        layer = self.layerbox.get_active_text()
        self.update_slice_count()
        self.ax.clear()
        if self.loaded_fits[layer].header['NAXIS'] == 3:
            imgdata = self.loaded_fits[layer].data[self.layer_slice, :, :]
        else:
            imgdata = self.loaded_fits[layer].data
        if not self.fixed_cuts:
            self.vmin, self.vmax = self.calculate_cuts(imgdata)
        self.imview = self.ax.imshow(imgdata, interpolation=self.image_interpolation, cmap=self.cmap,
                                     vmin=self.vmin, vmax=self.vmax, filterrad=1.)
        # self.imview.set_data(self.loaded_fits[layer].data[self.layer_slice, :, :])
        self.ax.set_frame_on(False)
        if not self.fixed_cuts:
            self.set_scaling()
        self.restore_regions()
        self.canvas.draw_idle()
        self.update_histogram()
        self.set_clip_line()

    def set_header_view(self):
        head = self.loaded_fits[0].header.tostring()
        header = "\n".join([head[i: i + 80] for i in range(0, len(head), 80)]).strip()
        self.headerbuffer.set_text(header, len(header))

    def set_layer(self, widget=None, layer=None):
        layer = widget.get_active_text()
        if layer is None:
            return
        try:
            if self.loaded_fits[layer].header['NAXIS'] == 3:
                imgdata = self.loaded_fits[layer].data[self.layer_slice, :, :]
            else:
                imgdata = self.loaded_fits[layer].data
        except IndexError:
            return
        self.update_slice_count()
        # imgheader = self.loaded_fits[layer].header
        # self.imview.remove()
        self.ax.clear()
        if not self.fixed_cuts:
            self.vmin, self.vmax = self.calculate_cuts(imgdata)
        self.imview = self.ax.imshow(imgdata, interpolation=self.image_interpolation, cmap=self.cmap, vmin=self.vmin,
                                     vmax=self.vmax)
        self.restore_regions()
        self.canvas.draw_idle()
        self.update_histogram()
        self.set_clip_line()

    def set_colormap(self, widget=None):
        self.cmap = widget.get_active_text()
        self.ax.images[0].set_cmap(self.cmap)
        self.zoomdata.set_cmap(self.cmap)
        self.canvas.draw_idle()
        return

    def set_scaling(self, widget=None):
        if widget is None:
            widget = self.layerbox.get_parent().get_children()[1]
        scale = widget.get_active_text()
        if scale is None:
            widget.set_active(0)
            scale = widget.get_active_text()
        if scale in ['LINEAR', 'LOG']:
            self.ax.images[0].set_norm(self.normalisations[scale]())
        elif scale in ['POWER']:
            self.ax.images[0].set_norm(self.normalisations[scale](2))
        elif scale in ['SQRT']:
            self.ax.images[0].set_norm(self.normalisations[scale](-2))

        if scale in ['LINEAR', 'LOG']:
            self.zoomdata.set_norm(self.normalisations[scale]())
        elif scale in ['POWER']:
            self.zoomdata.set_norm(self.normalisations[scale](2))
        elif scale in ['SQRT']:
            self.zoomdata.set_norm(self.normalisations[scale](-2))
        self.update_cuts(minmax=(self.vmin, self.vmax))
        self.canvas.draw_idle()

    def create_slider(self):
        box = Gtk.HBox()
        label = Gtk.Label()

        size = self.slice_count
        slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, size - 1, 1)
        slider.set_value_pos(Gtk.PositionType.LEFT)
        slider.set_digits(0)
        # slider.set_draw_value(False)

        # slider.connect('value-changed', self.update_timestamp, label)
        slider.connect('value-changed', self.set_slice)

        box.pack_start(slider, 1, 1, 5)
        box.pack_start(label, 0, 0, 0)
        return box

    def update_timestamp(self, widget=None, label=None):
        # label.set_text(self.datacube[int(widget.get_value())]['TIMESTAMP'])
        try:
            label.set_text(str(self.loaded_fits[self.layerbox.get_active_text()].header['NAXIS3']))
        except KeyError:
            label.set_text('---')

    def set_slice(self, widget=None, index=None):
        if (widget is None) and (index is None):
            return
        if index is None:
            index = int(widget.get_value())
        self.layer_slice = index
        self.set_view()
        if widget is not None:
            widget.show_all()

    def update_slice_count(self, widget=None):
        size = self.loaded_fits[self.layerbox.get_active_text()].data.shape[0]
        naxis = self.loaded_fits[self.layerbox.get_active_text()].header['NAXIS']
        slider, label = self.slider.get_children()
        if size == 1 or naxis == 2:
            slider.set_range(0, size - 1)
            slider.set_sensitive(False)
            self.set_slice(index=0)
            self.update_timestamp(label=label)
        else:
            slider.set_sensitive(True)
            slider.set_range(0, size - 1)
            slider.set_value(0)
            slider.set_draw_value(False)
            slider.set_draw_value(True)
            self.set_slice(index=0)
            self.update_timestamp(label=label)

    def create_zoom_view(self):
        fig = Figure()
        zoomplot = fig.add_subplot(111, frameon=False)
        zoomplot.xaxis.set_visible(False)
        zoomplot.yaxis.set_visible(False)
        try:
            ref_image = self.ax.get_images()[0].get_array()
        except IndexError:
            ref_image = np.zeros((200, 200))
        xc, yc = [x // 2 for x in ref_image.shape]
        self.zoomdata = zoomplot.imshow(
            ref_image[yc - self.pixzoom:yc + self.pixzoom, xc - self.pixzoom:xc + self.pixzoom],
            interpolation='none', cmap=self.cmap)
        zoom_view = FigureCanvas(fig)

        return zoom_view

    def update_zoom(self, event=None):
        if event is None:
            image = self.imview.get_array()
            self.zoomdata.set_data(image[0:2 * self.pixzoom, 0:2 * self.pixzoom])
            self.set_pixel_stats(event)
            self.zoom_view.draw_idle()
            return
        if (event.xdata or event.ydata) is None:
            return
        x, y = int(round(event.xdata)), int(round(event.ydata))
        image = event.inaxes.get_images()[0].get_array()
        if y < self.pixzoom:
            y = self.pixzoom
        elif y > (image.shape[0] - self.pixzoom):
            y = image.shape[0] - self.pixzoom
        if x < self.pixzoom:
            x = self.pixzoom
        elif x > (image.shape[1] - self.pixzoom):
            x = image.shape[1] - self.pixzoom
        self.zoomdata.set_data(image[y - self.pixzoom:y + self.pixzoom, x - self.pixzoom:x + self.pixzoom])
        self.zoomdata.set_clim(self.vmin, self.vmax)
        self.zoom_view.draw_idle()

    def update_region_cursor(self, event=None):
        if (event.xdata or event.ydata) is None:
            return
        x, y = event.xdata, event.ydata
        image = event.inaxes.get_images()[0].get_array()
        bdist = self.region_size / 2
        # if round(y) < bdist:
        #     y = bdist - 0.5
        # elif round(y) > (image.shape[0] - bdist):
        #     y = image.shape[0] - bdist - 0.5
        # if round(x) < bdist:
        #     x = bdist - 0.5
        # elif round(x) > (image.shape[1] - bdist):
        #     x = image.shape[1] - bdist - 0.5
        self.chcursor(pos=(x, y), size=self.region_size, shape=self.region_shape)

    def chcursor(self, pos, size=20, shape='square', store=False):
        if not store:
            if self.region_cursor is not None:
                try:
                    self.region_cursor.remove()
                except ValueError:
                    self.region_cursor = None
        if shape == 'square':
            self.region_cursor = matplotlib.patches.Rectangle(
                (round(pos[0]) - 0.5 - self.region_size // 2, round(pos[1]) - 0.5 - self.region_size // 2), size, size,
                fc='none', ec='cyan', picker=15)
        elif shape == 'circle':
            self.region_cursor = matplotlib.patches.Ellipse(pos, size, size, fc='none', ec='cyan', picker=15)
        self.ax.add_patch(self.region_cursor)
        self.canvas.draw_idle()
        # pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size('pixmap/circle.svg', 40, 40)
        # win = self.canvas.get_window()
        # win.set_cursor(Gdk.Cursor.new_from_pixbuf(Gdk.Display.get_default(), pixbuf, 20, 20))
        return self.region_cursor

    def clear_region_cursor(self, widget=None):
        try:
            self.region_cursor.remove()
        except ValueError:
            self.region_cursor = None
        self.canvas.draw_idle()

    def on_pick(self, event):
        print(event.mouseevent)
        if event.artist.contains(event.mouseevent):
            event.artist.set_linewidth(3)
            self.canvas.draw_idle()

    def create_stat_view(self):
        buff = Gtk.TextBuffer(text='XPOS:\t{}\nYPOS:\t{}\nADU:\t{}\n'.format(None, None, None) +
                                   'SUM:\t{}\nNPIX:\t{}\nAVG:\t{}\nSTDDEV:\t{}'.format(None, None, None, None))
        stat_view = Gtk.TextView.new_with_buffer(buff)
        stat_view.set_property("cursor-visible", False)
        stat_view.set_property("monospace", True)
        return stat_view

    # @delayed(50)
    def set_pixel_stats(self, event, region=None):
        if event is None:
            x, y, z = 0, 0, 0
        elif (event.xdata or event.ydata) is None:
            return
        else:
            image = event.inaxes.get_images()[0].get_array()
            x, y = event.xdata, event.ydata
            region = self.create_mask_from_patch(x, y, image)
            x, y = int(round(x)), int(round(y))
            if not ((0 <= y < image.shape[0]) and (0 <= x < image.shape[1])):
                return
            try:
                z = image[y, x]
            except IndexError:
                return
        buff = self.stat_view.get_buffer()
        buff.set_text('XPOS:\t{:9.0f}\nYPOS:\t{:9.0f}\nADU:\t{:9.0f}\n'.format(x, y, z) +
                      'SUM:\t{:9.0f}\nNPIX:\t{:9.0f}\nAVG:\t{:7.3E}\nSTD:\t{:7.3E}'.format(*self.pixel_stats(region)))

    def pixel_stats(self, region=None):
        if region is None or self.region_cursor is None:
            pixels = self.zoomdata.get_array()  # self.image[region]
        else:
            pixels = self.imview.get_array().copy()
            pixels.mask = region
        psum, npix, mean, stddev = pixels.sum(), pixels.count(), pixels.mean(), pixels.std()
        return psum, npix, mean, stddev

    def store_region_stats(self, event=None):
        if (event.xdata or event.ydata) is None:
            return
        if event.button == 2:
            image = self.imview.get_array()
            x, y = event.xdata, event.ydata
            cursor = self.chcursor(pos=(x, y), size=self.region_size, shape=self.region_shape, store=True)
            mask = self.create_mask_from_patch(x, y, image)
            stats = self.pixel_stats(mask)
            region_id = '{}_{:d}_x{:.0f}_y{:.0f}'.format(self.region_shape, self.region_size, x, y)
            self.region_store[region_id] = (cursor, mask)
            self.region_stats[region_id] = stats
            statstring = '\n\n'.join(['{}:\n{}'.format(region, ' | '.join(map(str, self.region_stats[region])))
                                      for region in self.region_stats])
            self.stat_store.get_buffer().set_text(statstring)
            print('HERE:', stats)

    def restore_regions(self, statstring=''):
        if self.keep_regions:
            for region in self.region_store:
                cursor, mask = self.region_store[region]
                # self.chcursor(pos=(x, y), size=size, shape=shape, store=True)
                self.ax.add_patch(cursor)
                stats = self.pixel_stats(mask)
                self.region_stats[region] = stats
                statstring = '\n\n'.join(['{}:\n{}'.format(region, ' | '.join(map(str, self.region_stats[region])))
                                          for region in self.region_stats])
            self.stat_store.get_buffer().set_text(statstring)
        else:
            self.region_store = {}
            self.region_stats = {}
            buf = self.stat_store.get_buffer()
            buf.delete(*buf.get_bounds())

    def create_mask_from_patch(self, x, y, image, patch=None):
        if not self.region_cursor:
            return
        # i, j = np.indices(image.shape)
        # mask = np.array([[not self.region_cursor.contains_point((x, y)) for x in j[0]] for y in i.T[0]])
        yi, xi = np.indices(image.shape)
        r = self.region_size / 2
        if self.region_shape == 'circle':
            mask = (xi - x) ** 2 + (yi - y) ** 2 > r ** 2
        elif self.region_shape == 'square':
            x, y = round(x), round(y)
            mask = ((x - r) <= xi) & (xi < (x + r)) & ((y - r) <= yi) & (yi < (y + r))
            np.invert(mask, mask)
        else:
            mask = np.zeros(image.shape, dtype=bool)
        return mask

    def _clear_axes(self, axes):
        axes.set_xticklabels(())
        axes.set_xticks(())
        axes.set_yticks(())
        axes.set_yticklabels(())

    def create_stat_settings(self):
        self.region_size_setter = Gtk.SpinButton.new_with_range(2, 200, 1)
        self.region_size_setter.set_value(self.region_size)
        self.region_size_setter.set_tooltip_text('Aperture size in pixels')
        self.region_size_setter.connect('value-changed', self.set_region_size)
        self.circbut = Gtk.RadioButton.new_with_label_from_widget(None, 'circle')
        self.circbut.set_tooltip_text('NO fractional pixels yet!')
        self.sqbut = Gtk.RadioButton.new_with_label_from_widget(self.circbut, 'square')
        self.sqbut.set_active(True)
        self.sqbut.connect('toggled', self.set_region_shape)

        grid = Gtk.Grid()
        grid.attach(self.circbut, 0, 0, 1, 1)
        grid.attach(self.sqbut, 0, 1, 1, 1)
        grid.attach(self.region_size_setter, 1, 0, 1, 2)

        self.stat_store = Gtk.TextView(monospace=True, cursor_visible=False)
        sv = Gtk.ScrolledWindow()
        sv.set_vexpand(True)
        sv.add(self.stat_store)
        grid.attach(sv, 0, 2, 2, 15)

        cbut = Gtk.Button(label='Clear stats')
        cbut.connect('clicked', self.clear_stat_hist)
        grid.attach(cbut, 0, 18, 2, 1)

        grid.set_row_spacing(2)
        return grid

    def clear_stat_hist(self, widget=None):
        self.region_stats = {}
        self.region_store = {}
        buf = self.stat_store.get_buffer()
        buf.delete(*buf.get_bounds())
        while len(self.ax.patches) > 0:
            for patch in self.ax.patches:
                patch.remove()
        self.canvas.draw_idle()

    def set_region_size(self, widget=None):
        self.region_size = widget.get_value_as_int()

    def set_region_shape(self, widget=None):
        if widget.get_active():
            self.region_shape = 'square'
        else:
            self.region_shape = 'circle'

    def create_histogram(self):
        fig = Figure()
        self.histogram = fig.add_subplot(111)
        values = self.ax.get_images()[0].get_array().flatten()
        h = self.histogram.hist(values, bins='fd', normed=True, histtype='stepfilled')
        # self._clear_axes(self.histogram)
        self.vmin, self.vmax = h[1].min(), h[1].max()
        self.minline = self.histogram.axvline(self.vmin, color='green', lw=1)
        self.maxline = self.histogram.axvline(self.vmax, color='red', lw=1)
        histcanvas = FigureCanvas(fig)
        histcanvas.set_size_request(200, 100)
        histcanvas.figure.subplots_adjust(top=0.95, bottom=0.25)
        histcanvas.mpl_connect('button_press_event', self.set_clip_line)
        histcanvas.mpl_connect('scroll_event', self._zoom_histogram)
        # histcanvas.mpl_connect('motion_notify_event', self.printxy)
        return histcanvas

    def printxy(self, event):
        print(event.xdata, event.ydata, event.guiEvent)

    # @delayed(1000)
    def update_histogram(self):
        self.histogram.clear()
        values = self.ax.get_images()[0].get_array().flatten()
        self.histogram.hist(values, bins='fd', normed=True, histtype='stepfilled')
        # self._clear_axes(self.histogram)
        # self.set_clip_line(event=None)
        self.histcanvas.draw_idle()

    def _zoom_histogram(self, event):
        if event.step == 0:
            return
        xmin, xmax = self.histogram.get_xlim()
        xc = np.mean((event.xdata, np.mean((xmin, xmax)), np.mean((xmin, xmax))))
        dx = (xmax - xmin) * (1.5 * np.abs(event.step)) ** np.sign(-event.step)
        self.histogram.set_xlim(xc - dx / 2, xc + dx / 2)
        self.histcanvas.draw_idle()

    def _onselect_histogram(self, vmin, vmax):
        print(vmin, vmax)
        self.histogram.xlim(vmin, vmax)
        self.histcanvas.draw_idle()

    def update_cuts(self, widget=None, minmax=None):
        if minmax is not None:
            self.vmin, self.vmax = minmax
        else:
            try:
                self.vmin, self.vmax = [float(entry.get_text()) for entry in widget.get_parent().get_children()]
                if self.vmax < self.vmin:
                    self.vmax = self.vmin
            except ValueError:
                return
        self.imview.set_clim((self.vmin, self.vmax))
        if not minmax:
            self.set_clip_line(event=None)
        self.canvas.draw_idle()

    def set_clip_line(self, event=None):
        if event is None:
            if isinstance(self.minline, matplotlib.lines.Line2D):
                try:
                    self.minline.remove()
                except ValueError:
                    pass
            self.minline = self.histogram.axvline(self.vmin, color='green', lw=1)
            self.minbox.set_text('{:.5f}'.format(self.vmin))
            if isinstance(self.maxline, matplotlib.lines.Line2D):
                try:
                    self.maxline.remove()
                except ValueError:
                    pass
            self.maxline = self.histogram.axvline(self.vmax, color='red', lw=1)
            self.maxbox.set_text('{:.5f}'.format(self.vmax))
            self.histcanvas.draw_idle()
            return
        if (event.xdata or event.ydata) is None:
            return
        x = event.xdata
        if event.button == 1:
            if x > self.vmax:
                x = self.vmax
            if isinstance(self.minline, matplotlib.lines.Line2D):
                try:
                    self.minline.remove()
                except ValueError:
                    pass
            self.minline = self.histogram.axvline(x, color='green', lw=1)
            self.vmin = x
            self.minbox.set_text('{:.5f}'.format(x))
        elif event.button == 3:
            if x < self.vmin:
                x = self.vmin
            if isinstance(self.maxline, matplotlib.lines.Line2D):
                try:
                    self.maxline.remove()
                except ValueError:
                    pass
            self.maxline = self.histogram.axvline(x, color='red', lw=1)
            self.vmax = x
            self.maxbox.set_text('{:.5f}'.format(x))
        self.histcanvas.draw_idle()
        self.update_cuts(minmax=(self.vmin, self.vmax))

    def start_dir_watch(self, directory=None):
        if self.watched_directory is None:
            print("No directory to watch")
            return
        thread = threading.Thread(target=self._dir_watcher)
        thread.daemon = True
        self.dir_watcher_active = True
        thread.start()

    def _dir_watcher(self):
        while self.dir_watcher_active:
            fitsfiles = glob.glob(self.watched_directory + "{}*.fits".format(self.prefix))
            fitsfiles.sort()
            for f in fitsfiles:
                if f not in self.instore:
                    GLib.idle_add(self._update_filestore, f)
            time.sleep(self.refresh_interval)

    def _update_filestore(self, f):
        self.filestore.append([f.split('/')[-1], f])
        self.instore.append(f)

    def change_watched_dir(self, directory, prefix=""):
        self.dir_watcher_active = False
        self.watched_directory = directory if directory.endswith('/') else directory + '/'
        self.prefix = prefix
        self.selection.disconnect_by_func(self.set_view)
        self.filestore.clear()
        self.selection.connect("changed", self.set_view)
        del self.instore[:]
        self.start_dir_watch()

    def _on_change_watched_dir(self, widget):
        dialog = Gtk.FileChooserDialog(title="Change directory", parent=self,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            name = dialog.get_filename()
            dialog.destroy()
        else:
            dialog.destroy()
            return
        self.change_watched_dir(directory=name)


class Histogram(Gtk.Window):
    def __init__(self, parent):
        Gtk.Window.__init__(self, title="hist", default_height=150,
                            default_width=300, parent=parent)

        fig = Figure(figsize=(21, 3))
        self.histogram = fig.add_subplot(111)
        values = np.random.normal(100, 20, 10000)
        h = self.histogram.hist(values, bins='fd', normed=True, histtype='stepfilled')
        self.vmin, self.vmax = h[1].min(), h[1].max()

        canvas = FigureCanvas(fig)

        self.add(canvas)
        self.show_all()

    def __call__(self):
        print('HELLO')


class NavBar(NavigationToolbar):
    def set_message(self, msg):
        pass


class Formatter(object):
    def __init__(self, im):
        self.im = im

    def __call__(self, x, y):
        z = self.im.get_array()[int(y), int(x)]
        return 'x={:1.1f}, y={:1.1f}, z={:1.3f}'.format(x, y, z)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        win = ImageViewer(directory=sys.argv[1])
    elif len(sys.argv) > 2:
        win = ImageViewer(directory=sys.argv[1], prefix=sys.argv[2])
    else:
        win = ImageViewer()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    Gtk.main()
