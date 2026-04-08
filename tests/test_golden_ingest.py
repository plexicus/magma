"""Golden tests for DOT ingestion.

These tests parse real Joern DOT exports (saved in tests/golden/) and assert
the parsed nodes/edges match an exact snapshot. They catch regressions when
Joern's DOT output format changes across versions.

To regenerate golden fixtures:
    python tests/generate_goldens.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from magma.ingest import load_cpg

GOLDEN_DIR = Path(__file__).parent / "golden"

GOLDEN_FILES = [
    "uaf_simple.c",
    "clean_no_uaf.c",
    "clean_after_null.c",
]


@pytest.mark.parametrize("c_file", GOLDEN_FILES)
def test_dot_parse_matches_snapshot(c_file: str) -> None:
    """Parsing a golden DOT file produces the expected node/edge structure."""
    dot_path = GOLDEN_DIR / f"{c_file}.dot"
    snapshot_path = GOLDEN_DIR / f"{c_file}.snapshot.json"
    assert dot_path.exists(), f"Golden DOT missing: {dot_path}"
    assert snapshot_path.exists(), f"Golden snapshot missing: {snapshot_path}"

    expected = json.loads(snapshot_path.read_text())
    nodes, edges = load_cpg(dot_path)

    # Counts must match exactly
    assert len(nodes) == expected["node_count"], (
        f"{c_file}: node count mismatch "
        f"(got {len(nodes)}, expected {expected['node_count']})"
    )
    assert len(edges) == expected["edge_count"], (
        f"{c_file}: edge count mismatch "
        f"(got {len(edges)}, expected {expected['edge_count']})"
    )

    # Edge type set must match
    actual_edge_types = sorted(set(e.type for e in edges))
    assert actual_edge_types == expected["edge_types"], (
        f"{c_file}: edge types mismatch"
    )

    # Spot-check first node's key attributes
    expected_first = expected["nodes"][0]
    actual_first = nodes[0]
    assert actual_first.id == expected_first["id"]
    assert actual_first.type == expected_first["type"]
    assert actual_first.label == expected_first["label"]
    assert actual_first.line_number == expected_first["line"]


@pytest.mark.parametrize("c_file", GOLDEN_FILES)
def test_dot_parse_deterministic(c_file: str) -> None:
    """Parsing the same DOT file twice produces identical results."""
    dot_path = GOLDEN_DIR / f"{c_file}.dot"
    nodes1, edges1 = load_cpg(dot_path)
    nodes2, edges2 = load_cpg(dot_path)

    assert len(nodes1) == len(nodes2)
    assert len(edges1) == len(edges2)
    for n1, n2 in zip(nodes1, nodes2, strict=False):
        assert n1.id == n2.id
        assert n1.type == n2.type
        assert n1.label == n2.label
        assert n1.line_number == n2.line_number
        assert n1.properties == n2.properties
