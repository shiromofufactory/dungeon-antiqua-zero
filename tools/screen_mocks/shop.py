"""Development adapter for the production shop overlay."""

from __future__ import annotations

from tools._bootstrap import APP_ROOT as _APP_ROOT  # Initialize app imports.
from ui import shop as _production_shop


for _name, _value in vars(_production_shop).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


ShopMockDataError = _production_shop.ShopUiDataError
ShopScreenMock = _production_shop.ShopOverlay

__all__ = [
    *_production_shop.__all__,
    "ShopMockDataError",
    "ShopScreenMock",
]
