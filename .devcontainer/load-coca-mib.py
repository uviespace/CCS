#!/usr/bin/env python3
"""Load the archived real CoCa MIB using the project's unmodified importer."""

import os
from pathlib import Path
import sys
from urllib.parse import quote_plus


WORKSPACE = Path("/workspace")
sys.path.insert(0, str(WORKSPACE / "Ccs" / "tools"))

import import_mib  # noqa: E402


if len(sys.argv) != 2:
    raise SystemExit(f"Usage: {sys.argv[0]} MIB_DIRECTORY")

mib_dir = Path(sys.argv[1])
if not (mib_dir / "pic.dat").is_file():
    raise SystemExit(f"CoCa MIB is incomplete: {mib_dir / 'pic.dat'} is missing")

try:
    password = quote_plus(os.environ["MYSQL_PASSWORD"])
except KeyError as exc:
    raise SystemExit(
        "MYSQL_PASSWORD is missing; create /workspace/.devcontainer/.env"
    ) from exc
import_mib.MIBDIR = str(mib_dir)
import_mib.DBNAME = "mib_schema_coca"
import_mib.DBURL = f"mysql://ccs:{password}@127.0.0.1"

import_mib.generate_wbsql()
import_mib.create_schema()
import_mib.import_mib()
