"""Argoshot: a small client for the Argoshot screenshot API (https://argoshot.com/docs). Standard library only."""

from ._client import (
    DEFAULT_BASE_URL,
    Argoshot,
    ArgoshotError,
    TakeOptions,
    build_query,
    parse_error,
    sign,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_BASE_URL",
    "Argoshot",
    "ArgoshotError",
    "TakeOptions",
    "build_query",
    "parse_error",
    "sign",
    "__version__",
]
