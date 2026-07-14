#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="python3"
if [[ -x "$project_root/.venv/bin/python" ]]; then
    python_bin="$project_root/.venv/bin/python"
fi
cd "$project_root"
"$python_bin" -m PyInstaller --noconfirm --clean --windowed \
    --name "SpectrumCompressor" \
    --paths "src" \
    --collect-submodules "serial" \
    "run_app.py"
