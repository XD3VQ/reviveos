#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ ! -x "$project_dir/.venv/bin/python" ]; then
    echo "Set up the Python environment using README.md first." >&2
    exit 1
fi
exec "$project_dir/.venv/bin/python" "$project_dir/launch.py" "$@"
