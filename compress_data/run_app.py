"""PyInstaller-friendly application entry point."""

import sys
from pathlib import Path


SOURCE_DIRECTORY = Path(__file__).resolve().parent / "src"

if SOURCE_DIRECTORY.is_dir() and str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from spectrum_compressor.main import main


if __name__ == "__main__":
    raise SystemExit(main())
