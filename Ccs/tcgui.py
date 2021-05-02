import gi
import matplotlib

matplotlib.use('GTK3Cairo')
gi.require_version('Notify', '0.7')
import datetime
from gi.repository import Gtk, Notify
import numpy as np

from database.tm_db import scoped_session_maker


class TcGui(Gtk.Window):
    autoscroll = 1
    tclog = Gtk.ListStore(str, str, str)
    column_names = ['Time', 'TC Name', 'Parameters']
    cmd_archive = {}

    def __init__(self, cfg, ccs, tcpool=None):
        # Gtk.Window.__init__(self, title="TC Control", default_height=500, default_width=800)
        super(TcGui, self).__init__(title="TC Control", default_height=500, default_width=800)

        self.set_border_width(5)
        self.set_resizable(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.ccs = ccs
        self.cfg = cfg
        self.poolmgr = ccs.poolmgr
        self.session_factory = self.poolmgr.session_factory

        Notify.init("TCGui")

        if tcpool is None:
            self.poolmgr.logger.warning("No TC Pool selected!")
            # Notify.Notification.new('No TC Pool selected!').show()
        elif tcpool not in self.poolmgr.loaded_pools:
            self.poolmgr.logger.warning("Cannot set {}. Not a loaded pool.".format(tcpool))
            # Notify.Notification.new("Cannot set {}. Not a loaded pool.".format(tcpool)).show()
            return
        self.pool_name = tcpool
        self.set_title("TC Control (Pool: {})".format(tcpool))

        if self.pool_name not in self.poolmgr.tc_connections:
            self.poolmgr.logger.warning("TC socket not connected!")

        cmd_model = self.create_cmd_model()

        box = Gtk.ComboBoxText()
        box.set_model(cmd_model)
        # box.get_child().set_placeholder_text('Select TC')
        box.set_tooltip_text('Select TC')
        but = Gtk.Button()
        but.set_label('Create TC')
        but.grab_focus()
        but.connect('clicked', self.on_click, box)

        resend_but = Gtk.Button(label='Send TC', tooltip_text='Send TC selected in list')
        # resend_but.set_sensitive(False)

        self.treeview = self.create_treeview()
        self.selection = self.treeview.get_selection()
        self.selection.connect('changed', self.tree_selection_changed, resend_but)
        resend_but.connect('clicked', self.resend_tc, self.selection)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.add(self.treeview)

        scrolled_window.connect('edge-reached', self.edge_reached)
        scrolled_window.connect('edge-overshot', self.edge_reached)
        scrolled_window.connect('scroll-event', self.scroll_event)

        vbox = Gtk.VBox()
        hbox = Gtk.HBox()

        hbox.pack_start(box, 0, 0, 0)
        hbox.pack_start(but, 0, 0, 5)
        hbox.pack_end(resend_but, 0, 0, 0)

        vbox.pack_start(hbox, 0, 0, 2)
        vbox.pack_start(scrolled_window, 1, 1, 2)
        self.add(vbox)
        self.show_all()

    def set_pool(self, tcpool):
        if tcpool not in self.poolmgr.loaded_pools:
            self.poolmgr.logger.warning("Cannot set {}. Not a loaded pool.".format(tcpool))
            # Notify.Notification.new("Cannot set {}. Not a loaded pool.".format(tcpool)).show()
            return
        self.pool_name = tcpool
        self.set_title("TC Control (Pool: {})".format(tcpool))
        self.show_all()

    def create_cmd_model(self):
        # cmd_model = Gtk.ListStore(str)
        cmd_model = Gtk.TreeStore(str)
        dbcon = self.session_factory()
        dbres = dbcon.execute('SELECT ccf_descr,ccf_type,ccf_stype from ccf order by ccf_type,ccf_stype')
        tcs = dbres.fetchall()
        dbcon.close()

        categ = ['DPU_DBS', 'DPU_IFSW', 'SES']

        for c in categ:
            it = cmd_model.append(None, [c])
            [cmd_model.append(it, ['({:d},{:d})\t'.format(*tc[1:]) + tc[0]]) for tc in tcs if tc[0].startswith(c)]
        return cmd_model

    def create_treeview(self):
        # self.textview = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        treeview = Gtk.TreeView(self.tclog)

        for i, name in enumerate(self.column_names):
            render = Gtk.CellRendererText(font='monotype')
            column = Gtk.TreeViewColumn(name, render, text=i)
            # column.set_sort_column_id(i)
            column.set_resizable(True)
            treeview.append_column(column)
        treeview.connect('size-allocate', self.treeview_update)
        return treeview

    def on_click(self, widget, box):
        model = box.get_model()
        path = box.get_active_iter()
        tc = model[path][0].split('\t')[1]

        dbcon = self.session_factory()
        dbres = dbcon.execute(
            'select CCF_NPARS,CCF_DESCR2,CDF_PNAME,CDF_GRPSIZE from ccf left join cdf on ccf_cname=cdf_cname where ccf_descr="%s"' % tc)
        fetch = dbres.fetchall()
        dbcon.close()
        npars, descr2, *_ = fetch[0]

        if npars != 0:
            win2 = CommandWindow()
            # win2 = Gtk.Window()
            # ask for number of parameter repetitions in case of var. length TCs 
            if any([i[-1] for i in fetch]):
                pnum = self.ask_par(win2)
                if pnum == 0:
                    return
            else:
                pnum = 0

            self.command_string = Gtk.Label('')
            self.command_string.set_selectable(True)
            self.command_string.set_padding(5, 1)

            pbox = self.tc_setup(tc, pnum)
            vbox = Gtk.VBox()
            hbox = Gtk.HBox()
            b = Gtk.Button()
            b.set_label('Cancel')
            b.connect('clicked', self.wdestroy, win2)

            b2 = Gtk.Button()
            b2.set_label('Create TC')
            b2.connect('clicked', self.tc_getpars, tc, pbox)
            b2.grab_focus()

            d = Gtk.Label(descr2.strip('_'))
            win2.set_title(tc.strip('_'))

            hbox.pack_start(d, 1, 0, 5)
            hbox.pack_start(b, 1, 0, 5)
            hbox.pack_end(b2, 1, 0, 5)

            vbox.pack_end(hbox, 1, 0, 5)
            vbox.pack_start(pbox, 0, 0, 5)
            vbox.pack_start(self.command_string, 1, 1, 0)

            win2.add(vbox)
            win2.connect('delete-event', self.wdestroy)
            win2.show_all()
        else:
            # pckt = self.ccs.Tcbuild(tc)
            self.log_tc(tc, pckt=[tc])

    def wdestroy(self, widget, w, *args):
        try:
            w.destroy()
        except AttributeError:
            widget.destroy()

    def tc_setup(self, tcname, reps):
        dbcon = self.session_factory()
        dbres = dbcon.execute(
            'SELECT cpc_descr,cpc_pafref,cdf_grpsize FROM ccf left join cdf on ccf_cname=cdf_cname left join cpc on cdf_pname=cpc_pname where ccf_descr="%s" and cpc_descr!="None"' % tcname)
        pars = dbres.fetchall()
        pbox = Gtk.HBox()

        for par in pars:
            if par[1] is not None:
                model = Gtk.ListStore(str)
                dbres = dbcon.execute(
                    'SELECT pas_altxt,pas_alval FROM cpc left join pas on cpc_pafref=pas_numbr where cpc_descr="%s"' %
                    par[0])
                paslist = dbres.fetchall()
                paslist = [i[0] for i in paslist]
                for pas in paslist:
                    model.append([pas])

                pfield = Gtk.ComboBoxText()
                pfield.set_model(model)
                pfield.set_tooltip_text(par[0])

            else:
                dbres = dbcon.execute(
                    'SELECT prv_minval,prv_maxval from prv left join cpc on cpc_prfref=prv_numbr where cpc_descr="%s"' %
                    par[0])
                fetch = dbres.fetchall()
                limits = '\n'.join(['[{} - {}]'.format(*x) for x in fetch])
                pfield = Gtk.Entry()
                pfield.set_placeholder_text(self.ccs.none_to_empty(par[0]))
                pfield.set_tooltip_text(par[0] + '\n' + limits)

            pbox.pack_start(pfield, 0, 0, 5)

        grpsize = [i[2] for i in pars]

        if np.any(grpsize) and reps > 1:
            repbox = Gtk.VBox()
            repbox.pack_start(pbox, 0, 0, 2)
            grpos = np.argwhere(grpsize)[0, 0]
            for i in range(reps - 1):
                pbox = Gtk.HBox()

                for par in pars[grpos + 1:][::-1]:
                    if par[1] is not None:
                        model = Gtk.ListStore(str)
                        dbres = dbcon.execute(
                            'SELECT pas_altxt,pas_alval FROM cpc left join pas on cpc_pafref=pas_numbr where cpc_descr="%s"' %
                            par[0])
                        paslist = dbres.fetchall()
                        paslist = [i[0] for i in paslist]
                        for pas in paslist:
                            model.append([pas])

                        pfield = Gtk.ComboBoxText()
                        pfield.set_model(model)
                        pfield.set_tooltip_text(par[0])

                    else:
                        pfield = Gtk.Entry()
                        pfield.set_placeholder_text(par[0])
                        pfield.set_tooltip_text(par[0])

                    pbox.pack_end(pfield, 0, 0, 5)
                repbox.pack_start(pbox, 0, 0, 2)
            dbcon.close()
            return repbox

        else:
            self.command_string.set_markup('<span style="italic">Tcsend_DB("{}", {})</span>'.format(tcname, ', '.join(
                [x.get_placeholder_text() if hasattr(x, 'get_placeholder_text') else x.get_tooltip_text()
                 for x in pbox.get_children()])))
            dbcon.close()
            return pbox

    def tc_getpars(self, widget, tcname, pbox=None):
        pars = [tcname]

        if isinstance(pbox, Gtk.HBox):
            pfields = pbox.get_children()
        elif isinstance(pbox, Gtk.VBox):
            pfields = [i for x in [hbox.get_children() for hbox in pbox.get_children()] for i in x]

        for par in pfields:
            if 'get_active' in par.__dir__():
                # dbres = self.dbcon.execute('SELECT pas_alval FROM pas where pas_altxt="%s";'%par.get_active_text())
                # pars.append(self.ccs.c.fetchone()[0])
                pars.append(par.get_active_text())
            else:
                parval = par.get_text()
                if par.get_placeholder_text() in ['DPU_IFSW_SkyPattern', 'DPU_DBS_FREE_BOOT_PARAM']:
                    parval = bytes.fromhex(parval)
                pars.append(parval)

        if None in pars:
            return

        pars = list(map(self.ccs.str_convert, pars))
        # pckt = self.ccs.Tcbuild(*pars)
        self.log_tc(tcname, pckt=pars, params=
                    ', '.join([x.get_active_text() if 'get_active' in x.__dir__() else x.get_text() for x in pfields]))

    def ask_par(self, widget, minval=0):
        dia = Gtk.Dialog('# of Parameters', widget, 0, ('Cancel', Gtk.ResponseType.CANCEL, 'OK', Gtk.ResponseType.OK))

        adj = Gtk.Adjustment(1, minval, 20, 1, 5, 0)
        e = Gtk.SpinButton.new(adj, adj.get_step_increment(), 0)
        e.set_numeric(1)
        cbox = dia.get_content_area()
        cbox.add(e)
        dia.show_all()

        resp = dia.run()
        if resp == Gtk.ResponseType.OK:
            parnum = e.get_value_as_int()
            # print(parnum)
        else:
            parnum = 0
        dia.destroy()
        return parnum

    def log_tc(self, tc, params='', pckt=None):
        timestamp = datetime.datetime.utcnow().strftime('%T.%f')[:-3]
        # text = '[{:s}]\t{:s}\t{:s}\n'.format(timestamp,tc,params)
        self.tclog.append([timestamp, tc, params])
        self.cmd_archive[timestamp] = pckt
        return

    def resend_tc(self, widget, selection):
        assert selection
        model, treepath = self.selection.get_selected_rows()

        if len(treepath) == 0:
            return
        row = model[treepath]
        tc_config = self.cmd_archive[row[0]]
        if self.pool_name not in self.poolmgr.tc_connections:
            self.poolmgr.logger.warning("Not connected to TC socket!")
            # Notify.Notification.new("Not connected to TC socket!").show()
            return
        tc, (st, sst, apid) = self.ccs.Tcbuild(*tc_config)
        self.poolmgr.tc_send(self.pool_name, tc.bytes)
        self.ccs.counters[int(str(apid), 0)] += 1
        self.poolmgr.logger.info('TC %s,%s sent to %s\n' % (st, sst, apid))

    def tree_selection_changed(self, selection, button):
        # if selection.count_selected_rows:
        #     button.set_sensitive(True)
        # else:
        #     button.set_sensitive(False)
        return

    def treeview_update(self, widget, event, data=None):
        if self.autoscroll:
            adj = widget.get_vadjustment()
            # if self.sort_order == Gtk.SortType.DESCENDING:
            adj.set_value(adj.get_upper() - adj.get_page_size())

    def edge_reached(self, widget, event, data=None):
        self.autoscroll = 1;
        return

    def scroll_bar(self, widget):
        # a little crude, but we want to catch scrollbar-drag events too
        self.autoscroll = 0;
        return

    def scroll_event(self, widget, event, data=None):
        self.autoscroll = 0;
        return


class CommandWindow(Gtk.Window):
    def __init__(self, parent=None):
        # Gtk.Window.__init__(self)
        super(CommandWindow, self).__init__()


if __name__ == "__main__":
    win = TcGui()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    Gtk.main()
