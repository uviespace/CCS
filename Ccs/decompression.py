import logging
import numpy as np
import os
import subprocess
import threading
import time
import astropy.io.fits as pyfits

import confignator
import ccs_function_lib as cfl

cfg = confignator.get_config(check_interpolation=False)
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, cfg.get('ccs-logging', 'level').upper()))

ce_decompressors = {}


def create_fits(data=None, header=None, filename=None):
    hdulist = pyfits.HDUList()
    hdu = pyfits.PrimaryHDU()
    hdu.header = header
    hdulist.append(hdu)

    imagette_hdu = pyfits.ImageHDU()
    stack_hdu = pyfits.ImageHDU()
    margins = pyfits.ImageHDU()

    hdulist.append(imagette_hdu)
    hdulist.append(stack_hdu)
    hdulist.append(margins)

    if filename:
        with open(filename, "wb") as fd:
            hdulist.writeto(fd)

    return hdulist


def build_fits(basefits, newfits):
    base = pyfits.open(basefits)
    new = pyfits.open(newfits)
    for hdu in range(len(base)):
        base[hdu].data = np.concatenate([base[hdu].data, new[hdu].data])
    base.writeto(basefits, overwrite=True)


def convert_fullframe_to_cheopssim(fname):
    """
    Convert a fullframe (1076x1033) FITS to CHEOPS-SIM format
    @param fname: Input FITS file
    """
    d = pyfits.open(fname)
    full = np.array(np.round(d[0].data), dtype=np.uint16)
    win_dict = {"SubArray": full[:, :1024, 28:28+1024],
                "OverscanLeftImage": full[:, :1024, :4],
                "BlankLeftImage": full[:, :1024, 4:4+8],
                "DarkLeftImage": full[:, :1024, 12:28],
                "DarkRightImage": full[:, :1024, 1052:1052+16],
                "BlankRightImage": full[:, :1024, 1068:],
                "DarkTopImage": full[:, 1024:-6, 28:-24],
                "OverscanTopImage": full[:, -6:, 28:-24]}

    hdulist = pyfits.HDUList()
    hdulist.append(pyfits.PrimaryHDU())

    for win in win_dict:
        hdu = pyfits.ImageHDU(data=win_dict[win], name=win)
        hdulist.append(hdu)

    hdulist.append(pyfits.BinTableHDU(name="ImageMetaData"))

    hdulist.writeto(fname[:-5] + '_CHEOPSSIM.fits')


def ce_decompress(outdir, pool_name=None, sdu=None, starttime=None, endtime=None, startidx=None, endidx=None,
                  ce_exec=None):
    decomp = CeDecompress(outdir, pool_name=pool_name, sdu=sdu, starttime=starttime, endtime=endtime, startidx=startidx,
                          endidx=endidx, ce_exec=ce_exec)
    decomp.start()
    ce_decompressors[int(time.time())] = decomp


def ce_decompress_stop(name=None):

    if name is not None:
        ce_decompressors[name].stop()
    else:
        for p in ce_decompressors:
            ce_decompressors[p].stop()


class CeDecompress:

    def __init__(self, outdir, pool_name=None, sdu=None, starttime=None, endtime=None, startidx=None, endidx=None,
                 ce_exec=None):
        self.outdir = outdir
        self.pool_name = pool_name
        self.sdu = sdu
        self.starttime = starttime
        self.endtime = endtime
        self.startidx = startidx
        self.endidx = endidx

        if ce_exec is None:
            try:
                self.ce_exec = cfg.get('ccs-misc', 'ce_exec')
            except (ValueError, confignator.config.configparser.NoOptionError) as err:
                raise err
        else:
            self.ce_exec = ce_exec

        # check if decompression is executable
        if not os.access(self.ce_exec, os.X_OK):
            raise PermissionError('"{}" is not executable.'.format(self.ce_exec))

        self.ce_decompression_on = False
        self.ce_thread = None
        self.last_ce_time = 0
        self.ce_collect_timeout = 1
        self.ldt_minimum_ce_gap = 0.001

    def _ce_decompress(self):
        checkdir = os.path.dirname(self.outdir)
        if not os.path.exists(checkdir) and checkdir != "":
            os.mkdir(checkdir)

        thread = threading.Thread(target=self._ce_decompress_worker, name="CeDecompression")
        thread.daemon = True
        self.ce_thread = thread
        if self.starttime is not None:
            self.last_ce_time = self.starttime
        self.ce_decompression_on = True

        try:
            thread.start()
            logger.info('Started CeDecompress...')
        except Exception as err:
            logger.error(err)
            self.ce_decompression_on = False
            raise err

        return thread

    def _ce_decompress_worker(self):

        def decompress(cefile):
            logger.info("Decompressing {}".format(cefile))
            fitspath = cefile[:-2] + 'fits'
            if os.path.isfile(fitspath):
                subprocess.run(["rm", fitspath])
            subprocess.run([self.ce_exec, cefile, fitspath], stdout=open(cefile[:-2] + 'log', 'w'))

        # first, get all TM13s already complete in pool
        filedict = cfl.dump_large_data(pool_name=self.pool_name, starttime=self.last_ce_time, endtime=self.endtime,
                                       outdir=self.outdir, dump_all=True, sdu=self.sdu, startidx=self.startidx,
                                       endidx=self.endidx)
        for ce in filedict:
            self.last_ce_time = ce
            decompress(filedict[ce])

        while self.ce_decompression_on:
            filedict = cfl.dump_large_data(pool_name=self.pool_name, starttime=self.last_ce_time, endtime=self.endtime,
                                           outdir=self.outdir, dump_all=False, sdu=self.sdu, startidx=self.startidx,
                                           endidx=self.endidx)
            if len(filedict) == 0:
                time.sleep(self.ce_collect_timeout)
                continue
            self.last_ce_time, cefile = list(filedict.items())[0]
            decompress(cefile)
            self.last_ce_time += self.ldt_minimum_ce_gap
            time.sleep(self.ce_collect_timeout)
        logger.info('CeDecompress stopped.')

    def start(self):
        self._ce_decompress()

    def stop(self):
        self.ce_decompression_on = False

    def reset(self, timestamp=0):
        self.last_ce_time = timestamp
