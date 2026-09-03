"""Compatibility import for production UI text-layout helpers."""

from __future__ import annotations

import sys

from tools._bootstrap import APP_ROOT as _APP_ROOT  # Initialize app imports.
from ui import text_layout as _production_text_layout


sys.modules[__name__] = _production_text_layout
