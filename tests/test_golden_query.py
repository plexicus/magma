"""Golden tests for UAF query output.

These tests run detect_uaf() on real Joern CPGs (from tests/golden/) and
assert the findings match an exact saved snapshot. They catch regressions
in the query engine: line numbers shifting, descriptions changing, or
findings appearing/disappearing silently.

Fixtures are loaded from Parquet when available, falling back to DOT.

To regenerate golden fixtures:
    python tests/generate_goldens.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from magma.graph import CPGGraph
from magma.ingest import _parse_dot
from magma.parquet import load_parquet
from magma.query import detect_uaf

GOLDEN_DIR = Path(__file__).parent / "golden"

# (c_file, expected_finding_count, description_contains)
GOLDEN_QUERY_CASES = [
    ("uaf_simple.c", 1, "free(ptr)"),
    ("clean_no_uaf.c", 0, None),
    ("clean_after_null.c", 0, None),
]


def _load_golden(c_file: str) -> tuple[list, list]:
    """Load nodes/edges from Parquet fixture, falling back to DOT."""
    pq_path = GOLDEN_DIR / f"{c_file}.parquet"
    if pq_path.exists():
        return load_parquet(pq_path)
    dot_path = GOLDEN_DIR / f"{c_file}.dot"
    return _parse_dot(dot_path)


@pytest.mark.parametrize("c_file,expected_count,_desc", GOLDEN_QUERY_CASES)
def test_query_finding_count(
    c_file: str, expected_count: int, _desc: str | None
) -> None:
    """Query produces the expected number of findings."""
    nodes, edges = _load_golden(c_file)
    graph = CPGGraph(nodes, edges)
    findings = detect_uaf(graph)

    assert len(findings) == expected_count, (
        f"{c_file}: expected {expected_count} findings, got {len(findings)}: "
        f"{[f.description for f in findings]}"
    )


@pytest.mark.parametrize("c_file", ["uaf_simple.c"])
def test_query_output_matches_snapshot(c_file: str) -> None:
    """Query output exactly matches the saved golden findings snapshot."""
    findings_path = GOLDEN_DIR / f"{c_file}.findings.json"
    assert findings_path.exists(), f"Golden findings missing: {findings_path}"

    expected = json.loads(findings_path.read_text())
    nodes, edges = _load_golden(c_file)
    graph = CPGGraph(nodes, edges)
    findings = detect_uaf(graph)

    assert len(findings) == expected["finding_count"]

    for actual, expected_f in zip(findings, expected["findings"], strict=False):
        assert actual.vuln_type == expected_f["vuln_type"], (
            f"vuln_type mismatch: {actual.vuln_type} != {expected_f['vuln_type']}"
        )
        assert actual.file == expected_f["file"], (
            f"file mismatch: {actual.file} != {expected_f['file']}"
        )
        assert actual.line == expected_f["line"], (
            f"line mismatch: {actual.line} != {expected_f['line']}"
        )
        assert actual.description == expected_f["description"], (
            f"description mismatch:\n  got:  {actual.description}\n  expected: {expected_f['description']}"
        )


@pytest.mark.parametrize("c_file,_,expected_desc", GOLDEN_QUERY_CASES)
def test_query_finding_descriptions(
    c_file: str, _: int, expected_desc: str | None
) -> None:
    """Vulnerable files produce findings mentioning the free function."""
    if expected_desc is None:
        pytest.skip("Clean file — no description to check")

    nodes, edges = _load_golden(c_file)
    graph = CPGGraph(nodes, edges)
    findings = detect_uaf(graph)

    assert len(findings) >= 1
    assert any(expected_desc in f.description for f in findings), (
        f"Expected description containing '{expected_desc}', "
        f"got: {[f.description for f in findings]}"
    )
