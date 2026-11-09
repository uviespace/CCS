#!/usr/bin/env bash
set -euo pipefail

cd /workspace

coca_mib_revision="67bc00ccbddc135bd4b9750c97e4f0bb0904bfe2"
mib_archive_path="CoCa/mib_tables/mib_dat_exports"
db_password="${MYSQL_PASSWORD:?MYSQL_PASSWORD is missing; create .devcontainer/.env}"
export MYSQL_PWD="${db_password}"

if ! git cat-file -e "${coca_mib_revision}^{commit}" 2>/dev/null; then
    echo "The CoCa MIB revision is unavailable in this Git checkout:" >&2
    echo "  ${coca_mib_revision}" >&2
    exit 1
fi

pic_rows="$(mysql --host=127.0.0.1 --user=ccs --batch --skip-column-names \
    --execute="SELECT COUNT(*) FROM mib_schema_coca.pic" 2>/dev/null || true)"

if [ -n "${pic_rows}" ] && [ "${pic_rows}" -gt 0 ]; then
    echo "CoCa MIB is already populated (${pic_rows} PIC rows); leaving it unchanged."
    exit 0
fi

mib_tmp="$(mktemp -d)"
trap 'rm -rf "${mib_tmp}"' EXIT
git archive "${coca_mib_revision}" "${mib_archive_path}" | tar -x -C "${mib_tmp}"
mib_dir="${mib_tmp}/${mib_archive_path}"

python .devcontainer/load-coca-mib.py "${mib_dir}"
echo "Real CoCa MIB import completed."
