"""Compatibility import for the production menu party status panel."""

from __future__ import annotations

import sys

from tools._bootstrap import APP_ROOT as _APP_ROOT  # Initialize app imports.
from ui import party_status as _production_party_status


sys.modules[__name__] = _production_party_status
