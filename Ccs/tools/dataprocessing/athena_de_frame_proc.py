#!/usr/bin/env python3

"""
Extract FPM frames from telemetry file and save as FITS.

"""

import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button

sys.path.append('../../')
import packet_config_ATHENA_DE as de


NPKTS = 16  # number of event packets (6 bytes) per SpW packet


def run(fname, binary=False):

    fproc = de.FpmProcessor()

    results = fproc.proc_file(fname, npkts_sci=NPKTS, binary=binary)

    return results


def save_frames(frames, outfile, nans=False):

    from astropy.io import fits

    hdl = fits.HDUList()
    empty_frames = 0

    for frame in frames:

        if len(frame.evt_list_proc) == 0:
            empty_frames += 1
            continue

        hdu = fits.ImageHDU(data=frame.as_array(nans=nans))
        hdu.header['FRAMENUM'] = frame.header.frame_n
        hdu.header['NEVTS'] = len(frame.evt_list_proc)

        hdl.append(hdu)

    print('Processed {} frames.'.format(len(frames)))

    if empty_frames != 0:
        print('There were {} frames with no valid event data!'.format(empty_frames))

    hdl.writeto(outfile, overwrite=True)
    print('Results written to', outfile)


class FrameViewer:

    def __init__(self, framelist, show_empty=False, nans=False):

        self.update(framelist, show_empty=show_empty, nans=nans)

    def update(self, framelist, show_empty=False, nans=False):

        if show_empty:
            self.frames = framelist
        else:
            self.frames = [frame for frame in framelist if frame.nevts > 0]

        self.data = np.zeros((len(self.frames), de.FRAME_SIZE_Y, de.FRAME_SIZE_X))
        self.nans = nans

        for i, frame in enumerate(self.frames):
            self.data[i, :, :] = frame.as_array(nans=self.nans)

    def show(self, idx=0, cmap='inferno', interpolation='none'):

        idx = int(idx)

        fig, ax = plt.subplots(figsize=(7, 8))
        fig.subplots_adjust(bottom=0.25)
        im = ax.imshow(self.data[idx, :, :], origin='lower', vmin=np.nanmin(self.data), vmax=np.nanmax(self.data), cmap=cmap, interpolation=interpolation)
        ax.set_title('Frame ID {} (#{})'.format(self.frames[idx].frameid, idx))

        ax_frm = fig.add_axes([0.15, 0.1, 0.73, 0.03])

        # create the sliders
        sfrm = Slider(ax_frm, "Frame #", 0, self.data.shape[0] - 1, valinit=idx, valstep=range(self.data.shape[0]), color="tab:blue")

        def _update(val):
            im.set_data(self.data[val, :, :])
            ax.set_title('Frame ID {} (#{})'.format(self.frames[val].frameid, val))
            fig.canvas.draw_idle()

        sfrm.on_changed(_update)

        plt.show()


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('USAGE: ./athena_de_frame_proc.py <EVT_FILENAME> <FITS_FILE>')
        sys.exit()

    if '-b' in sys.argv:
        binary = True
        sys.argv.remove('-b')
    else:
        binary = False

    fname, fitsfile = sys.argv[1:3]
    fitsfile = os.path.abspath(fitsfile)

    ow = ''
    if os.path.isfile(fitsfile):
        while ow.lower() not in ['y', 'n']:
            ow = input('File {} already exists, overwrite? (y/n) '.format(fitsfile))

        if ow.lower() == 'n':
            sys.exit()

    frames = run(fname, binary=binary)
    save_frames(frames, fitsfile, nans=False)
