"""Vector registry and base class.

Each vector module registers itself by subclassing BaseVector.
The registry maps VectorType → vector instance for route dispatch.
"""

from __future__ import annotations

import abc
from typing import Any

from models import VectorType


class BaseVector(abc.ABC):
    vector_type: VectorType

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "vector_type") and cls.vector_type is not None:
            _registry[cls.vector_type] = cls

    @abc.abstractmethod
    def generate(self, callback_url: str, test_case: str = "", **kwargs: Any) -> bytes:
        """Return the raw payload content (bytes)."""

    @abc.abstractmethod
    def content_type(self) -> str:
        """MIME type for the HTTP response."""

    def poc_files(self, callback_url: str, test_case: str = "", **kwargs: Any) -> dict[str, bytes]:
        """Return {relative_path: content} for POC bundle inclusion.

        Default: no files (vectors that only serve HTTP content).
        Override for vectors that produce repo files (CLAUDE.md, .mcp.json, etc).
        """
        return {}


_registry: dict[VectorType, type[BaseVector]] = {}


def get_vector_class(vtype: VectorType) -> type[BaseVector] | None:
    return _registry.get(vtype)


def get_vector(vtype: VectorType) -> BaseVector | None:
    cls = _registry.get(vtype)
    return cls() if cls else None


def list_vectors() -> list[VectorType]:
    return list(_registry.keys())
