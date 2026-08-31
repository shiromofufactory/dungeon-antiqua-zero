"""Load and resolve reusable localized game text by stable keys."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

if __package__ == "":
    from localization import Localizer, format_text_template
    from resources.data import DataResourceError, load_record_array
else:
    from .localization import Localizer, format_text_template
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

            normalized = dict(record)
            for field, value in record.items():
                if field.startswith("text_") and field != "text_key":
                    if isinstance(value, str):
                        continue
                    if not isinstance(value, (list, tuple)) or not all(
                        isinstance(line, str) for line in value
                    ):
                        raise TextCatalogError(
                            f"texts[{index}].{field} must be a string "
                            "or an array of strings"
                        )
                    normalized[field] = tuple(value)
            indexed[key] = MappingProxyType(normalized)

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

    def formatted_text(
        self,
        key: str,
        localizer: Localizer,
        values: Mapping[str, str],
        default: str = "",
    ) -> str:
        """Resolve named ``$NAME$`` placeholders and localize the result."""

        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        if not isinstance(values, Mapping):
            raise TypeError("formatted text values must be a mapping")
        if not isinstance(default, str):
            raise TypeError("default must be a string")

        record = self._records.get(key, {})
        template = localizer.value(record, "text", default)
        if not isinstance(template, str):
            raise TextCatalogError(f"localized text must be a string: {key}")
        template = format_text_template(template, values)
        return localizer.text(
            {f"text_{localizer.language.value}": template},
            "text",
            default,
        )

    def formatted_text_from_keys(
        self,
        key: str,
        localizer: Localizer,
        value_keys: Mapping[str, str],
        default: str = "",
    ) -> str:
        """Format one template with raw localized values from other keys."""

        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        if not isinstance(default, str):
            raise TypeError("default must be a string")
        if not isinstance(value_keys, Mapping):
            raise TypeError("formatted text value keys must be a mapping")
        if not all(
            isinstance(name, str)
            and name
            and isinstance(value_key, str)
            and value_key
            for name, value_key in value_keys.items()
        ):
            raise ValueError("formatted text value keys must be non-empty strings")

        values: dict[str, str] = {}
        for name, value_key in value_keys.items():
            record = self._records.get(value_key, {})
            value = localizer.value(record, "text", "")
            if not isinstance(value, str):
                raise TextCatalogError(
                    f"localized text must be a string: {value_key}"
                )
            if not value:
                return localizer.text({}, "text", default)
            values[name] = value
        return self.formatted_text(
            key,
            localizer,
            values,
            default=default,
        )

    def lines(
        self,
        key: str,
        localizer: Localizer,
        *,
        default: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        """Return one or more localized lines from a string or string array."""

        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        if not isinstance(default, tuple) or not all(
            isinstance(line, str) for line in default
        ):
            raise TypeError("default must be a tuple of strings")

        record = self._records.get(key, {})
        value = localizer.value(record, "text", default)
        if isinstance(value, str):
            source_lines = (value,)
        elif isinstance(value, (list, tuple)) and all(
            isinstance(line, str) for line in value
        ):
            source_lines = tuple(value)
        else:
            raise TextCatalogError(
                f"localized text must be a string or array of strings: {key}"
            )

        selected_field = f"text_{localizer.language.value}"
        return tuple(
            localizer.text({selected_field: line}, "text")
            for line in source_lines
        )
