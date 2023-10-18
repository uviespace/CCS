#!/bin/bash
# Generate desktop entries for CCS and TST apps

CDIR=$1

echo "[Desktop Entry]
Name=CCS
Icon=${CDIR}/Ccs/pixmap/ccs_logo_2.svg
Comment=The UVIE Central Checkout System
Exec=${CDIR}/start_ccs
Path=${CDIR}
Type=Application
Categories=Development;" > ccs.desktop

echo "[Desktop Entry]
Name=TST
Icon=${CDIR}/Tst/tst/style/tst.png
Comment=The UVIE Test Specification Tool
Exec=${CDIR}/start_tst
Path=${CDIR}
Type=Application
Categories=Development;" > tst.desktop
