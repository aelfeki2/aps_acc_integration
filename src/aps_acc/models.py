"""Optional typed wrappers for the most-used response shapes.

These are intentionally minimal — the raw dicts coming back from APS are
what most callers want. These classes exist mainly for IDE autocompletion
and a stable place to add computed properties later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Project:
    id: str
    name: str
    status: str
    type: str | None
    classification: str | None
    raw: dict[str, Any]

    @classmethod
    def from_api(cls, doc: dict[str, Any]) -> Project:
        return cls(
            id=doc["id"],
            name=doc.get("name", ""),
            status=doc.get("status", ""),
            type=doc.get("type"),
            classification=doc.get("classification"),
            raw=doc,
        )


@dataclass
class Issue:
    id: str
    display_id: int | None
    title: str
    status: str
    raw: dict[str, Any]

    @classmethod
    def from_api(cls, doc: dict[str, Any]) -> Issue:
        return cls(
            id=doc["id"],
            display_id=doc.get("displayId"),
            title=doc.get("title", ""),
            status=doc.get("status", ""),
            raw=doc,
        )
