"""
Simple (graphical) interface for interactive test execution and reporting
"""

import datetime
import time
import logging
import os
import json

import gi
gi.require_version('Gtk', '3.0')

from gi.repository import Gtk, Gdk
from pathlib import Path

logger = logging.getLogger(__name__)


SEQUENCE_IDX = 0  # get default sequence from test spec JSON


class TestReport:
    """
    Provides functions for interactive test reporting
    """
    def __init__(self, specfile, version, idb_version, gui=False, delimiter='|', comments=False, as_json=True, show_code=False):
        super(TestReport, self).__init__()
        self.specfile = specfile
        self.delimiter = delimiter
        self.gui = gui
        self.report = dict()

        self.version = int(version)
        self.idb_version = str(idb_version)

        self.as_json = as_json
        self._show_code = show_code

        # column positions in spec file
        self._idx_item = 0
        self._idx_descr = 1
        self._idx_ver = 3
        self._idx_res = 4

        self.testname = ''
        self.comments = comments

        self.step_rowid = dict()
        self._read_test_spec(specfile)


    def _read_test_spec(self, filename):

        if self.as_json:
            self._read_test_spec_json(filename)
        else:
            self._read_test_spec_csv(filename)

    def _read_test_spec_json(self, filename):
        with open(filename, 'r') as fd:
            spec = json.load(fd)

        self.testname = spec.get('_name')
        # self._precond = spec.get('_precon_descr')
        # self._precond_name = spec.get('_precon_name')
        # self._postcond = spec.get('_postcon_descr')
        # self._postcond_name = spec.get('_postcon_name')

        self._meta = {k: spec.get(k) for k in spec if k.startswith('_')}

        self.report['steps'] = dict()
        for step in spec.get('sequences')[SEQUENCE_IDX].get('steps'):
            self.report['steps'][step.get('_step_number')] = step

    @property
    def steps(self):
        return self.report.get('steps')

    def _read_test_spec_csv(self, filename):
        with open(filename, 'r') as fd:
            csv = fd.readlines()

        # check if TMTC column is present
        if csv[0].count(self.delimiter) == 3:
            self._idx_ver = 2
            self._idx_res = 3
            print('> Legacy version without TMTC column! <')
        elif csv[0].count(self.delimiter) == 4:
            self._idx_ver = 3
            self._idx_res = 4
        else:
            raise ValueError('Unexpected number of columns: {}'.format(csv[0].count(self.delimiter) + 1))

        step = None
        for i, line in enumerate(csv):

            items = line.strip().split(self.delimiter)
            self.report[i] = items

            if items[self._idx_item].startswith('Step '):
                self.step_rowid[items[self._idx_item]] = {'idx': i, 'comment': ''}
                step = items[self._idx_item]

            elif items[self._idx_item] == 'Comment':
                if step is not None:
                    self.step_rowid[step]['comment'] += items[self._idx_descr]

            elif items[self._idx_item] == 'Precond.':
                self._precond = items[self._idx_descr]

            elif items[self._idx_item] == 'Postcond.':
                self._postcond = items[self._idx_descr]

        self.testname = self.report[1][0]

    def execute_step(self, step, ask=True):
        """

        :param step:
        :param ask:
        :return:
        """
        if not ask:
            return

        if self.as_json:
            self._execute_step_json(step)
        else:
            self._execute_step_csv(step)

    def _execute_step_json(self, step):

        if step not in self.steps:
            raise KeyError('"{}": no such step defined!'.format(step))

        _step = self.steps.get(step)

        exe_msg = '<b>{}_{}</b>\n{}'.format(self.testname, step, _step.get('_description'))
        comment = _step.get('_step_comment')
        code = _step.get('_command_code') if self._show_code else ''

        execute = self._exec_dialog(exe_msg, comment, code=code)

        if execute:
            _step['_report_exec_time'] = get_utc()
            return
        else:
            raise KeyboardInterrupt('Test aborted at step {}'.format(step))

    def _execute_step_csv(self, step):

        try:
            exe_msg = '{}:\n{}'.format(step.upper(), self.report[self.step_rowid[str(step)]['idx']][self._idx_descr])
            comment = self.step_rowid[str(step)]['comment']

            execute = self._exec_dialog(exe_msg, comment=comment)

            if execute:
                return
            else:
                raise KeyboardInterrupt

        except KeyError:
            logger.error('"{}": no such step defined!'.format(str(step)))
            return

    def _exec_dialog(self, msg, comment, code=''):

        if self.gui:
            dialog = TestExecGUI(self.testname, msg, comment=comment, code=code)
            response = dialog.run()

            if response == Gtk.ResponseType.YES:
                dialog.destroy()
                execute = True
            else:
                dialog.destroy()
                execute = False

        else:
            execute = input(msg + ':\n(y/n)? > ')
            while execute.lower() not in ('y', 'yes', 'n', 'no'):
                execute = input(msg + ':\n(y/n)? > ')

            if execute in ('y', 'yes'):
                execute = True
            else:
                execute = False

        return execute

    def verify_step(self, step):
        """

        :param step:
        :return:
        """

        if self.as_json:
            self._verify_step_json(step)
        else:
            self._verify_step_csv(step)

    def _verify_step_json(self, step):

        if step not in self.steps:
            raise KeyError('"{}": no such step defined!'.format(step))

        _step = self.steps.get(step)

        vmsg = _step.get('_verification_description')

        if not vmsg:
            vmsg = _step.get('_description')

        result, comment, tminfo = self._verify_dialog(vmsg)

        _step['_report_result'] = result
        _step['_report_comment'] = comment
        _step['_report_tminfo'] = tminfo
        _step['_report_verification_time'] = get_utc()

    def _verify_step_csv(self, step):
        try:
            ver_msg = '{}:\n{}'.format(step.upper(), self.report[self.step_rowid[str(step)]['idx']][self._idx_ver])
            result = self._verify_dialog(ver_msg)

        except KeyError:
            logger.error('"{}": no such step defined!'.format(str(step)))
            return

        self.report[self.step_rowid[str(step)]][self._idx_res] = result

    def _verify_dialog(self, msg):

        if self.gui:
            if self.as_json:
                dialog = TestReportGUI(self.testname, msg)
            else:
                dialog = TestReportGUINoTm(self.testname, msg)

            response = dialog.run()

            comment = dialog.comment.get_text()

            if response == Gtk.ResponseType.YES:
                result = 'OK'
            elif response == Gtk.ResponseType.NO:
                result = 'NOT_OK'
            else:
                comment = ''
                result = ''

            if self.as_json:
                tminfo = dialog.tminfo
                dialog.destroy()
                return result, comment, tminfo

            if comment:
                dialog.destroy()
                result += ' ({})'.format(comment)
                return result

        else:
            return input(msg + ':\n>')

    def export(self, reportdir=None, reportfile=None, as_json=True):
        """

        :param reportdir:
        :param reportfile:
        :param as_json:
        """

        if as_json:
            if reportfile is None:
                if reportdir is None:
                    reportfile = self.specfile.replace('.jinp', '-TR-{:03d}.jrep'.format(self.version))
                else:
                    reportfile = os.path.join(reportdir, os.path.basename(self.specfile).replace('.jinp', '-TR-{:03d}.jrep'.format(self.version)))

            self.report.update(self._meta)

            self.report['_report_success'] = 'OK'  # OK, NOT_OK, PARTIAL TODO
            self.report['_report_remarks'] = ''
            self.report['_report_version'] = self.version
            self.report['_report_mib_version'] = '{}'.format(self.idb_version)
            self.report['_report_date'] = get_utc()

            Path(os.path.dirname(reportfile)).mkdir(parents=True, exist_ok=True)  # create directory if it does not exist

            with open(reportfile, 'w') as fd:
                json.dump(self.report, fd, indent=2)

        else:
            if reportfile is None:
                if reportdir is None:
                    reportfile = self.specfile.replace('.csv_PIPE', '-TR-{:03d}.csv_PIPE'.format(self.version)).replace('/testspec/', '/testrep/')
                else:
                    reportfile = os.path.join(reportdir, os.path.basename(self.specfile).replace('.csv_PIPE', '-TR-{:03d}.csv_PIPE'.format(self.version)))

            self.report[1][3] += ' TR-{:03d}, MIB v{}'.format(self.version, self.idb_version)
            self.report[2][3] = time.strftime('%Y-%m-%d')

            buf = '\n'.join([self.delimiter.join(self.report[line]) for line in range(len(self.report))])

            Path(os.path.dirname(reportfile)).mkdir(parents=True, exist_ok=True)  # create directory if it does not exist

            with open(reportfile, 'w') as fd:
                fd.write(buf + '\n')

        logger.info('Report written to {}.'.format(reportfile))
        print('Report written to {}.'.format(reportfile))


