"""Load and resolve reusable localized game text by stable keys."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

if __package__ == "":
    from localization import Localizer
    from resources.data import DataResourceError, load_record_array
else:
    from .localization import Localizer
    from .resources.data import DataResourceError, load_record_array


class TextCatalogError(RuntimeError):
    """Raised when localized text data cannot be loaded safely."""


@dataclass(frozen=True)
class TextCatalog:
    """Index localized text records and resolve them with a ``Localizer``."""

    _records: Mapping[str, Mapping[str, object]]

    @classmethod
    def from_records(cls, records: Iterable[Mapping[str, object]]) -> TextCatalog:
        """Build a catalog from records containing a stable ``text_key``."""

        if isinstance(records, (str, bytes, Mapping)):
            raise TextCatalogError("texts must be an array of objects")

        indexed: dict[str, Mapping[str, object]] = {}
        try:
            iterator = iter(records)
        except TypeError as error:
            raise TextCatalogError("texts must be an array of objects") from error

        for index, record in enumerate(iterator):
            if not isinstance(record, Mapping):
                raise TextCatalogError(f"texts[{index}] must be an object")

            key = record.get("text_key")
            if not isinstance(key, str) or not key:
                raise TextCatalogError(
                    f"texts[{index}].text_key must be a non-empty string"
                )
            if key in indexed:
                raise TextCatalogError(f"duplicate text_key: {key}")

            for field, value in record.items():
                if field.startswith("text_") and field != "text_key":
                    if not isinstance(value, str):
                        raise TextCatalogError(
                            f"texts[{index}].{field} must be a string"
                        )
            indexed[key] = MappingProxyType(dict(record))

        return cls(MappingProxyType(indexed))

    @classmethod
    def from_json(cls, path: Path) -> TextCatalog:
        """Load a catalog from a UTF-8 JSON file."""

        if not isinstance(path, Path):
            raise TypeError("path must be a pathlib.Path")
        try:
            records = load_record_array(path.name, path.parent)
        except DataResourceError as error:
            raise TextCatalogError(str(error)) from error
        return cls.from_records(records)

    def text(
        self,
        key: str,
        localizer: Localizer,
        *,
        default: str = "",
    ) -> str:
        """Return localized text for ``key`` using deterministic fallback."""

        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        if not isinstance(default, str):
            raise TypeError("default must be a string")

        record = self._records.get(key)
        if record is None:
            return localizer.text({}, "text", default)
        try:
            return localizer.text(record, "text", default)
        except TypeError as error:
            raise TextCatalogError(
                f"localized text must be a string: {key}"
            ) from error
