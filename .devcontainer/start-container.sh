#!/usr/bin/env bash
set -e

# A fixed session-bus address lets independent GUI processes started by an IDE
# discover one another, as CCS expects. /tmp persists across container restarts,
# but the old daemon does not, so always replace its stale socket.
bus_socket="/tmp/ccs-session-bus"
rm -f "${bus_socket}"
dbus-daemon --session --fork --nopidfile --address="unix:path=${bus_socket}"

exec "$@"
