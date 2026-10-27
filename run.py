#!/usr/bin/env python3
"""Launcher: keep ``-I`` isolation while loading src/."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

from gwy_format.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
