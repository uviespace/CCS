#!/usr/bin/env bash
set -euo pipefail

cd /workspace

runtime_config="/home/ubuntu/.config/ccs/egse.cfg"
python .devcontainer/render-runtime-config.py /workspace/egse.cfg "${runtime_config}"

echo "Installing the local confignator package..."
make confignator BASIC_CONFI_CFG="${runtime_config}" BASIC_PATH=/workspace

echo "Creating the CCS and TST database schemas..."
make databases

echo "Importing the CoCa SCOS MIB..."
bash .devcontainer/import-coca-mib.sh

echo "Checking CoCa runtime imports..."
python -c "import dbus, gi; gi.require_version('Gtk', '3.0'); gi.require_version('GtkSource', '3.0'); from gi.repository import Gtk, GtkSource"
python -c "import gi; gi.require_version('GdkPixbuf', '2.0'); from gi.repository import GdkPixbuf; GdkPixbuf.Pixbuf.new_from_file('/workspace/Ccs/pixmap/media-playback-start-symbolic_uvie.svg')"

echo "CoCa development environment is ready."
