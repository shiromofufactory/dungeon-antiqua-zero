"""Authoring-time validation and compilation helpers for event data."""

from .catalogs import reference_catalogs
from .events import (
    EVENT_SOURCE_FORMAT_VERSION,
    EVENT_RUNTIME_FORMAT_VERSION,
    EventDiagnostic,
    EventSourceError,
    compile_event_sources,
    event_source_paths,
    load_event_source,
    load_event_sources,
    save_compiled_events,
    save_event_source,
    validate_event_sources,
)

__all__ = (
    "EVENT_RUNTIME_FORMAT_VERSION",
    "EVENT_SOURCE_FORMAT_VERSION",
    "reference_catalogs",
    "EventDiagnostic",
    "EventSourceError",
    "compile_event_sources",
    "event_source_paths",
    "load_event_source",
    "load_event_sources",
    "save_compiled_events",
    "save_event_source",
    "validate_event_sources",
)
