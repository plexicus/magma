"""Golden tests for CPG ingestion (Parquet + DOT).

These tests load golden fixtures from tests/golden/ and assert the parsed
nodes/edges match an exact snapshot. They test the Parquet pipeline by
default (load_parquet), falling back to DOT parsing when no .parquet exists.

To regenerate golden fixtures:
    python tests/generate_goldens.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from magma.ingest import _parse_dot
from magma.parquet import load_parquet

GOLDEN_DIR = Path(__file__).parent / "golden"

GOLDEN_FILES = [
    "uaf_simple.c",
    "clean_no_uaf.c",
    "clean_after_null.c",
]


def _load_golden(c_file: str) -> tuple[list, list]:
    """Load nodes/edges from Parquet fixture, falling back to DOT."""
    pq_path = GOLDEN_DIR / f"{c_file}.parquet"
    if pq_path.exists():
        return load_parquet(pq_path)
    dot_path = GOLDEN_DIR / f"{c_file}.dot"
    return _parse_dot(dot_path)


@pytest.mark.parametrize("c_file", GOLDEN_FILES)
def test_golden_parse_matches_snapshot(c_file: str) -> None:
    """Loading a golden fixture produces the expected node/edge structure."""
    snapshot_path = GOLDEN_DIR / f"{c_file}.snapshot.json"
    assert snapshot_path.exists(), f"Golden snapshot missing: {snapshot_path}"

    expected = json.loads(snapshot_path.read_text())
    nodes, edges = _load_golden(c_file)

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
def test_golden_parse_deterministic(c_file: str) -> None:
    """Loading the same golden fixture twice produces identical results."""
    nodes1, edges1 = _load_golden(c_file)
    nodes2, edges2 = _load_golden(c_file)

    assert len(nodes1) == len(nodes2)
    assert len(edges1) == len(edges2)
    for n1, n2 in zip(nodes1, nodes2, strict=False):
        assert n1.id == n2.id
        assert n1.type == n2.type
        assert n1.label == n2.label
        assert n1.line_number == n2.line_number
        assert n1.properties == n2.properties


@pytest.mark.parametrize("c_file", GOLDEN_FILES)
def test_parquet_fixture_exists(c_file: str) -> None:
    """Each golden file has a .parquet fixture."""
    pq_path = GOLDEN_DIR / f"{c_file}.parquet"
    assert pq_path.exists(), f"Parquet fixture missing: {pq_path}"
    assert (pq_path / "nodes.parquet").exists()
    assert (pq_path / "edges.parquet").exists()