class TestReportGUINoTm(Gtk.MessageDialog):
    """
    GUI for the TestReport class
    """
    def __init__(self, testlabel, message):
        super(TestReportGUINoTm, self).__init__(title=testlabel,
                                            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                                     Gtk.STOCK_NO, Gtk.ResponseType.NO,
                                                     Gtk.STOCK_YES, Gtk.ResponseType.YES,))

        head, body = self.get_message_area().get_children()
        head.set_text(message)

        cancel, fail, verify = self.get_action_area().get_children()

        cancel.get_child().get_child().get_children()[1].set_label('Skip')
        fail.get_child().get_child().get_children()[1].set_label('FAILED')
        verify.get_child().get_child().get_children()[1].set_label('VERIFIED')

        self.comment = Gtk.Entry()
        self.comment.set_placeholder_text('Optional comment')
        self.get_message_area().add(self.comment)

        verify.grab_focus()

        self.show_all()


class TestReportGUI(Gtk.MessageDialog):
    def __init__(self, testlabel, message):
        super(TestReportGUI, self).__init__(title=testlabel, skip_taskbar_hint=False)

        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_NO, Gtk.ResponseType.NO,
                         Gtk.STOCK_YES, Gtk.ResponseType.YES)

        self.set_markup('\n' + message)

        self.set_resizable(True)
        self.set_border_width(5)

        cancel = self.get_widget_for_response(Gtk.ResponseType.CANCEL)
        fail = self.get_widget_for_response(Gtk.ResponseType.NO)
        verify = self.get_widget_for_response(Gtk.ResponseType.YES)


        cancel.get_child().get_child().get_children()[1].set_label('SKIP')
        fail.get_child().get_child().get_children()[1].set_label('FAILED')
        verify.get_child().get_child().get_children()[1].set_label('VERIFIED')

        verify.grab_focus()

        self.comment = Gtk.Entry()
        self.comment.set_placeholder_text('Optional comment')

        msgbox = self.get_content_area()
        msgbox.pack_start(self.comment, False, False, 0)

        self.tmview = self.pmodel()
        self.tmview.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.tmview.drag_dest_set_target_list(None)
        self.tmview.drag_dest_add_text_targets()

        self.tmview.connect('drag-data-received', self.pktin)

        self.tmlist = Gtk.ScrolledWindow()
        self.tmlist.set_size_request(500, -1)

        self.tmlist.add(self.tmview)
        # self.tmlist.set_min_content_height(40)
        # self.tmlist.set_max_content_height(500)

        tmbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)

        tmbuttons = Gtk.Toolbar(orientation=Gtk.Orientation.VERTICAL)
        tmbuttons.set_style(Gtk.ToolbarStyle.ICONS)

        b_add = Gtk.ToolButton()
        b_add.set_icon_name('list-add')
        b_add.connect('clicked', self._add_tm_item)
        b_rm = Gtk.ToolButton()
        b_rm.set_icon_name('list-remove')
        b_rm.connect('clicked', self._rm_tm_item)
        b_up = Gtk.ToolButton()
        b_up.set_icon_name('go-up')
        b_up.connect('clicked', self._up_tm_item)
        b_down = Gtk.ToolButton()
        b_down.set_icon_name('go-down')
        b_down.connect('clicked', self._down_tm_item)

        tmbuttons.insert(b_add, -1)
        tmbuttons.insert(b_rm, -1)
        tmbuttons.insert(b_up, -1)
        tmbuttons.insert(b_down, -1)

        tmbox.pack_start(self.tmlist, True, True, 0)
        tmbox.pack_start(tmbuttons, False, False, 0)

        msgbox.pack_start(tmbox, True, True, 0)

        self.show_all()

    def _rm_tm_item(self, widget, *args):
        tv, i = self.tmview.get_selection().get_selected()
        tv.remove(i)

    def _add_tm_item(self, widget, *args):
        self.tmview.get_model().append(None, ['', True])

    def _up_tm_item(self, widget, *args):
        tv, i = self.tmview.get_selection().get_selected()
        tv.move_before(i, tv.iter_previous(i))

    def _down_tm_item(self, widget, *args):
        tv, i = self.tmview.get_selection().get_selected()
        tv.move_after(i, tv.iter_next(i))

    @property
    def tminfo(self) -> list:

        info = []
        model = self.tmview.get_model()

        for pkt in model:
            if pkt[1]:
                pars = [par[0] for par in pkt.iterchildren() if par[1]]
                info.append(tuple([pkt[0], pars]))

        return info

    def pktin(self, *args):
        data = args[4]

        try:
            desc, pars = self.proc_tm(data.get_text())
        except Exception as err:
            logger.info(err)
            return

        ref = self.tmview.get_model().append(None, [desc, True])
        for par in pars:
            self.tmview.get_model().append(ref, [par, False])

    def pmodel(self):
        pm = Gtk.TreeStore(str, bool)
        tv = Gtk.TreeView()
        tv.set_tooltip_text('Drop TM packets you want included in the test report here')
        tv.set_model(pm)

        text_cell = Gtk.CellRendererText(editable=True)
        text_cell.connect('edited', self._edit_cell, 0)
        column = Gtk.TreeViewColumn("Telemetry", text_cell, text=0)
        tv.append_column(column)

        toggle_cell = Gtk.CellRendererToggle()
        toggle_cell.connect('toggled', self._use_row, 1)
        column = Gtk.TreeViewColumn("Use", toggle_cell, active=1)
        tv.append_column(column)

        return tv

    def _use_row(self, widget, row, columnidx):
        self.tmview.get_model()[row][columnidx] = not self.tmview.get_model()[row][columnidx]

    def _edit_cell(self, widget, row, text, columnidx):
            self.tmview.get_model()[row][columnidx] = text

    def proc_tm(self, tm):
        hdr, name, _, *pars = tm.split('\n')

        pktdesc = self.fmt_hdr(name, hdr)
        pktpars = [' '.join(par.split()) for par in pars]

        return pktdesc, pktpars

    def fmt_hdr(self, name, hdr):

        apid, seq, len7, st, sst, cuc = hdr.split('|')

        seq = seq.split(':')[1]
        st = st.split(':')[1]
        sst = sst.split(':')[1]
        cuc = cuc.split(':')[1]

        desc = 'TM({},{}) {} @ {} [{}]'.format(st, sst, name, cuc, seq)

        return desc


class TestExecGUI(Gtk.MessageDialog):
    """
    Dialog window to confirm test step execution
    """
    def __init__(self, testlabel, message, comment='', code=''):
        super(TestExecGUI, self).__init__(title=testlabel, skip_taskbar_hint=False)

        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_YES, Gtk.ResponseType.YES)
        # self.add_buttons(Gtk.STOCK_YES, Gtk.ResponseType.YES)

        head, body = self.get_message_area().get_children()

        if comment:
            message += '\n\n<i>{}</i>'.format(comment)

        if code:
            message += '\n\n<tt><b>CODE</b>\n{}</tt>'.format(code)

        head.set_markup(message)

        abort, exe = self.get_action_area().get_children()
        # exe, = self.get_action_area().get_children()

        abort.get_child().get_child().get_children()[1].set_label('ABORT')
        exe.get_child().get_child().get_children()[1].set_label('EXECUTE')

        exe.grab_focus()

        self.show_all()


def get_utc():
    return datetime.datetime.isoformat(datetime.datetime.now(datetime.UTC))
