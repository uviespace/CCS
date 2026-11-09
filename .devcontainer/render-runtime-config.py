#!/usr/bin/env python3
"""Create an untracked egse.cfg copy containing the local DB password."""

import configparser
import os
from pathlib import Path
import sys


if len(sys.argv) != 3:
    raise SystemExit(f"Usage: {sys.argv[0]} SOURCE_CONFIG RUNTIME_CONFIG")

try:
    password = os.environ["MYSQL_PASSWORD"]
except KeyError as exc:
    raise SystemExit(
        "MYSQL_PASSWORD is missing; create /workspace/.devcontainer/.env"
    ) from exc

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
config = configparser.ConfigParser(interpolation=None)
if not config.read(source):
    raise SystemExit(f"Could not read {source}")

config.set("database", "password", password)
destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
with destination.open("w") as stream:
    config.write(stream)
destination.chmod(0o600)
