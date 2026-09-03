"""Compatibility import for the production shop party panel."""

from __future__ import annotations

import sys

from tools._bootstrap import APP_ROOT as _APP_ROOT  # Initialize app imports.
from ui import shop_party as _production_shop_party


sys.modules[__name__] = _production_shop_party
