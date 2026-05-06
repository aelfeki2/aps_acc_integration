"""Output writers — JSON and CSV.

Auto-detects format from the file extension. Flattens nested dicts for CSV
using dotted keys (e.g. `attributes.name`), since most ACC responses have
one or two levels of nesting that pandas would handle the same way.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger(__name__)


def write_records(records: Iterable[dict[str, Any]], path: Path) -> int:
    """Write `records` to `path`. Format chosen by extension.

    Returns the number of records written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    records = list(records)  # materialize once; APIs are fast enough.

    if suffix == ".json":
        with path.open("w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, default=str)
    elif suffix == ".csv":
        _write_csv(records, path)
    else:
        raise ValueError(f"Unsupported output extension: {suffix!r}. Use .json or .csv.")

    log.info("Wrote %d records to %s", len(records), path)
    return len(records)


def _write_csv(records: list[dict[str, Any]], path: Path) -> None:
    if not records:
        path.write_text("", encoding="utf-8")
        return

    flat = [_flatten(r) for r in records]
    # Union of all keys; preserves a stable order for determinism.
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in flat:
        for key in row:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in flat:
            writer.writerow({k: _stringify(v) for k, v in row.items()})


def _flatten(obj: dict[str, Any], parent: str = "", sep: str = ".") -> dict[str, Any]:
    """Flatten one level of nesting at a time using dotted keys."""
    out: dict[str, Any] = {}
    for k, v in obj.items():
        key = f"{parent}{sep}{k}" if parent else k
        if isinstance(v, dict):
            out.update(_flatten(v, key, sep=sep))
        else:
            out[key] = v
    return out


def _stringify(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        return json.dumps(v, default=str)
    return str(v)
