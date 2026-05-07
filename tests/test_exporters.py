"""Tests for JSON/CSV exporters."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from aps_acc.exporters import write_records


def test_writes_json(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    n = write_records(
        [{"id": "1", "attributes": {"name": "Alpha"}}, {"id": "2"}], out
    )
    assert n == 2
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0]["attributes"]["name"] == "Alpha"


def test_writes_csv_flattens_nested(tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    write_records(
        [
            {"id": "1", "attributes": {"name": "Alpha", "status": "active"}},
            {"id": "2", "attributes": {"name": "Beta", "status": "archived"}},
        ],
        out,
    )
    rows = list(csv.DictReader(out.open("r", encoding="utf-8")))
    assert rows[0]["attributes.name"] == "Alpha"
    assert rows[1]["attributes.status"] == "archived"


def test_csv_handles_lists_as_json(tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    write_records([{"id": "1", "tags": ["a", "b"]}], out)
    rows = list(csv.DictReader(out.open("r", encoding="utf-8")))
    assert json.loads(rows[0]["tags"]) == ["a", "b"]


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        write_records([{"id": "1"}], tmp_path / "out.parquet")


def test_empty_csv_is_blank(tmp_path: Path) -> None:
    out = tmp_path / "empty.csv"
    write_records([], out)
    assert out.read_text(encoding="utf-8") == ""
